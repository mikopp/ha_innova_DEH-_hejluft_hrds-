"""Consistency check for the architecture decision records (ADRs).

Where an ADR lives follows its status (ADR-0001, ADR-0029):

* accepted: real files in ``.claude/rules/adr/``; Claude Code loads one when it
  reads a file matching its ``paths``. ``doc/adr/accepted`` is a symlink to
  that folder for browsing.
* proposed: ``doc/adr/proposed/``
* superseded, rejected, deprecated: ``doc/adr/superseded/``

Neither of the last two is under ``.claude/``, so nothing loads them, and
``.claude/settings.json`` asks before the Read tool opens them. Agents get a
digest from ``--history`` instead. ``doc/adr/README.md`` is the index.

Checked like code:

* frontmatter: ``status``, ``date``, ``decision-makers``, ``topics``; ``paths``
  for accepted and proposed ADRs (the small YAML subset Claude Code parses)
* every ``paths`` glob matches a file (a stale scope means the ADR silently
  stops loading) and every topic is one of ``TOPICS``
* an accepted or proposed ADR has a ``## Decision`` with RFC 2119 rules and a
  ``## Confirmation`` whose test ids exist; accepted ones' ``sh`` blocks exit 0
* a retired ADR says ``## Why it was <superseded|rejected|deprecated>``; a
  superseded one names a successor that lists it in ``supersedes``
* ``revives: [ADR-NNNN]`` names a retired ADR and comes with a
  ``## What changed since ADR-NNNN`` section (the revival challenge, ADR-0029)
* an ADR sits in the folder its status calls for (``--fix`` moves it)
* the index, the two history READMEs and the topic map
  ``.claude/rules/adr-topics.md`` are current
* instruction files (CLAUDE.md, .claude/) cite only accepted ADRs

Only failures are printed, to keep the output short for agents.

Run with:  python3 tests/adr_check.py          (check, as CI does)
           python3 tests/adr_check.py --fix    (rewrite generated files, move ADRs)
           python3 tests/adr_check.py --no-run (skip the sh blocks)
           python3 tests/adr_check.py --for FILE...    (accepted ADRs governing these)
           python3 tests/adr_check.py --topic TOPIC... (accepted ADRs with these)
           python3 tests/adr_check.py --history [--topic TOPIC...]
                                       (digest of proposed and retired ADRs)
           python3 tests/adr_check.py --next   (next free ADR number)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACCEPTED_DIR = ROOT / ".claude/rules/adr"  # loaded by Claude Code, by `paths`
ACCEPTED_LINK = ROOT / "doc/adr/accepted"  # symlink to ACCEPTED_DIR, for browsing
PROPOSED_DIR = ROOT / "doc/adr/proposed"  # history: read only when recording
RETIRED_DIR = ROOT / "doc/adr/superseded"  # history: superseded, rejected, deprecated
INDEX = ROOT / "doc/adr/README.md"
INDEX_START = "<!-- adr-index:start -->"
INDEX_END = "<!-- adr-index:end -->"
COMPONENT = "custom_components/innova_hrds/"
TOPIC_MAP = ROOT / ".claude/rules/adr-topics.md"
TOPIC_MAP_PATHS = ("custom_components/**", "tests/**", ".github/**")

# What a decision is about, independent of the file it is in. Keep the set
# small: each topic is a line in the topic map that loads with all code.
TOPICS = {
    "modbus-reads": "polling, the block plan, decoding registers",
    "modbus-writes": "any write to the unit, the write paths, EEPROM wear",
    "requests": "switching the unit on/off, the DEU and INT requests, their guards",
    "state": "what an entity shows: read-back, unknown, unavailable, pending",
    "entities": "adding, grouping and renaming entities and devices",
    "config": "config and options flows, options, device identity, installer menu",
    "climate": "the climate entity",
    "fan": "the recirculation fan and the airflow estimate",
    "season": "summer and winter, heating",
    "water": "the water circuit and brine",
    "dependencies": "Home Assistant and pymodbus versions",
    "tests": "where a test goes, the simulator",
    "ci": "workflows, releases, repository rules",
    "docs": "documentation and the ADRs themselves",
}

ADR_FILE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
ADR_REF = re.compile(r"\bADR-(\d{4})\b")
TEST_REF = re.compile(r"\b(tests/[\w/]+\.py)::(\w+)")
RFC2119 = re.compile(r"\b(MUST|MUST NOT|SHOULD|SHOULD NOT|MAY)\b")
STATUSES = ("proposed", "accepted", "rejected", "deprecated")
SUPERSEDED = re.compile(r"^superseded by ADR-(\d{4})$")
MAX_LINES = 90  # an accepted ADR loads into an agent's context: keep it short
TEMPLATE_LEFTOVERS = ("YYYY-MM-DD", "# ADR-NNNN", "one rule per bullet")

FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)
    print("  FAIL " + message)


@dataclass
class Adr:
    number: str
    path: pathlib.Path
    meta: dict = field(default_factory=dict)
    title: str = ""
    sections: dict = field(default_factory=dict)
    lines: int = 0

    @property
    def status(self) -> str:
        return str(self.meta.get("status", ""))

    @property
    def retired(self) -> bool:
        return self.status not in ("accepted", "proposed")

    def _list(self, key: str) -> list[str]:
        value = self.meta.get(key, [])
        return value if isinstance(value, list) else [value]

    @property
    def paths(self) -> list[str]:
        return self._list("paths")

    @property
    def topics(self) -> list[str]:
        return self._list("topics")

    @property
    def short_title(self) -> str:
        return re.sub(r"^ADR-\d{4}:\s*", "", self.title)


def folder_for(status: str) -> pathlib.Path:
    if status == "accepted":
        return ACCEPTED_DIR
    if status == "proposed":
        return PROPOSED_DIR
    return RETIRED_DIR


def _scalar(text: str) -> str | list[str]:
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_scalar(p) for p in inner.split(",")] if inner else []
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def parse_frontmatter(text: str, name: str) -> tuple[dict, str]:
    """The ``key: value`` / ``key:`` + ``  - item`` subset, and the body."""
    if not text.startswith("---\n"):
        fail(f"{name}: no frontmatter")
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        fail(f"{name}: frontmatter not closed")
        return {}, text
    meta: dict = {}
    key = None
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and key is not None:
            if not isinstance(meta[key], list):
                meta[key] = []
            meta[key].append(_scalar(line[4:]))
        elif re.match(r"^[a-z][a-z-]*:", line):
            key, _, value = line.partition(":")
            meta[key] = _scalar(value) if value.strip() else []
        else:
            fail(f"{name}: frontmatter line not understood: {line!r}")
    return meta, text[end + 5 :]


def load_adrs() -> dict[str, Adr]:
    adrs: dict[str, Adr] = {}
    paths = [
        p
        for folder in (ACCEPTED_DIR, PROPOSED_DIR, RETIRED_DIR)
        if folder.is_dir()
        for p in folder.glob("*.md")
    ]
    for path in sorted(paths, key=lambda p: p.name):
        match = ADR_FILE.match(path.name)
        if not match:
            continue
        text = path.read_text(encoding="utf-8")
        adr = Adr(match.group(1), path, lines=len(text.splitlines()))
        adr.meta, body = parse_frontmatter(text, path.name)
        current = None
        for line in body.splitlines():
            if line.startswith("# ") and not adr.title:
                adr.title = line[2:].strip()
            elif line.startswith("## "):
                current = line[3:].strip().lower()
                adr.sections[current] = []
            elif current is not None:
                adr.sections[current].append(line)
        if adr.number in adrs:
            fail(f"{path.name}: number {adr.number} used twice")
        adrs[adr.number] = adr
    return adrs


def glob_regex(pattern: str) -> re.Pattern:
    """Claude Code's ``paths`` globs: ``**``, ``*``, ``?`` and ``{a,b}``."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        elif pattern[i] == "{":
            end = pattern.index("}", i)
            options = pattern[i + 1 : end].split(",")
            out, i = out + "(?:" + "|".join(map(re.escape, options)) + ")", end + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def repo_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split()


def check_adr(adr: Adr, adrs: dict[str, Adr], files: list[str], run: bool) -> None:
    name = adr.path.name
    for key in ("status", "date", "decision-makers"):
        if not adr.meta.get(key):
            fail(f"{name}: frontmatter has no {key}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(adr.meta.get("date", ""))):
        fail(f"{name}: date must be YYYY-MM-DD")
    if not adr.title.startswith(f"ADR-{adr.number}: "):
        fail(f"{name}: title must start with 'ADR-{adr.number}: '")
    text = adr.path.read_text(encoding="utf-8")
    for leftover in TEMPLATE_LEFTOVERS:
        if leftover in text:
            fail(f"{name}: template text left in: {leftover!r}")
    if "<!--" in text:
        fail(f"{name}: HTML comment (costs tokens, says nothing)")
    if not adr.topics:
        fail(f"{name}: no topics, so --history and the topic map miss it")
    for topic in adr.topics:
        if topic not in TOPICS:
            fail(f"{name}: unknown topic {topic!r}; one of {sorted(TOPICS)}")

    superseded = SUPERSEDED.match(adr.status)
    if superseded:
        successor = adrs.get(superseded.group(1))
        if successor is None:
            fail(f"{name}: successor ADR-{superseded.group(1)} does not exist")
        elif f"ADR-{adr.number}" not in successor.meta.get("supersedes", []):
            fail(f"{name}: ADR-{successor.number} does not list it in supersedes")
    elif adr.status not in STATUSES:
        fail(
            f"{name}: status {adr.status!r} is not one of {STATUSES} "
            "or 'superseded by ADR-NNNN'"
        )
    for ref in adr.meta.get("supersedes", []):
        old = adrs.get(ref.removeprefix("ADR-"))
        if old is None or old.status != f"superseded by ADR-{adr.number}":
            fail(f"{name}: supersedes {ref}, whose status does not point back")
    for ref in adr.meta.get("revives", []):
        number = ref.removeprefix("ADR-")
        old = adrs.get(number)
        section = adr.sections.get(f"what changed since adr-{number}", [])
        if old is None or not old.retired:
            fail(f"{name}: revives {ref}, which is not a retired ADR")
        elif not any(line.strip() for line in section):
            fail(
                f"{name}: revives {ref}: add '## What changed since ADR-{number}' "
                "with the new evidence"
            )

    if "decision" not in adr.sections:
        fail(f"{name}: no '## Decision' section")
    if adr.retired:
        why = [v for k, v in adr.sections.items() if k.startswith("why it was ")]
        if not any(line.strip() for lines in why for line in lines):
            fail(f"{name}: retired ADR needs '## Why it was superseded/rejected/...'")
        return

    # In force (or about to be): an agent must be able to act on it.
    decision = "\n".join(adr.sections.get("decision", []))
    if not RFC2119.search(decision):
        fail(f"{name}: Decision has no MUST/SHOULD/MAY rule")
    for section in ("context", "consequences", "confirmation"):
        if section not in adr.sections:
            fail(f"{name}: no '## {section.capitalize()}' section")
    if adr.lines > MAX_LINES:
        fail(f"{name}: {adr.lines} lines; keep an ADR under {MAX_LINES}")
    if not adr.paths:
        fail(f"{name}: no paths, so it never loads for an agent")
    for pattern in adr.paths:
        if not any(glob_regex(pattern).match(f) for f in files):
            fail(f"{name}: paths glob {pattern!r} matches no file")

    confirmation = "\n".join(adr.sections.get("confirmation", []))
    for module, test in TEST_REF.findall(confirmation):
        source = ROOT / module
        if not source.is_file() or not re.search(
            rf"^(?:async )?def {test}\(", source.read_text(encoding="utf-8"), re.M
        ):
            fail(f"{name}: confirmation cites {module}::{test}, which does not exist")
    if run and adr.status == "accepted":  # a proposal's check may not hold yet
        for block in re.findall(r"```sh\n(.*?)```", confirmation, re.S):
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", block],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            if result.returncode:
                fail(
                    f"{name}: confirmation command failed:\n"
                    f"{block}{result.stdout}{result.stderr}"
                )


def check_folders(adrs: dict[str, Adr], fix: bool) -> None:
    """Each ADR in the folder its status calls for (only accepted ones load)."""
    for adr in adrs.values():
        folder = folder_for(adr.status)
        if adr.path.parent == folder:
            continue
        target = folder / adr.path.name
        if fix:
            folder.mkdir(parents=True, exist_ok=True)
            moved = subprocess.run(
                ["git", "mv", str(adr.path), str(target)], cwd=ROOT, capture_output=True
            )
            if moved.returncode:
                adr.path.replace(target)
            adr.path = target
        else:
            fail(
                f"{adr.path.relative_to(ROOT)}: status {adr.status!r} belongs in "
                f"{folder.relative_to(ROOT)}/ (--fix)"
            )


def check_accepted_link(fix: bool) -> None:
    """``doc/adr/accepted`` -> the folder of accepted ADRs (browsing only).

    Git on Windows checks a symlink out as a text file holding the target;
    that is accepted too. Nothing reads through the link: the index links the
    real files.
    """
    link, target = ACCEPTED_LINK, os.path.relpath(ACCEPTED_DIR, ACCEPTED_LINK.parent)
    rel = link.relative_to(ROOT)
    if link.is_symlink():
        if os.readlink(link) == target:
            return
        if not fix:
            return fail(f"{rel}: points to {os.readlink(link)}, not {target} (--fix)")
        link.unlink()
    elif link.is_file():
        if link.read_text(encoding="utf-8").strip() != target:
            fail(f"{rel}: a file that does not hold {target}")
        return
    elif link.exists():
        return fail(f"{rel}: exists and is not a link to {target}")
    elif not fix:
        return fail(f"{rel}: missing; a link to {target} (--fix)")
    link.symlink_to(target)


def index_text(adrs: dict[str, Adr]) -> str:
    """Accepted ADRs, with real links; the rest only as links to their lists."""
    rows = ["| ADR | Decision | Loads for |", "|---|---|---|"]
    for adr in adrs.values():
        if adr.status != "accepted":
            continue
        scope = ", ".join(f"`{p.removeprefix(COMPONENT)}`" for p in adr.paths)
        link = os.path.relpath(adr.path, INDEX.parent)
        rows.append(f"| [{adr.number}]({link}) | {adr.short_title} | {scope} |")
    history = [
        f"[{label} ({count})]({folder.name}/README.md)"
        for label, folder in (("proposed", PROPOSED_DIR), ("superseded", RETIRED_DIR))
        if (count := sum(a.path.parent == folder for a in adrs.values()))
    ]
    if history:
        rows += [
            "",
            "Not in force and not loaded; read only when recording an ADR "
            "(ADR-0029): " + ", ".join(history) + ".",
        ]
    return "\n".join(rows)


def history_readme(adrs: dict[str, Adr], folder: pathlib.Path) -> str | None:
    items = [a for a in adrs.values() if a.path.parent == folder]
    if not items:
        return None
    heading = (
        "Proposed" if folder == PROPOSED_DIR else "Superseded, rejected, deprecated"
    )
    lines = [
        f"# {heading} ADRs",
        "",
        "Not loaded by Claude Code. Agents read this folder only when recording,",
        "superseding or reviving a decision (ADR-0029), and then through",
        "`python3 tests/adr_check.py --history`. Generated by `--fix`.",
        "",
        "| ADR | Decision | Status | Topics |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| [{a.number}]({a.path.name}) | {a.short_title} | {a.status} "
        f"| {', '.join(a.topics)} |"
        for a in items
    ]
    return "\n".join(lines) + "\n"


def sync_file(path: pathlib.Path, wanted: str | None, fix: bool) -> None:
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    if current == wanted:
        return
    if not fix:
        return fail(f"{path.relative_to(ROOT)} is out of date (--fix)")
    if wanted is None:
        path.unlink()
    else:
        path.write_text(wanted, encoding="utf-8")


def check_index(adrs: dict[str, Adr], fix: bool) -> None:
    text = INDEX.read_text(encoding="utf-8")
    start, end = text.find(INDEX_START), text.find(INDEX_END)
    if start < 0 or end < 0:
        fail(f"{INDEX.name}: index markers missing")
    else:
        body = text[: start + len(INDEX_START)] + "\n"
        sync_file(INDEX, body + index_text(adrs) + "\n" + text[end:], fix)
    for folder in (PROPOSED_DIR, RETIRED_DIR):
        sync_file(folder / "README.md", history_readme(adrs, folder), fix)


def topic_map(adrs: dict[str, Adr]) -> str:
    lines = ["---", "paths:", *(f'  - "{p}"' for p in TOPIC_MAP_PATHS), "---", ""]
    lines += [
        "# Accepted ADRs by topic",
        "",
        "Generated by `python3 tests/adr_check.py --fix` from the ADRs' `topics`.",
        "A decision binds the logic it is about, in any file. The ADRs whose",
        "`paths` match a file you read load by themselves. For code no path",
        "covers (a new module, logic moved elsewhere), read the ADRs of its",
        "topics before the first edit: ADR-NNNN is `.claude/rules/adr/NNNN-*.md`; run",
        "`python3 tests/adr_check.py --topic <topic>` for their titles.",
        "",
    ]
    for topic, description in TOPICS.items():
        ids = ", ".join(
            f"ADR-{a.number}"
            for a in adrs.values()
            if a.status == "accepted" and topic in a.topics
        )
        lines.append(f"- **{topic}** ({description}): {ids}")
    return "\n".join(lines) + "\n"


def check_topic_map(adrs: dict[str, Adr], fix: bool) -> None:
    for topic in TOPICS:
        if not any(a.status == "accepted" and topic in a.topics for a in adrs.values()):
            fail(f"topic {topic!r} has no accepted ADR; drop it from TOPICS")
    sync_file(TOPIC_MAP, topic_map(adrs), fix)


def check_references(adrs: dict[str, Adr]) -> None:
    """Instruction files cite accepted ADRs only; every ADR cites real ones."""
    adr_files = {a.path for a in adrs.values()}
    instruction_files = [
        p
        for p in ROOT.rglob("*.md")
        if ".git" not in p.parts
        and (p.name == "CLAUDE.md" or ".claude" in p.parts)
        and p not in adr_files
    ]
    for path in instruction_files:
        for number in ADR_REF.findall(path.read_text(encoding="utf-8")):
            adr = adrs.get(number)
            if adr is None or adr.status != "accepted":
                status = adr.status if adr else "missing"
                fail(f"{path.relative_to(ROOT)}: cites ADR-{number} ({status})")
    for adr in adrs.values():
        for number in ADR_REF.findall(adr.path.read_text(encoding="utf-8")):
            if number not in adrs:
                fail(f"{adr.path.name}: cites ADR-{number}, which does not exist")


def first_paragraph(lines: list[str], limit: int) -> str:
    out: list[str] = []
    for line in lines:
        if not line.strip():
            if out:
                break
            continue
        out.append(line.strip())
    text = " ".join(out)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def print_history(adrs: dict[str, Adr], topics: list[str]) -> None:
    """Digest of proposed and retired ADRs, so the files need not be opened."""
    shown = [
        a
        for a in adrs.values()
        if a.status != "accepted" and (not topics or set(topics) & set(a.topics))
    ]
    scope = f" for topics {', '.join(topics)}" if topics else ""
    if not shown:
        print(f"No proposed or retired ADRs{scope}.")
        return
    for adr in shown:
        print(f"ADR-{adr.number} [{adr.status}] {adr.short_title}")
        print(f"  topics: {', '.join(adr.topics)}")
        print(f"  decided: {first_paragraph(adr.sections.get('decision', []), 300)}")
        for key, lines in adr.sections.items():
            if key.startswith("why it was "):
                print(f"  {key}: {first_paragraph(lines, 400)}")
        print(
            f"  file (open only if the new decision overlaps): {adr.path.relative_to(ROOT)}"
        )
    if any(a.retired for a in shown):
        print(
            "A decision that re-adopts a rule above is a revival: stop and "
            "challenge it before writing (ADR-0029)."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fix", action="store_true", help="rewrite generated files, move ADRs"
    )
    parser.add_argument("--no-run", action="store_true", help="skip sh blocks")
    parser.add_argument(
        "--for", dest="files", nargs="*", metavar="FILE", help="list governing ADRs"
    )
    parser.add_argument(
        "--topic", dest="topics", nargs="+", metavar="TOPIC", help="list ADRs by topic"
    )
    parser.add_argument(
        "--history", action="store_true", help="digest of proposed and retired ADRs"
    )
    parser.add_argument("--next", action="store_true", help="next free ADR number")
    args = parser.parse_args()

    adrs = load_adrs()
    accepted = [a for a in adrs.values() if a.status == "accepted"]
    if args.next:
        print(f"{max(int(n) for n in adrs) + 1:04d}")
        return 0
    if args.topics:
        unknown = sorted(set(args.topics) - TOPICS.keys())
        if unknown:
            print(f"unknown topic(s) {unknown}; known: {', '.join(TOPICS)}")
            return 1
    if args.history:
        print_history(adrs, args.topics or [])
        return 0
    if args.topics is not None:
        for adr in accepted:
            if set(args.topics) & set(adr.topics):
                print(f"{adr.path.relative_to(ROOT)} {adr.title}")
        return 0
    if args.files is not None:
        covered: set[str] = set()
        for adr in accepted:
            hits = {
                f for f in args.files if any(glob_regex(p).match(f) for p in adr.paths)
            }
            covered |= hits
            if hits:
                print(f"{adr.path.relative_to(ROOT)} {adr.title}")
        for f in args.files:
            if f not in covered:
                print(f"no ADR paths cover {f}: look up its topics (--topic)")
        return 0
    files = repo_files()
    for adr in adrs.values():
        check_adr(adr, adrs, files, run=not args.no_run)
    check_folders(adrs, args.fix)
    check_accepted_link(args.fix)
    check_index(adrs, args.fix)
    check_topic_map(adrs, args.fix)
    check_references(adrs)
    print(
        f"ADRs: {len(adrs)} ({len(accepted)} accepted) - "
        + ("ALL PASS" if not FAILURES else f"{len(FAILURES)} FAILURE(S)")
    )
    return 1 if FAILURES else 0


if __name__ == "__main__":
    try:
        code = main()
        sys.stdout.flush()
    except BrokenPipeError:
        # The reader left early (`| grep -q`, `| head`): not an error, and under
        # `pipefail` a traceback here would fail the reader's pipeline.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        code = 1 if FAILURES else 0
    sys.exit(code)
