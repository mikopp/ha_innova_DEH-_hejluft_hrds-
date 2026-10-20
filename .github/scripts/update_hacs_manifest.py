"""Update the version field of the integration manifest.

Used by the release workflow to stamp manifest.json with the release version:

    python .github/scripts/update_hacs_manifest.py --version v1.2.3

A leading ``v`` (as in the release tag) is stripped. Key order is preserved so
``domain`` and ``name`` stay first, as hassfest's own style expects.
"""

import json
import os
import re
import sys

MANIFEST = f"{os.getcwd()}/custom_components/innova_hrds/manifest.json"


def update_manifest() -> None:
    version = "0.0.0"
    for index, value in enumerate(sys.argv):
        if value in ("--version", "-V"):
            version = sys.argv[index + 1]
    version = version.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+([.+-][0-9A-Za-z.+-]+)?", version):
        sys.exit(f"Refusing to stamp a non-version string: {version!r}")

    with open(MANIFEST) as manifestfile:
        manifest = json.load(manifestfile)

    manifest["version"] = version

    with open(MANIFEST, "w") as manifestfile:
        manifestfile.write(json.dumps(manifest, indent=4) + "\n")


if __name__ == "__main__":
    update_manifest()
