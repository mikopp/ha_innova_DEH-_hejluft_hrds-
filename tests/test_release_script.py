"""scripts/release.py: prepare, check, notes and info (ADR-0031, ADR-0032).

Pure Python on a temporary copy of the files the script touches; no Home
Assistant, no git.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("release", ROOT / "scripts/release.py")
release = importlib.util.module_from_spec(SPEC)
sys.modules["release"] = release  # dataclasses look the module up
SPEC.loader.exec_module(release)

UNRELEASED = """# Changelog

Intro.

---

## Unreleased

### ⚠️ Breaking changes

- **Renamed a switch.** Update automations.

### ✨ Highlights

- **Auto mode.** The unit regulates itself.

### 📚 Documentation

- **New page.**

---

## 0.9.3 (2026-10-21): enables are yours

**Breaking:** old free-form style.
"""


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    manifest = tmp_path / release.MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "domain": "innova_hrds",
                "name": "x",
                "documentation": "https://github.com/o/r#readme",
                "version": "0.9.3",
            },
            indent=4,
        )
        + "\n"
    )
    (tmp_path / "CHANGELOG.md").write_text(UNRELEASED)
    (tmp_path / "README.md").write_text("# X\n\n## Release 0.9.3 — beta\n")
    (tmp_path / "README.de.md").write_text(
        "# X\n\n## Release 0.9.3: Beta\n\n[en](README.md#release-093--beta)\n"
    )
    return tmp_path


def test_lint_passes_with_unreleased_on_top(repo):
    assert release.check(repo) == "0.9.3"


def test_prepare_writes_every_version_place(repo):
    written = release.prepare(repo, "0.9.4", "auto mode", "2026-10-23")
    assert written == ["CHANGELOG.md", "README.de.md", "README.md", release.MANIFEST]
    manifest = json.loads((repo / release.MANIFEST).read_text())
    assert manifest["version"] == "0.9.4"
    assert list(manifest)[:2] == ["domain", "name"]
    changelog = (repo / "CHANGELOG.md").read_text()
    assert "## 0.9.4 (2026-10-23): auto mode\n" in changelog
    assert "## Unreleased" not in changelog
    assert "## Release 0.9.4 — beta" in (repo / "README.md").read_text()
    german = (repo / "README.de.md").read_text()
    assert "## Release 0.9.4: Beta" in german
    assert "README.md#release-094--beta" in german
    assert release.check(repo, "v0.9.4") == "0.9.4"
    assert release.info(repo)["releasable"] == "true"
    assert release.info(repo)["title"] == "v0.9.4: auto mode"


def test_bump_and_default_title(repo):
    assert release.bump("0.9.3", "patch") == "0.9.4"
    assert release.bump("0.9.3", "minor") == "0.10.0"
    assert release.bump("0.9.3", "major") == "1.0.0"
    top, _ = release.top_section(repo)
    assert release.default_title(top) == "Renamed a switch"


def test_prepare_refuses_a_lower_version_and_an_empty_unreleased(repo):
    with pytest.raises(release.ReleaseError, match="not above"):
        release.prepare(repo, "0.9.3", "t", "2026-10-23")
    (repo / "CHANGELOG.md").write_text(
        UNRELEASED.split("## Unreleased")[0] + "## 0.9.3 (2026-10-21): x\n"
    )
    with pytest.raises(release.ReleaseError, match="nothing under"):
        release.prepare(repo, "0.9.4", "t", "2026-10-23")


def test_notes_keep_user_parts_and_fold_docs(repo):
    release.prepare(repo, "0.9.4", "auto mode", "2026-10-23")
    body = release.notes(repo)
    assert body.index("## ⚠️ Breaking changes") < body.index("## ✨ Highlights")
    assert "<details>\n<summary>📚 Documentation</summary>" in body
    assert "### 📚 Documentation" in body.split("<details>")[1]
    assert "https://github.com/o/r/blob/v0.9.4/CHANGELOG.md" in body


@pytest.mark.parametrize(
    ("tag", "match"),
    [("0.9.3", "not vX.Y.Z"), ("v0.9.4", "manifest says 0.9.3")],
)
def test_release_gate_refuses_a_wrong_tag(repo, tag, match):
    with pytest.raises(release.ReleaseError, match=match):
        release.check(repo, tag)


def test_release_gate_refuses_unreleased_left_on_top(repo):
    with pytest.raises(release.ReleaseError, match="still on top"):
        release.check(repo, "v0.9.3")


def test_lint_refuses_a_guessed_version(repo):
    text = UNRELEASED.replace("## Unreleased", "## 0.9.4 (2026-10-22): guess")
    (repo / "CHANGELOG.md").write_text(text)
    with pytest.raises(release.ReleaseError, match="never set a version"):
        release.check(repo)


def test_lint_refuses_a_stale_banner_or_anchor(repo):
    (repo / "README.md").write_text("## Release 0.9.2 — beta\n")
    with pytest.raises(release.ReleaseError, match="banner"):
        release.check(repo)
    (repo / "README.md").write_text("## Release 0.9.3 — beta\n")
    (repo / "README.de.md").write_text(
        "## Release 0.9.3: Beta\n[en](README.md#release-092--beta)\n"
    )
    with pytest.raises(release.ReleaseError, match="stale"):
        release.check(repo)


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ("### ✨ Highlights", "### Changed", "unknown subsection"),
        ("### ⚠️ Breaking changes", "### 📚 Documentation", "appears twice"),
        ("- **Auto mode.** The unit regulates itself.\n", "", "is empty"),
    ],
)
def test_lint_refuses_a_broken_structure(repo, old, new, match):
    (repo / "CHANGELOG.md").write_text(UNRELEASED.replace(old, new, 1))
    with pytest.raises(release.ReleaseError, match=match):
        release.check(repo)


def test_lint_refuses_subsections_out_of_order(repo):
    text = UNRELEASED.replace("### ⚠️ Breaking changes", "### 🧪 Tests and CI")
    (repo / "CHANGELOG.md").write_text(text)
    with pytest.raises(release.ReleaseError, match="out of order"):
        release.check(repo)


def test_the_repository_itself_passes_the_lint():
    assert release.check(ROOT)
