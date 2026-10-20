"""Stage a Home Assistant /config for the e2e run.

    python -m tests.e2e.stage <dir>

Copies ``tests/e2e/config`` and ``custom_components/innova_hrds`` into
``<dir>`` (emptied first). Used by the pytest fixtures and by the CI
``check_config`` step, so both test exactly the same configuration.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).resolve().parent / "config"
COMPONENT = ROOT / "custom_components" / "innova_hrds"


def stage(target: Path) -> Path:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(CONFIG, target)
    shutil.copytree(
        COMPONENT,
        target / "custom_components" / "innova_hrds",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return target


def image_from_dockerfile() -> str:
    """The pinned HA image (``FROM`` line of .github/ha-versions/Dockerfile)."""
    dockerfile = ROOT / ".github" / "ha-versions" / "Dockerfile"
    for line in dockerfile.read_text().splitlines():
        if line.startswith("FROM "):
            return line.split()[1]
    raise RuntimeError(f"no FROM line in {dockerfile}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(stage(Path(sys.argv[1]).resolve()))
