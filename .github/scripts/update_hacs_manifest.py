"""Update the version field of the integration manifest.

Used by the release tooling to stamp manifest.json with the release version:

    python .github/scripts/update_hacs_manifest.py --version 1.2.3
"""

import json
import os
import sys

MANIFEST = f"{os.getcwd()}/custom_components/innova_hrds/manifest.json"


def update_manifest() -> None:
    version = "0.0.0"
    for index, value in enumerate(sys.argv):
        if value in ("--version", "-V"):
            version = sys.argv[index + 1]

    with open(MANIFEST) as manifestfile:
        manifest = json.load(manifestfile)

    manifest["version"] = version

    with open(MANIFEST, "w") as manifestfile:
        manifestfile.write(json.dumps(manifest, indent=4, sort_keys=True))


if __name__ == "__main__":
    update_manifest()
