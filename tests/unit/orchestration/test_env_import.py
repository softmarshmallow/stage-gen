from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from stage_gen.orchestration.env_import import import_provider_env


def test_env_import_copies_only_allowlisted_keys_with_private_mode(tmp_path: Path) -> None:
    source = tmp_path / "source.env"
    destination = tmp_path / "nested" / "destination.env"
    openai = "synthetic-openai-private"
    openrouter = "synthetic-openrouter-private"
    fal = "synthetic-fal-private"
    elevenlabs = "synthetic-elevenlabs-private"
    source.write_text(
        "\n".join(
            (
                f"OPENAI_API_KEY={openai}",
                f"OPENROUTER_API_KEY={openrouter}",
                f"FAL_KEY='{fal}'",
                f"ELEVENLABS_API_KEY={elevenlabs}",
                "DATABASE_URL=must-not-copy",
                "UNRELATED_SECRET=must-not-copy-either",
            )
        ),
        encoding="utf-8",
    )

    result = import_provider_env(source, destination)

    written = destination.read_text(encoding="utf-8")
    assert json.loads(written.splitlines()[0].split("=", 1)[1]) == openai
    assert json.loads(written.splitlines()[1].split("=", 1)[1]) == openrouter
    assert json.loads(written.splitlines()[2].split("=", 1)[1]) == fal
    assert json.loads(written.splitlines()[3].split("=", 1)[1]) == elevenlabs
    assert "DATABASE_URL" not in written
    assert "UNRELATED_SECRET" not in written
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    rendered = json.dumps(result)
    assert result["imported"] == [
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "FAL_KEY",
        "ELEVENLABS_API_KEY",
    ]
    assert result["count"] == 4
    assert openai not in rendered
    assert openrouter not in rendered
    assert fal not in rendered
    assert elevenlabs not in rendered


def test_env_import_missing_key_error_never_exposes_present_value(tmp_path: Path) -> None:
    source = tmp_path / "source.env"
    destination = tmp_path / "destination.env"
    present = "synthetic-present-private"
    source.write_text(
        f"OPENAI_API_KEY={present}\nOPENROUTER_API_KEY=synthetic-openrouter\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="FAL_KEY") as captured:
        import_provider_env(source, destination)

    assert present not in str(captured.value)
    assert not destination.exists()
