"""Environment-derived configuration at the headless application boundary."""

from __future__ import annotations

import math
import os
from collections.abc import Iterable, Mapping
from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator

from gnode import ContractModel
from stage_gen.provider_env import load_provider_dotenv


class CapabilityName(StrEnum):
    STRUCTURED_GENERATION = "structured_generation"
    TOOL_LOOP = "tool_loop"
    IMAGE_GENERATION = "image_generation"
    NATIVE_IMAGE_GENERATION = "native_image_generation"
    BACKGROUND_REMOVAL = "background_removal"
    MUSIC_GENERATION = "music_generation"
    SOUND_EFFECT_GENERATION = "sound_effect_generation"
    SPEECH_GENERATION = "speech_generation"


class TransparencyMode(StrEnum):
    NATIVE = "native"
    AI = "ai"
    CHROMA = "chroma"


DEFAULT_TRANSPARENCY_MODE = TransparencyMode.NATIVE


class StageGenConfig(ContractModel):
    out_dir: Path = Path("out")
    #: Where every recipe's content-addressed cache lives, under its own namespace.
    #: Repo-anchored rather than derived from a run's --output: a run written under
    #: a different parent used to start a cold cache silently, and `rm -rf out`
    #: destroyed a gigabyte of paid artifacts that only lived there.
    cache_dir: Path = Path(".cache")
    game_library_root: Path | None = None
    openai_api_key: str | None = Field(default=None, repr=False)
    open_router_api_key: str | None = Field(default=None, repr=False)
    fal_key: str | None = Field(default=None, repr=False)
    elevenlabs_api_key: str | None = Field(default=None, repr=False)

    def secret_values(self) -> tuple[str, ...]:
        """Every provider credential this configuration holds, for trace redaction.

        One list, so an executor cannot forget the key its newest modality
        needs: the runner's redaction set omitted the ElevenLabs key for as
        long as speech existed, and a scheduler redacts exactly what it is
        handed.
        """

        return tuple(
            value
            for value in (
                self.openai_api_key,
                self.open_router_api_key,
                self.fal_key,
                self.elevenlabs_api_key,
            )
            if value is not None
        )

    openai_base_url: str | None = None
    open_router_base_url: str | None = None
    fal_base_url: str | None = None
    elevenlabs_base_url: str | None = None
    openai_image_model: str = "gpt-image-2"
    openai_image_ipm: int = Field(default=150, ge=1)
    image_model: str = "openai/gpt-image-2"
    text_model: str = "openai/gpt-5.6-sol"
    music_model: str = "google/lyria-3-pro-preview"
    sound_effect_model: str = "eleven_text_to_sound_v2"
    speech_model: str = "eleven_v3"
    background_removal_model: str = "fal-ai/birefnet/v2"
    transparency_mode: TransparencyMode = DEFAULT_TRANSPARENCY_MODE
    stage_timeout_ms: int = Field(default=1_800_000, gt=0)
    capability_timeout_ms: int = Field(default=600_000, gt=0)

    @field_validator(
        "openai_image_model",
        "image_model",
        "text_model",
        "music_model",
        "sound_effect_model",
        "speech_model",
        "background_removal_model",
    )
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model identifiers must be non-empty")
        return value.strip()

    @property
    def stage_timeout_s(self) -> float:
        return self.stage_timeout_ms / 1000

    @property
    def capability_timeout_s(self) -> float:
        return self.capability_timeout_ms / 1000


class ConfigError(ValueError):
    """A capability the run needs has no credential; a value error, because it is one."""

    def __init__(self, missing: Iterable[str]) -> None:
        self.missing = tuple(dict.fromkeys(missing))
        suffix = "" if len(self.missing) == 1 else "s"
        super().__init__(
            f"missing required environment variable{suffix}: {', '.join(self.missing)}"
        )


def load_config(
    *,
    env: Mapping[str, str | None] | None = None,
    require: Iterable[CapabilityName | str] = (),
) -> StageGenConfig:
    values: Mapping[str, str | None] = _application_environment() if env is None else env
    config = StageGenConfig(
        out_dir=_first(values, "STAGE_GEN_OUT_DIR", "OUT_DIR") or "out",
        cache_dir=_first(values, "STAGE_GEN_CACHE_DIR") or ".cache",
        game_library_root=_first(values, "STAGE_GEN_GAME_LIBRARY_ROOT"),
        openai_api_key=_first(values, "OPENAI_API_KEY"),
        open_router_api_key=_first(values, "OPENROUTER_API_KEY"),
        fal_key=_first(values, "FAL_KEY"),
        elevenlabs_api_key=_first(values, "ELEVENLABS_API_KEY"),
        openai_base_url=_first(values, "OPENAI_BASE_URL"),
        open_router_base_url=_first(values, "OPENROUTER_BASE_URL"),
        fal_base_url=_first(values, "FAL_BASE_URL"),
        elevenlabs_base_url=_first(values, "ELEVENLABS_BASE_URL"),
        openai_image_model=_first(values, "STAGE_GEN_OPENAI_IMAGE_MODEL") or "gpt-image-2",
        openai_image_ipm=_positive_integer(
            values.get("STAGE_GEN_OPENAI_IMAGE_IPM"),
            "STAGE_GEN_OPENAI_IMAGE_IPM",
            150,
        ),
        image_model=_first(values, "STAGE_GEN_IMAGE_MODEL", "IMAGE_MODEL") or "openai/gpt-image-2",
        text_model=_first(values, "STAGE_GEN_TEXT_MODEL", "TEXT_MODEL") or "openai/gpt-5.6-sol",
        music_model=_first(values, "STAGE_GEN_MUSIC_MODEL", "MUSIC_MODEL")
        or "google/lyria-3-pro-preview",
        sound_effect_model=_first(values, "STAGE_GEN_SOUND_EFFECT_MODEL", "SOUND_EFFECT_MODEL")
        or "eleven_text_to_sound_v2",
        speech_model=_first(values, "STAGE_GEN_SPEECH_MODEL", "SPEECH_MODEL") or "eleven_v3",
        background_removal_model=_first(
            values, "STAGE_GEN_BACKGROUND_REMOVAL_MODEL", "BACKGROUND_REMOVAL_MODEL"
        )
        or "fal-ai/birefnet/v2",
        transparency_mode=parse_transparency_mode(
            _first(values, "TRANSPARENCY_MODE") or DEFAULT_TRANSPARENCY_MODE,
            "TRANSPARENCY_MODE",
        ),
        stage_timeout_ms=_positive_integer(
            values.get("STAGE_GEN_STAGE_TIMEOUT_MS"),
            "STAGE_GEN_STAGE_TIMEOUT_MS",
            1_800_000,
        ),
        capability_timeout_ms=_positive_integer(
            values.get("STAGE_GEN_CAPABILITY_TIMEOUT_MS"),
            "STAGE_GEN_CAPABILITY_TIMEOUT_MS",
            600_000,
        ),
    )
    assert_capabilities(config, require)
    return config


def _application_environment() -> Mapping[str, str]:
    process_environment = dict(os.environ)
    if process_environment.get("_STAGE_GEN_DISABLE_DOTENV") == "1":
        return process_environment
    dotenv_environment = load_provider_dotenv(Path.cwd() / ".env")
    application_environment = {str(key): value for key, value in dotenv_environment.items()}
    application_environment.update(process_environment)
    return application_environment


def assert_capabilities(
    config: StageGenConfig, capabilities: Iterable[CapabilityName | str]
) -> None:
    missing: list[str] = []
    for raw_capability in capabilities:
        capability = CapabilityName(raw_capability)
        if (
            capability
            in {
                CapabilityName.STRUCTURED_GENERATION,
                CapabilityName.TOOL_LOOP,
                CapabilityName.IMAGE_GENERATION,
                CapabilityName.MUSIC_GENERATION,
            }
            and not config.open_router_api_key
        ):
            missing.append("OPENROUTER_API_KEY")
        if capability is CapabilityName.BACKGROUND_REMOVAL and not config.fal_key:
            missing.append("FAL_KEY")
        if capability is CapabilityName.NATIVE_IMAGE_GENERATION and not config.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if (
            capability in {CapabilityName.SOUND_EFFECT_GENERATION, CapabilityName.SPEECH_GENERATION}
            and not config.elevenlabs_api_key
        ):
            missing.append("ELEVENLABS_API_KEY")
    if missing:
        raise ConfigError(missing)


def parse_transparency_mode(value: object, label: str = "transparency mode") -> TransparencyMode:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be native, ai, or chroma")
    try:
        return TransparencyMode(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be native, ai, or chroma") from error


def transparency_capabilities(mode: TransparencyMode) -> tuple[CapabilityName, ...]:
    if mode is TransparencyMode.NATIVE:
        return (CapabilityName.NATIVE_IMAGE_GENERATION,)
    if mode is TransparencyMode.AI:
        return (CapabilityName.BACKGROUND_REMOVAL,)
    return ()


def _first(env: Mapping[str, str | None], *keys: str) -> str | None:
    for key in keys:
        value = env.get(key)
        if value is not None and value.strip():
            return value.strip()
    return None


def _positive_integer(value: str | None, name: str, fallback: int) -> int:
    if value is None or not value.strip():
        return fallback
    try:
        numeric = float(value.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if not math.isfinite(numeric) or numeric <= 0 or not numeric.is_integer():
        raise ValueError(f"{name} must be a positive integer")
    parsed = int(numeric)
    if parsed > 9_007_199_254_740_991:
        raise ValueError(f"{name} must be a positive integer")
    return parsed
