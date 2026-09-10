from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from . import run_fixture


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m external_image_consumer OUTPUT_DIR")
    result = asyncio.run(run_fixture(Path(sys.argv[1])))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
