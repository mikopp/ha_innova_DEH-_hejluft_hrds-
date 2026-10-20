"""Keep the test layers on the Home Assistant release (and pymodbus) they claim.

The in-process layer gets Home Assistant from the exact pin inside
pytest-homeassistant-custom-component, the Docker layer from the image tag in
.github/ha-versions/Dockerfile. Dependabot bumps them in separate PRs, so
these tests fail when they drift apart. Only the release (year.month) has to
match; patch releases may differ.
"""

from __future__ import annotations

import json
import re
from importlib.metadata import version
from pathlib import Path

import homeassistant
from homeassistant.const import MAJOR_VERSION, MINOR_VERSION

DOCKERFILE = Path(__file__).parents[2] / ".github" / "ha-versions" / "Dockerfile"


def test_in_process_ha_matches_docker_image():
    match = re.search(
        r"^FROM\s+\S+:(\d+)\.(\d+)\.\d+\s*$", DOCKERFILE.read_text(), re.M
    )
    assert match, f"{DOCKERFILE} must pin a release tag (YYYY.M.P), not latest/beta"
    image = (int(match[1]), int(match[2]))
    assert image == (MAJOR_VERSION, MINOR_VERSION), (
        f"Docker e2e image is Home Assistant {image[0]}.{image[1]}, but "
        f"pytest-homeassistant-custom-component runs {MAJOR_VERSION}.{MINOR_VERSION}: "
        "bump both together (requirements_test.txt and .github/ha-versions/Dockerfile)"
    )


def test_pymodbus_matches_home_assistant():
    # Read the file instead of importing the component: importing it needs
    # modbus_connection, which is not installed.
    manifest = (
        Path(homeassistant.__file__).parent / "components" / "modbus" / "manifest.json"
    )
    wanted = [
        r.partition("==")[2]
        for r in json.loads(manifest.read_text())["requirements"]
        if r.startswith("pymodbus==")
    ]
    assert len(wanted) == 1, "Home Assistant's modbus manifest no longer pins pymodbus"
    assert version("pymodbus") == wanted[0], (
        f"Home Assistant ships pymodbus {wanted[0]}, tests run {version('pymodbus')}: "
        "set pymodbus in requirements_test.txt to the version Home Assistant ships"
    )
