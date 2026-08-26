from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast

import pytest

from stage_gen.config import (
    ConfigError,
    TransparencyMode,
    assert_capabilities,
    load_config,
    parse_transparency_mode,
    transparency_capabilities,
)
from stage_gen.tags import slugify, tag_for, tag_for_transparency_mode


class TagVector(TypedDict):
    name: str
    prompt: str
    transparencyMode: str
    slug: str
    baseTag: str
    tag: str


def _tag_vectors() -> list[TagVector]:
    fixture = Path(__file__).resolve().parents[2] / "contract" / "fixtures" / "tag-vectors.json"
    payload = cast("dict[str, object]", json.loads(fixture.read_text(encoding="utf-8")))
    assert payload.get("schemaVersion") == 1
    vectors = payload.get("vectors")
    assert isinstance(vectors, list)
    return [cast("TagVector", vector) for vector in vectors]


def test_config_defaults_to_native_and_conditionally_requires_fal() -> None:
    config = load_config(env={})
    assert config.out_dir == Path("out")
    assert config.image_model == "openai/gpt-image-2"
    assert config.music_model == "google/lyria-3-pro-preview"
    assert config.transparency_mode == "native"
    assert transparency_capabilities(TransparencyMode.NATIVE) == ("native-image-generation",)
    assert tuple(map(str, transparency_capabilities(TransparencyMode.AI))) == (
        "background-removal",
    )
    assert transparency_capabilities(TransparencyMode.CHROMA) == ()
    with pytest.raises(ConfigError, match="FAL_KEY"):
        assert_capabilities(config, ("background-removal",))


def test_config_validation_never_includes_present_secret() -> None:
    config = load_config(env={"OPENROUTER_API_KEY": "do-not-render"})
    with pytest.raises(ConfigError) as caught:
        assert_capabilities(config, ("background-removal",))
    assert "do-not-render" not in str(caught.value)
    with pytest.raises(ValueError, match="must be native, ai, or chroma"):
        parse_transparency_mode("AI", "--transparency")


@pytest.mark.parametrize("vector", _tag_vectors(), ids=lambda vector: vector["name"])
def test_tags_match_shared_language_neutral_vectors(vector: TagVector) -> None:
    mode = TransparencyMode(vector["transparencyMode"])
    assert slugify(vector["prompt"]) == vector["slug"]
    assert tag_for(vector["prompt"]) == vector["baseTag"]
    assert tag_for_transparency_mode(vector["baseTag"], mode) == vector["tag"]
