"""Run the shared SDK package check over the progression payload.

Real files only, a UID sidecar beside every script (unique within the closure), and no dependency
outside the addons `sdk.json` declares. The check itself belongs to game_presentation's tools; this
wrapper points it at this payload so the verification coordinator can list it under this owner.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PACKAGE = HERE.parents[1]
CHECK = PACKAGE.parent / "game_presentation" / "tools" / "check_sdk_package.py"


def main() -> int:
    if not CHECK.is_file():
        print(f"FAIL: shared package check is absent: {CHECK}")
        return 2
    return subprocess.call([sys.executable, str(CHECK), "--sdk-root", str(PACKAGE / "addons" / "progression")])


if __name__ == "__main__":
    sys.exit(main())
