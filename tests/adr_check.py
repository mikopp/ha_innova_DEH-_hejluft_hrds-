"""Consistency check for the architecture decision records (ADRs).

Accepted ADRs are real files in ``.claude/rules/adr/``: Claude Code loads one
when it reads a file matching its ``paths``. The template and the ADRs not in
force (proposed, superseded, rejected, deprecated) are in ``.claude/adr/``,
which nothing loads. ``doc/adr/README.md`` is the index people browse.

ADRs are written for agents as much as for people (ADR-0001), so their shape is
checked like code:

* frontmatter: ``status``, ``date``, ``decision-makers``, ``paths`` (accepted
  and proposed ADRs) in the small YAML subset Claude Code parses
* every ``paths`` glob matches a file in the repository (a stale scope means
  the ADR silently stops loading)
* an accepted or proposed ADR has a ``## Decision`` with RFC 2119 rules and a
  ``## Confirmation`` whose test ids exist; its ``sh`` blocks exit 0
* an accepted or proposed ADR has ``topics`` from ``TOPICS``; every topic
  has an accepted ADR
* a superseded ADR names an existing successor that lists it in
  ``supersedes`` (and the other way round)
* an ADR sits in the folder its status calls for (``--fix`` moves it)
* the index table in ``doc/adr/README.md`` and the topic map
  ``.claude/rules/adr-topics.md`` are current. The map loads with any code,
  test or CI file, so a decision reaches logic in a file no ``paths`` glob
  covers yet (a new module)
* instruction files (CLAUDE.md, .claude/) cite only accepted ADRs

Only failures are printed, to keep the output short for agents.

Run with:  python3 tests/adr_check.py          (check, as CI does)
           python3 tests/adr_check.py --fix    (rewrite index and topic map, move ADRs)
           python3 tests/adr_check.py --no-run (skip the sh blocks)
           python3 tests/adr_check.py --for FILE...  (which ADRs govern these)
           python3 tests/adr_check.py --topic TOPIC... (which ADRs have these)
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
OTHER_DIR = ROOT / ".claude/adr"  # template and ADRs not in force; never loaded
INDEX = ROOT / "doc/adr/README.md"
INDEX_START = "<!-- adr-index:start -->"
INDEX_END = "<!-- adr-index:end -->"
COMPONENT = "custom_components/innova_hrds/"
TOPIC_MAP = ROOT / ".claude/rules/adr-topics.md"
TOPIC_MAP_PATHS = ("custom_components/**", "tests/**", ".github/**")

# What a decision is about, independent of the file it is in. Keep the set
# small: each topic is a heading in the topic map that loads with all code.
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
    def paths(self) -> list[str]:
        value = self.meta.get("paths", [])
        return value if isinstance(value, list) else [value]

    @property
    def topics(self) -> list[str]:
        value = self.meta.get("topics", [])
        return value if isinstance(value, list) else [value]

    @property
    def short_title(self) -> str:
        return re.sub(r"^ADR-\d{4}:\s*", "", self.title)


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
    paths = [*ACCEPTED_DIR.glob("*.md"), *OTHER_DIR.glob("*.md")]
    for path in sorted(paths, key=lambda p: p.name):
        match = ADR_FILE.match(path.name)
        if not match:
            continue
        text = path.read_text(encoding="utf-8")
        adr = Adr(match.group(1), path, lines=text.count("\n") + 1)
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


def index_table(adrs: dict[str, Adr]) -> str:
    rows = ["| ADR | Decision | Status | Loads for |", "|---|---|---|---|"]
    for adr in adrs.values():
        title = adr.short_title
        scope = (
            ", ".join(f"`{p.removeprefix(COMPONENT)}`" for p in adr.paths)
            if adr.status == "accepted"
            else "-"
        )
        link = os.path.relpath(adr.path, INDEX.parent)
        rows.append(f"| [{adr.number}]({link}) | {title} | {adr.status} | {scope} |")
    return "\n".join(rows)


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

    superseded = SUPERSEDED.match(adr.status)
    if superseded:
        successor = adrs.get(superseded.group(1))
        if successor is None:
            fail(f"{name}: successor ADR-{superseded.group(1)} does not exist")
        elif f"ADR-{adr.number}" not in successor.meta.get("supersedes", []):
            fail(f"{name}: ADR-{successor.number} does not list it in supersedes")
    elif adr.status not in STATUSES:
        fail(
            f"{name}: status {adr.status!r} is not one of {STATUSES} or 'superseded by ADR-NNNN'"
        )
    for ref in adr.meta.get("supersedes", []):
        old = adrs.get(ref.removeprefix("ADR-"))
        if old is None or old.status != f"superseded by ADR-{adr.number}":
            fail(f"{name}: supersedes {ref}, whose status does not point back")

    if "decision" not in adr.sections:
        fail(f"{name}: no '## Decision' section")
    if adr.status not in ("accepted", "proposed"):
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
    if not adr.topics:
        fail(f"{name}: no topics, so it is missing from the topic map")
    for topic in adr.topics:
        if topic not in TOPICS:
            fail(f"{name}: unknown topic {topic!r}; one of {sorted(TOPICS)}")
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
                    f"{name}: confirmation command failed:\n{block}{result.stdout}{result.stderr}"
                )


def check_folders(adrs: dict[str, Adr], fix: bool) -> None:
    """Accepted ADRs must be where Claude Code loads them, the rest must not."""
    for adr in adrs.values():
        folder = ACCEPTED_DIR if adr.status == "accepted" else OTHER_DIR
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


def check_index(adrs: dict[str, Adr], fix: bool) -> None:
    text = INDEX.read_text(encoding="utf-8")
    start, end = text.find(INDEX_START), text.find(INDEX_END)
    if start < 0 or end < 0:
        fail(f"{INDEX.name}: index markers missing")
        return
    current = text[start + len(INDEX_START) : end].strip()
    table = index_table(adrs)
    if current != table:
        if fix:
            INDEX.write_text(
                text[: start + len(INDEX_START)] + "\n" + table + "\n" + text[end:],
                encoding="utf-8",
            )
        else:
            fail(f"{INDEX.name}: index is out of date (--fix)")


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
    wanted = topic_map(adrs)
    current = TOPIC_MAP.read_text(encoding="utf-8") if TOPIC_MAP.is_file() else ""
    if current != wanted:
        if fix:
            TOPIC_MAP.write_text(wanted, encoding="utf-8")
        else:
            fail(f"{TOPIC_MAP.relative_to(ROOT)} is out of date (--fix)")


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fix", action="store_true", help="rewrite index and topic map, move ADRs"
    )
    parser.add_argument("--no-run", action="store_true", help="skip sh blocks")
    parser.add_argument(
        "--for", dest="files", nargs="*", metavar="FILE", help="list governing ADRs"
    )
    parser.add_argument(
        "--topic", dest="topics", nargs="+", metavar="TOPIC", help="list ADRs by topic"
    )
    args = parser.parse_args()

    adrs = load_adrs()
    live = [a for a in adrs.values() if a.status in ("accepted", "proposed")]
    if args.topics is not None:
        unknown = sorted(set(args.topics) - TOPICS.keys())
        if unknown:
            print(f"unknown topic(s) {unknown}; known: {', '.join(TOPICS)}")
            return 1
        for adr in live:
            if set(args.topics) & set(adr.topics):
                print(f"{adr.path.relative_to(ROOT)} [{adr.status}] {adr.title}")
        return 0
    if args.files is not None:
        # Which accepted / proposed ADRs govern these files (e.g. a diff).
        covered: set[str] = set()
        for adr in live:
            hits = {
                f for f in args.files if any(glob_regex(p).match(f) for p in adr.paths)
            }
            covered |= hits
            if hits:
                print(f"{adr.path.relative_to(ROOT)} [{adr.status}] {adr.title}")
        for f in args.files:
            if f not in covered:
                print(f"no ADR paths cover {f}: look up its topics (--topic)")
        return 0
    files = repo_files()
    for adr in adrs.values():
        check_adr(adr, adrs, files, run=not args.no_run)
    check_folders(adrs, args.fix)
    check_index(adrs, args.fix)
    check_topic_map(adrs, args.fix)
    check_references(adrs)
    accepted = sum(a.status == "accepted" for a in adrs.values())
    print(
        f"ADRs: {len(adrs)} ({accepted} accepted) - "
        + ("ALL PASS" if not FAILURES else f"{len(FAILURES)} FAILURE(S)")
    )
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
