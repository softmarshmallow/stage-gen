"""Read-only collection commands must not load unrelated game preparation graphs."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest


@pytest.mark.parametrize("arguments", [["--help"], ["models", "routes"], ["doctor", "--json"]])
def test_read_only_commands_do_not_import_game_builders(arguments: list[str]) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json
import sys
from io import StringIO
from demo_game_collection.cli import main

output = StringIO()
errors = StringIO()
status = main(json.loads(sys.argv[1]), stdout=output, stderr=errors)
prefixes = ('bellweather_pipeline', 'iron_petal_unit_pipeline', 'the_grain_pipeline',
            'ember_hollow_pipeline')
loaded = sorted(name for name in sys.modules if name.startswith(prefixes))
print(json.dumps({'status': status, 'errors': errors.getvalue(), 'loaded': loaded}))
""",
            json.dumps(arguments),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["status"] in ({0, 2} if arguments[0] == "doctor" else {0})
    assert report["errors"] == ""
    # The parser reads only this small game-owned vocabulary, with no node imports.
    assert report["loaded"] == ["ember_hollow_pipeline", "ember_hollow_pipeline.scopes"]
