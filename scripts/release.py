#!/usr/bin/env python3
"""Prepare, check and describe a release (ADR-0031, ADR-0032).

The only code that writes the version: ``manifest.json``, the CHANGELOG
heading and the README banners. The owner runs it locally, an agent runs it
through the ``release-prep`` skill, and CI runs ``check``, ``notes`` and
``info``, so all three see the same rules.

    python3 scripts/release.py 0.9.5            prepare, branch, commit, push, PR
    python3 scripts/release.py --bump minor     the same, version from the manifest
    python3 scripts/release.py 0.9.5 --no-git   only change the files (agents)
    python3 scripts/release.py check [vX.Y.Z]   lint (every PR) or release gate
    python3 scripts/release.py notes [X.Y.Z]    the release body, from CHANGELOG
    python3 scripts/release.py info             version/title/releasable, for CI

Standard library only, so it runs anywhere Python 3.12+ does.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = "custom_components/innova_hrds/manifest.json"
CHANGELOG = "CHANGELOG.md"
READMES = ("README.md", "README.de.md")

VERSION = r"\d+\.\d+\.\d+(?:[.+-][0-9A-Za-z.+-]+)?"
VERSION_RE = re.compile(rf"^{VERSION}$")
TAG_RE = re.compile(rf"^v({VERSION})$")
UNRELEASED = "## Unreleased"
VERSION_HEADING = re.compile(rf"^## ({VERSION}) \((\d{{4}}-\d{{2}}-\d{{2}})\): (.+)$")
BANNER = re.compile(rf"^## Release ({VERSION})\b", re.M)
# GitHub's anchor of the English banner, e.g. README.md#release-094--beta-...
BANNER_ANCHOR = re.compile(r"(README\.md#release-)(\d+)(-)")

# ADR-0032: the only subsections, in this order. The last two fold into a
# <details> block in the release notes.
SUBSECTIONS = (
    "⚠️ Breaking changes",
    "✨ Highlights",
    "🛠️ Fixes and other changes",
    "📚 Documentation",
    "🧪 Tests and CI",
)
FOLDED = SUBSECTIONS[3:]


class ReleaseError(Exception):
    """A rule is broken; the message says which and how to fix it."""


# --- files -----------------------------------------------------------------


def read(root: pathlib.Path, name: str) -> str:
    return (root / name).read_text(encoding="utf-8")


def write(root: pathlib.Path, name: str, text: str) -> None:
    (root / name).write_text(text, encoding="utf-8")


def manifest_version(root: pathlib.Path) -> str:
    return str(json.loads(read(root, MANIFEST)).get("version", ""))


def set_manifest_version(root: pathlib.Path, version: str) -> None:
    # Key order is kept so domain and name stay first, as hassfest expects.
    manifest = json.loads(read(root, MANIFEST))
    manifest["version"] = version
    write(root, MANIFEST, json.dumps(manifest, indent=4) + "\n")


def repo_url(root: pathlib.Path) -> str:
    docs = str(json.loads(read(root, MANIFEST)).get("documentation", ""))
    return docs.split("#", 1)[0].rstrip("/")


def anchor_digits(version: str) -> str:
    return re.sub(r"\D", "", version.split("-", 1)[0].split("+", 1)[0])


def tracked_markdown(root: pathlib.Path) -> list[pathlib.Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "*.md"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        return [root / name for name in out]
    except (OSError, subprocess.CalledProcessError):
        return sorted(root.rglob("*.md"))


def parse_version(version: str) -> tuple[int, int, int]:
    major, minor, patch = re.match(r"(\d+)\.(\d+)\.(\d+)", version).groups()
    return int(major), int(minor), int(patch)


def bump(version: str, part: str) -> str:
    major, minor, patch = parse_version(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


# --- CHANGELOG -------------------------------------------------------------


@dataclass
class Section:
    heading: str
    start: int  # line index of the heading
    end: int  # line index after the section
    body: list[str] = field(default_factory=list)

    @property
    def version(self) -> str | None:
        match = VERSION_HEADING.match(self.heading)
        return match.group(1) if match else None

    @property
    def title(self) -> str | None:
        match = VERSION_HEADING.match(self.heading)
        return match.group(3) if match else None

    @property
    def unreleased(self) -> bool:
        return self.heading == UNRELEASED


def sections(text: str) -> tuple[list[str], list[Section]]:
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("## ")]
    result = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        body = lines[start + 1 : end]
        while body and body[-1].strip() in ("", "---"):
            body.pop()
        result.append(Section(lines[start], start, end, body))
    return lines, result


def subsections(section: Section) -> tuple[list[str], dict[str, list[str]]]:
    """The text before the first ``###``, and each subsection's lines."""
    intro: list[str] = []
    parts: dict[str, list[str]] = {}
    current = None
    for line in section.body:
        if line.startswith("### "):
            current = line[4:].strip()
            if current in parts:
                raise ReleaseError(f"{CHANGELOG}: '### {current}' appears twice")
            parts[current] = []
        elif current is None:
            intro.append(line)
        else:
            parts[current].append(line)
    return intro, parts


def has_entries(lines: list[str]) -> bool:
    return any(line.strip() for line in lines)


def check_structure(section: Section) -> None:
    """ADR-0032: only the fixed subsections, in order, none empty."""
    intro, parts = subsections(section)
    unknown = [name for name in parts if name not in SUBSECTIONS]
    if unknown:
        raise ReleaseError(
            f"{CHANGELOG} '{section.heading}': unknown subsection(s) {unknown}; "
            f"use only: {', '.join(SUBSECTIONS)}"
        )
    order = [SUBSECTIONS.index(name) for name in parts]
    if order != sorted(order):
        raise ReleaseError(
            f"{CHANGELOG} '{section.heading}': subsections out of order; "
            f"the order is: {', '.join(SUBSECTIONS)}"
        )
    for name, lines in parts.items():
        if not has_entries(lines):
            raise ReleaseError(
                f"{CHANGELOG} '{section.heading}': '### {name}' is empty; drop it"
            )
    if has_entries(intro) and not parts:
        raise ReleaseError(
            f"{CHANGELOG} '{section.heading}': entries must sit under the "
            f"subsections: {', '.join(SUBSECTIONS)}"
        )


def top_section(root: pathlib.Path) -> tuple[Section, list[Section]]:
    _, found = sections(read(root, CHANGELOG))
    if not found:
        raise ReleaseError(f"{CHANGELOG}: no '## ' section")
    return found[0], found


def default_title(section: Section) -> str:
    _, parts = subsections(section)
    for name in SUBSECTIONS:
        for line in parts.get(name, []):
            match = re.search(r"\*\*(.+?)\*\*", line)
            if match:
                return match.group(1).strip().rstrip(".:")
    return "maintenance release"


# --- check -------------------------------------------------------------------


def check(root: pathlib.Path, tag: str | None = None) -> str:
    """Raise ReleaseError on the first broken rule; return the manifest version.

    Without a tag this is the PR lint (ADR-0032): no guessed version, the
    Unreleased structure, the banners. With a tag it is the release gate
    (ADR-0031): the tag, manifest, CHANGELOG and banners name one version.
    """
    version = manifest_version(root)
    if not VERSION_RE.match(version):
        raise ReleaseError(f"{MANIFEST}: version {version!r} is not X.Y.Z")

    for name in READMES:
        banners = BANNER.findall(read(root, name))
        if banners != [version]:
            raise ReleaseError(
                f"{name}: the '## Release X.Y.Z' banner says {banners or 'nothing'},"
                f" the manifest says {version}; only scripts/release.py changes it"
            )
    digits = anchor_digits(version)
    for path in tracked_markdown(root):
        for match in BANNER_ANCHOR.finditer(path.read_text(encoding="utf-8")):
            if match.group(2) != digits:
                raise ReleaseError(
                    f"{path.relative_to(root)}: link to README.md#release-"
                    f"{match.group(2)}-… is stale; the banner is {version}"
                )

    top, found = top_section(root)
    for section in found[1:]:
        if section.unreleased:
            raise ReleaseError(f"{CHANGELOG}: '{UNRELEASED}' must be the first section")
    versions = [s.version for s in found if s.version]
    duplicates = sorted({v for v in versions if versions.count(v) > 1})
    if duplicates:
        raise ReleaseError(f"{CHANGELOG}: version heading(s) {duplicates} twice")
    if not top.unreleased and not top.version:
        raise ReleaseError(
            f"{CHANGELOG}: the first section must be '{UNRELEASED}' or "
            f"'## X.Y.Z (YYYY-MM-DD): title', not {top.heading!r}"
        )
    released = top if top.version else next((s for s in found if s.version), None)
    if released is not None and released.version != version:
        raise ReleaseError(
            f"{CHANGELOG}: the newest version heading is {released.version}, the "
            f"manifest says {version}. Pull requests add to '{UNRELEASED}' and "
            "never set a version; scripts/release.py does (ADR-0032)"
        )
    check_structure(top)

    if tag is not None:
        match = TAG_RE.match(tag)
        if not match:
            raise ReleaseError(f"tag {tag!r} is not vX.Y.Z")
        if match.group(1) != version:
            raise ReleaseError(
                f"tag {tag} but the tagged commit's manifest says {version}: "
                "publish the draft that release-draft.yaml made, or run "
                f"scripts/release.py {match.group(1)} first"
            )
        if top.unreleased:
            raise ReleaseError(
                f"{CHANGELOG}: '{UNRELEASED}' is still on top at {tag}: run "
                f"scripts/release.py {match.group(1)} and merge its PR first"
            )
    return version


# --- notes -------------------------------------------------------------------


def notes(root: pathlib.Path, version: str | None = None) -> str:
    """The release body: the user parts verbatim, docs and tests folded."""
    _, found = sections(read(root, CHANGELOG))
    version = version or manifest_version(root)
    section = next((s for s in found if s.version == version), None)
    if section is None:
        raise ReleaseError(f"{CHANGELOG}: no '## {version} (date): title' section")
    intro, parts = subsections(section)
    out: list[str] = []
    if has_entries(intro):
        out += [*trim(intro), ""]
    for name in SUBSECTIONS:
        if name in parts and name not in FOLDED:
            out += [f"## {name}", "", *trim(parts[name]), ""]
    folded = [name for name in FOLDED if name in parts]
    if folded:
        out += [
            "<details>",
            f"<summary>{' · '.join(folded)}</summary>",
            "",
        ]
        for name in folded:
            out += [f"### {name}", "", *trim(parts[name]), ""]
        out += ["</details>", ""]
    url = repo_url(root)
    out += [
        "---",
        "",
        f"Full changelog: [CHANGELOG.md]({url}/blob/v{version}/CHANGELOG.md). "
        f"Install or update through HACS: [README]({url}#1-install).",
    ]
    return "\n".join(out) + "\n"


def trim(lines: list[str]) -> list[str]:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def info(root: pathlib.Path) -> dict[str, str]:
    """What release-draft.yaml needs: is the top of CHANGELOG a release?"""
    version = manifest_version(root)
    top, _ = top_section(root)
    releasable = top.version == version
    return {
        "version": version,
        "tag": f"v{version}",
        "title": f"v{version}: {top.title}" if releasable else "",
        "releasable": "true" if releasable else "false",
    }


# --- prepare -----------------------------------------------------------------


def prepare(root: pathlib.Path, version: str, title: str, date: str) -> None:
    """Write the version into the manifest, CHANGELOG and README banners."""
    current = check(root)
    if not VERSION_RE.match(version):
        raise ReleaseError(f"version {version!r} is not X.Y.Z")
    if parse_version(version) <= parse_version(current):
        raise ReleaseError(f"version {version} is not above the current {current}")
    top, _ = top_section(root)
    if not top.unreleased or not has_entries(top.body):
        raise ReleaseError(
            f"{CHANGELOG}: nothing under '{UNRELEASED}' to release; pull requests "
            "add their entries there (ADR-0032)"
        )
    title = " ".join(title.split())
    if not title:
        raise ReleaseError("the release title is empty")

    lines, _ = sections(read(root, CHANGELOG))
    lines[top.start] = f"## {version} ({date}): {title}"
    write(root, CHANGELOG, "\n".join(lines) + "\n")
    set_manifest_version(root, version)
    for name in READMES:
        text = BANNER.sub(f"## Release {version}", read(root, name), count=1)
        write(root, name, text)
    digits = anchor_digits(version)
    for path in tracked_markdown(root):
        text = path.read_text(encoding="utf-8")
        new = BANNER_ANCHOR.sub(rf"\g<1>{digits}\g<3>", text)
        if new != text:
            path.write_text(new, encoding="utf-8")
    check(root)


def changed_files(root: pathlib.Path) -> list[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line[3:] for line in out.splitlines() if line.strip()]


def git(root: pathlib.Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise ReleaseError(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def preflight(root: pathlib.Path, version: str) -> None:
    if changed_files(root):
        raise ReleaseError("the working tree has changes; commit or stash them first")
    if git(root, "branch", "--show-current") != "main":
        raise ReleaseError("run it on main (git switch main && git pull)")
    git(root, "fetch", "--quiet", "origin", "main", "--tags")
    if git(root, "rev-parse", "HEAD") != git(root, "rev-parse", "origin/main"):
        raise ReleaseError("main is not origin/main; git pull first")
    if git(root, "tag", "--list", f"v{version}"):
        raise ReleaseError(f"tag v{version} exists already")


def run_checks(root: pathlib.Path) -> None:
    commands = [
        [sys.executable, "tests/wiring_check.py"],
        [sys.executable, "tests/adr_check.py"],
    ]
    if shutil.which("ruff"):
        commands[:0] = [["ruff", "check", "."], ["ruff", "format", "--check", "."]]
    else:
        print("  ruff not installed: lint left to CI")
    for command in commands:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True)
        if result.returncode:
            raise ReleaseError(
                f"{' '.join(command)} failed:\n{result.stdout}{result.stderr}"
            )
        print(
            f"  ok  {' '.join(command[-2:] if command[0] == 'ruff' else command[1:])}"
        )


def open_pull_request(root: pathlib.Path, version: str, title: str) -> None:
    branch = f"release/v{version}"
    git(root, "switch", "-c", branch)
    git(root, "add", "-A")
    git(root, "commit", "-m", f"Release v{version}: {title}")
    git(root, "push", "-u", "origin", branch)
    body = (
        f"Prepares v{version} with `scripts/release.py` (ADR-0031).\n\n"
        "After merging: open the draft release `release-draft.yaml` made, "
        "review it and **Publish** it (a normal release, not a pre-release).\n\n"
        "## Release notes preview\n\n" + notes(root, version)
    )
    if shutil.which("gh"):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
            handle.write(body)
        try:
            subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    "main",
                    "--head",
                    branch,
                    "--title",
                    f"Release v{version}: {title}",
                    "--body-file",
                    handle.name,
                ],
                cwd=root,
                check=True,
            )
        finally:
            os.unlink(handle.name)
    else:
        print(f"Open the PR: {repo_url(root)}/compare/main...{branch}?expand=1")


def ask_title(default: str) -> str:
    if not sys.stdin.isatty():
        return default
    answer = input(f"Release title [{default}]: ").strip()
    return answer or default


def cmd_prepare(argv: list[str], root: pathlib.Path) -> None:
    parser = argparse.ArgumentParser(
        prog="release.py", description="Prepare a release (ADR-0031)."
    )
    parser.add_argument("version", nargs="?", help="X.Y.Z (default: --bump)")
    parser.add_argument("--bump", choices=("patch", "minor", "major"))
    parser.add_argument("--title", help="short title for the CHANGELOG heading")
    parser.add_argument(
        "--no-git", action="store_true", help="only change the files (agents)"
    )
    parser.add_argument("--skip-checks", action="store_true")
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    args = parser.parse_args(argv)
    if args.version and args.bump:
        parser.error("give a version or --bump, not both")
    version = args.version or bump(manifest_version(root), args.bump or "patch")
    version = version.removeprefix("v")

    if not args.no_git:
        preflight(root, version)
    top, _ = top_section(root)
    title = args.title or ask_title(default_title(top))
    prepare(root, version, title, args.date)
    print(f"Prepared v{version}: {title}")
    if not args.skip_checks:
        run_checks(root)
    print(
        "Reminder: review plans/todo.md against this release's entries "
        "(the release-prep skill does this for an agent run)."
    )
    if args.no_git:
        print("Files changed; commit them and open the release PR.")
    else:
        open_pull_request(root, version, title)


def main(argv: list[str] | None = None, root: pathlib.Path = ROOT) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["check"]:
            version = check(root, argv[1] if len(argv) > 1 else None)
            print(f"release check ok ({version})")
        elif argv[:1] == ["notes"]:
            sys.stdout.write(notes(root, argv[1] if len(argv) > 1 else None))
        elif argv[:1] == ["info"]:
            for key, value in info(root).items():
                print(f"{key}={value}")
        else:
            cmd_prepare(argv, root)
    except ReleaseError as error:
        print(f"release.py: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
