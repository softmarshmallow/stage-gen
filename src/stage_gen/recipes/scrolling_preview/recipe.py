"""Public scrolling-preview recipe definition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stage_gen.components.game_contract import load_game_vocabulary
from stage_gen.config import CapabilityName
from stage_gen.image_prompting import load_image_style_resources
from stage_gen.recipes.base import JsonObject, Recipe
from stage_gen.recipes.scrolling_preview.game import (
    game_contract_tag_suffix,
    parse_game_contract_binding,
)
from stage_gen.recipes.scrolling_preview.map_book import (
    assert_map_book_matches_game_and_soundtrack,
    parse_game_map_book_binding,
)
from stage_gen.recipes.scrolling_preview.profile import (
    character_profile_tag_suffix,
    parse_character_profile_binding,
)
from stage_gen.recipes.scrolling_preview.proportion import (
    character_proportion_tag_suffix,
    parse_character_heads_tall,
)
from stage_gen.recipes.scrolling_preview.soundtrack import (
    assert_soundtrack_matches_game,
    parse_game_soundtrack_binding,
)
from stage_gen.recipes.scrolling_preview.stages import STAGES, scrolling_preview_stages
from stage_gen.recipes.scrolling_preview.village import parse_village_opt_in
from stage_gen.tags import tag_for
from stage_gen.theme import parse_theme_handles, theme_digest

_SCROLLING_PREVIEW_INPUT_FIELDS = frozenset(
    {
        "prompt",
        "theme",
        "style_anchor",
        "character_profile",
        "character_heads_tall",
        "game",
        "soundtrack",
        "map_book",
        "village",
        # Parsed by the orchestration boundary and re-inserted into the canonical request.
        "transparency_mode",
    }
)


def parse_scrolling_preview_input(value: object) -> JsonObject:
    if isinstance(value, str):
        prompt = value.strip()
    elif isinstance(value, Mapping):
        unexpected = sorted(
            repr(key) for key in value if key not in _SCROLLING_PREVIEW_INPUT_FIELDS
        )
        if unexpected:
            raise ValueError(
                "scrolling-preview input has unexpected fields: " + ", ".join(unexpected)
            )
        raw_prompt = value.get("prompt")
        prompt = str(raw_prompt if raw_prompt is not None else "").strip()
    else:
        prompt = ""
    if not prompt:
        raise ValueError("scrolling-preview input requires a non-empty prompt")
    parsed: JsonObject = {"prompt": prompt}
    if isinstance(value, Mapping) and "theme" in value:
        parsed["theme"] = parse_theme_handles(value["theme"]).model_dump(mode="json")
    if isinstance(value, Mapping) and "style_anchor" in value:
        parsed["style_anchor"] = _parse_style_anchor_opt_in(value["style_anchor"])
    if isinstance(value, Mapping) and "character_profile" in value:
        parsed["character_profile"] = parse_character_profile_binding(value["character_profile"])
    if isinstance(value, Mapping) and "character_heads_tall" in value:
        parsed["character_heads_tall"] = parse_character_heads_tall(value["character_heads_tall"])
    if isinstance(value, Mapping) and "game" in value:
        parsed["game"] = parse_game_contract_binding(value["game"])
    if isinstance(value, Mapping) and "soundtrack" in value:
        parsed["soundtrack"] = parse_game_soundtrack_binding(value["soundtrack"])
    if isinstance(value, Mapping) and "map_book" in value:
        parsed["map_book"] = parse_game_map_book_binding(value["map_book"])
    if isinstance(value, Mapping) and "village" in value:
        parsed["village"] = parse_village_opt_in(value["village"])
    if "game" in parsed and "character_heads_tall" in parsed:
        # Refused rather than resolved by precedence. Both state the run's build, and a request
        # carrying two answers has not decided which it means: silently preferring one would
        # generate artwork the request does not describe, and the world's answer is a *table*
        # while the flat opt-in is a single number, so they are not even the same kind of claim.
        raise ValueError(
            "scrolling-preview accepts game or character_heads_tall, not both; a world "
            "contract states the build for the whole cast in [proportion]"
        )
    if "soundtrack" in parsed:
        if "game" not in parsed:
            raise ValueError("scrolling-preview soundtrack requires a game contract binding")
        if "map_book" not in parsed:
            raise ValueError("scrolling-preview soundtrack requires a map_book binding")
        assert_soundtrack_matches_game(parsed["soundtrack"], parsed["game"])
    if "map_book" in parsed:
        if "game" not in parsed or "soundtrack" not in parsed:
            raise ValueError("scrolling-preview map_book requires game and soundtrack bindings")
        assert_map_book_matches_game_and_soundtrack(
            parsed["map_book"], parsed["game"], parsed["soundtrack"]
        )
    return parsed


def _parse_style_anchor_opt_in(value: object) -> JsonObject:
    expected: JsonObject = {
        "schema_version": 1,
        "kind": "automatic_style_anchor_v1",
    }
    if not isinstance(value, Mapping) or dict(value) != expected:
        raise ValueError(
            "scrolling-preview style_anchor must equal "
            '{"schema_version":1,"kind":"automatic_style_anchor_v1"}'
        )
    return expected


def scrolling_preview_tag(input_value: Mapping[str, Any]) -> str:
    """Separate run directories by every input that changes an existing artifact's bytes.

    `village`, `soundtrack`, and `map_book` are deliberately absent from this list. Every
    other one re-directs artwork the run already produces - a theme rewrites the concept prompt,
    a style anchor rewrites all of them, a profile and a proportion rewrite the player, and a
    game contract rewrites every prompt in the run and the build of its whole cast - so
    sharing a directory would mean serving cached bytes generated under different direction. The
    village only ever *adds* visual artifacts, while soundtrack and map-book artifacts own
    separate namespaces whose caches are bound to their own digests. Giving any of them a suffix
    would fork the run directory and regenerate an entire world to gain independent files,
    leaving the same artwork in two directories.
    """

    prompt_tag = tag_for(str(input_value["prompt"]))
    suffixes: list[str] = []
    if "theme" in input_value:
        digest = theme_digest(parse_theme_handles(input_value["theme"]))
        suffixes.append(f"theme-{digest}")
    if "style_anchor" in input_value:
        resources = load_image_style_resources()
        suffixes.append(f"style-v1-{resources.resource_sha256[:8]}-{resources.compiler_sha256[:8]}")
    if "character_profile" in input_value:
        suffixes.append(character_profile_tag_suffix(input_value["character_profile"]))
    if "character_heads_tall" in input_value:
        suffixes.append(
            character_proportion_tag_suffix(
                parse_character_heads_tall(input_value["character_heads_tall"])
            )
        )
    if "game" in input_value:
        suffixes.append(
            game_contract_tag_suffix(
                input_value["game"],
                vocabulary_sha256=load_game_vocabulary().sha256,
            )
        )
    return "-".join((prompt_tag, *suffixes))


scrolling_preview_recipe = Recipe(
    id="scrolling-preview",
    description="Reference 2D scrolling preview asset pipeline",
    required_capabilities=(
        CapabilityName.STRUCTURED_GENERATION,
        CapabilityName.IMAGE_GENERATION,
    ),
    parse_input=parse_scrolling_preview_input,
    tag_for=scrolling_preview_tag,
    stages=STAGES,
    stage_resolver=scrolling_preview_stages,
)
