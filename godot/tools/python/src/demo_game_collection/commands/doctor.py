"""Private collection adapter for doctor."""

from __future__ import annotations

import argparse
import json
from typing import Literal, TextIO

from gnode import ImageRouteRequirementsV1, RouteResolutionError
from stage_gen.config import (
    StageGenConfig,
    TransparencyMode,
    load_config,
    parse_transparency_mode,
)
from stage_gen.model_routes import (
    OPENAI_SUNBURST_MODEL,
    OPENROUTER_SUNBURST_MODEL,
    SUNBURST_PRODUCT_ID,
    image_policy_id_for,
    resolve_configured_image_route,
)


def create_doctor_report(
    config: StageGenConfig, requested_mode: TransparencyMode | None = None
) -> dict[str, object]:
    mode = requested_mode or config.transparency_mode
    background: Literal["opaque", "transparent"] = (
        "transparent" if mode is TransparencyMode.NATIVE else "opaque"
    )
    image_requirements = ImageRouteRequirementsV1(
        operation_variant="generation",
        background=background,
        output_format="png",
        size="1024x1024",
        reference_count=0,
    )
    image_policy_id = image_policy_id_for(image_requirements)
    try:
        image_binding = resolve_configured_image_route(
            config,
            image_requirements,
            policy_id=image_policy_id,
        )
    except RouteResolutionError:
        image_binding = None
    requires_background = mode is TransparencyMode.AI
    image_route_provider = image_binding.route.model.provider if image_binding else None
    image_provider_ready = bool(
        image_binding
        and {
            "openai": config.openai_api_key,
            "fal": config.fal_key,
            "openrouter": config.open_router_api_key,
        }[image_binding.route.model.provider]
    )
    ready = bool(
        config.open_router_api_key
        and image_provider_ready
        and (not requires_background or config.fal_key)
    )
    return {
        "ok": ready,
        "transparency_mode": mode,
        "requirements": {
            "image_policy_id": image_policy_id,
            "image_route_id": image_binding.route.route_id if image_binding else None,
            "image_route_provider": image_route_provider,
            "image_route_supported": image_binding is not None,
            "openrouter": True,
            "background_removal": requires_background,
        },
        "capabilities": {
            "openai": bool(config.openai_api_key),
            "openrouter": bool(config.open_router_api_key),
            "fal": bool(config.fal_key),
            "elevenlabs": bool(config.elevenlabs_api_key),
        },
        "models": {
            "image_product": SUNBURST_PRODUCT_ID,
            "openai_image_assertion": config.openai_image_model or OPENAI_SUNBURST_MODEL,
            "openrouter_image_assertion": config.image_model or OPENROUTER_SUNBURST_MODEL,
            "text": config.text_model,
            "music": config.music_model,
            "sound_effect": config.sound_effect_model,
            "speech": config.speech_model,
            "background_removal": config.background_removal_model,
        },
        "out_dir": str(config.out_dir),
    }


def dispatch(args: argparse.Namespace, *, stdout: TextIO) -> int:
    config = load_config()
    mode = (
        parse_transparency_mode(args.transparency, "--transparency")
        if args.transparency is not None
        else None
    )
    report = create_doctor_report(config, mode)
    if args.json_output:
        stdout.write(f"{json.dumps(report, separators=(',', ':'))}\n")
    else:
        requirements = report["requirements"]
        capabilities = report["capabilities"]
        assert isinstance(requirements, dict) and isinstance(capabilities, dict)
        fal = (
            ("configured" if capabilities["fal"] else "missing")
            if requirements["background_removal"] or requirements["image_route_provider"] == "fal"
            else "not-required"
        )
        stdout.write(
            f"demo-games: {'ready' if report['ok'] else 'incomplete'}; "
            f"transparency={report['transparency_mode']}; "
            f"image-policy={requirements['image_policy_id']}; "
            f"image-provider={requirements['image_route_provider']}; "
            f"openrouter={'configured' if capabilities['openrouter'] else 'missing'}; "
            f"fal={fal}\n"
        )
    return 0 if report["ok"] else 2
