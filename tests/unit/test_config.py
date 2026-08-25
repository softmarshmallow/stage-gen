from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.config import (
    CapabilityName,
    ConfigError,
    TransparencyMode,
    assert_capabilities,
    load_config,
    parse_transparency_mode,
    transparency_capabilities,
)


def test_config_precedence_defaults_and_timeout_conversion() -> None:
    config = load_config(
        env={
            "OUT_DIR": "old-out",
            "STAGE_GEN_OUT_DIR": "new-out",
            "IMAGE_MODEL": "old/image",
            "STAGE_GEN_IMAGE_MODEL": "new/image",
            "STAGE_GEN_CAPABILITY_TIMEOUT_MS": "1250",
            "STAGE_GEN_CHARACTER_LIBRARY_ROOT": "/workspace/characters",
            "STAGE_GEN_GAME_LIBRARY_ROOT": "/workspace/games",
        }
    )
    assert str(config.out_dir) == "new-out"
    assert config.image_model == "new/image"
    assert config.text_model == "openai/gpt-5.5"
    assert config.music_model == "google/lyria-3-pro-preview"
    assert config.transparency_mode is TransparencyMode.AI
    assert config.capability_timeout_s == 1.25
    assert config.character_library_root == Path("/workspace/characters")
    assert config.game_library_root == Path("/workspace/games")


def test_authored_library_roots_are_unset_by_default() -> None:
    assert load_config(env={}).character_library_root is None
    assert load_config(env={}).game_library_root is None


def test_capability_errors_name_variables_but_not_present_values() -> None:
    config = load_config(env={"OPENROUTER_API_KEY": "secret-value"})
    with pytest.raises(ConfigError) as captured:
        assert_capabilities(config, [CapabilityName.BACKGROUND_REMOVAL])
    assert "FAL_KEY" in str(captured.value)
    assert "secret-value" not in str(captured.value)


def test_transparency_validation_and_conditional_capability() -> None:
    assert parse_transparency_mode("chroma") is TransparencyMode.CHROMA
    with pytest.raises(ValueError, match="must be ai or chroma"):
        parse_transparency_mode("AI")
    assert transparency_capabilities(TransparencyMode.AI) == (CapabilityName.BACKGROUND_REMOVAL,)
    assert transparency_capabilities(TransparencyMode.CHROMA) == ()


@pytest.mark.parametrize("value", ["0", "-1", "1.5"])
def test_timeout_env_requires_canonical_positive_integer(value: str) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        load_config(env={"STAGE_GEN_STAGE_TIMEOUT_MS": value})


def test_timeout_env_accepts_integer_valued_numeric_text() -> None:
    assert load_config(env={"STAGE_GEN_STAGE_TIMEOUT_MS": " 1000.0 "}).stage_timeout_ms == 1000


def test_config_loads_only_allowlisted_provider_values_from_cwd_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("OPENROUTER_API_KEY", "FAL_KEY", "_STAGE_GEN_DISABLE_DOTENV"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=file-openrouter\n"
        "FAL_KEY='file-fal'\n"
        "STAGE_GEN_IMAGE_MODEL=ignored/from-file\n"
        "UNRELATED_SECRET=ignored-value\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.open_router_api_key == "file-openrouter"
    assert config.fal_key == "file-fal"
    assert config.image_model == "openai/gpt-image-2"
    assert "file-openrouter" not in repr(config)
    assert "file-fal" not in repr(config)
    assert "ignored-value" not in repr(config)


def test_process_provider_environment_takes_precedence_over_cwd_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("_STAGE_GEN_DISABLE_DOTENV", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "process-openrouter")
    monkeypatch.delenv("FAL_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=file-openrouter\nFAL_KEY=file-fal\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.open_router_api_key == "process-openrouter"
    assert config.fal_key == "file-fal"
    assert "process-openrouter" not in repr(config)
    assert "file-fal" not in repr(config)


def test_offline_gate_switch_prevents_cwd_dotenv_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setenv("_STAGE_GEN_DISABLE_DOTENV", "1")
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=file-openrouter\nFAL_KEY=file-fal\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.open_router_api_key is None
    assert config.fal_key is None


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (
            "OPENROUTER_API_KEY=first\nOPENROUTER_API_KEY=second\n",
            "duplicate key: OPENROUTER_API_KEY",
        ),
        ("FAL_KEY without-equals\n", "malformed assignment for FAL_KEY"),
        ('OPENROUTER_API_KEY="unterminated\n', "malformed quoted value"),
        (r'FAL_KEY="line\nfeed"' + "\n", "unsafe value for FAL_KEY"),
    ],
)
def test_config_rejects_unsafe_allowlisted_dotenv_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    contents: str,
    message: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("OPENROUTER_API_KEY", "FAL_KEY", "_STAGE_GEN_DISABLE_DOTENV"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_config()
