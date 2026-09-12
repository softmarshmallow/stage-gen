"""Capability contracts work without declaring a game or adopting playback rules."""

from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from gnode import ImageReference
from stage_gen.components.effects_art import EffectsArt
from stage_gen.components.effects_art.models import DustAtlasDirection, SpriteDirection
from stage_gen.components.music import MusicTrack, TrackGenerationIntent, music_track_prompt
from stage_gen.components.screen_art import ImagePlate, Rect, ScreenLayout, ScreenPlateRequest
from stage_gen.components.sideview_actor import AssetScale, ResolvedMagnitude, calibrate_subject
from stage_gen.components.sound_effect import SoundEffectRequest
from stage_gen.components.speech import SpeechRequest
from stage_gen.components.ui_art import (
    PANEL_FRAME_LAYOUT,
    AtlasRoleDirection,
    UiArt,
    UiReference,
)
from stage_gen.components.ui_art.nodes import document_roles
from stage_gen.media.codec import encode_png


def test_one_ui_asset_is_an_independent_request() -> None:
    request = UiArt(
        references=[
            UiReference(
                reference_id="style",
                source="references/style.png",
                source_sha256="0" * 64,
                rights_status="unreviewed",
                rights_basis=["Original input owned by the author"],
            )
        ],
        panel_frame=AtlasRoleDirection(
            layout=PANEL_FRAME_LAYOUT,
            alpha_policy="transparent_exterior_opaque_body_v1",
            reference_ids=["style"],
            prompt="A softly painted timber border",
        ),
    )
    assert [role.role for role in document_roles(request)] == ["panel_frame"]
    assert "game_id" not in request.model_dump()
    with pytest.raises(ValidationError, match="at least one"):
        UiArt(references=request.references)


def test_dust_asset_does_not_need_a_gameplay_moment() -> None:
    request = EffectsArt(
        sprite=SpriteDirection(
            dust=DustAtlasDirection(
                layout="fx_dust_atlas_1024x1024_v1",
                alpha_policy="transparent_exterior_v1",
                prompt="Warm clay particles with soft painted edges",
            )
        )
    )
    assert "moments" not in request.model_dump()
    assert request.kind == "effects-art-v1"


def test_single_music_track_needs_no_playlist_or_game_identity() -> None:
    track = MusicTrack(
        track_id="quiet_rain",
        display_name="Quiet rain",
        creative_brief="Sparse soft percussion and a rising wooden flute phrase",
        generation=TrackGenerationIntent(
            intent="generate", instrumental=True, seamless_loop=True, target_duration_seconds=30
        ),
    )
    prompt = music_track_prompt(
        medium="an interactive illustration",
        track_id=track.track_id,
        creative_brief=track.creative_brief,
        generation=track.generation,
    )
    assert "Game ID" not in prompt
    assert "reconnect naturally" in prompt


def test_screen_plate_has_geometry_without_screen_flow() -> None:
    request = ScreenPlateRequest(
        plate=ImagePlate(
            mode="still",
            alpha_policy="fully_opaque_v1",
            reference_ids=["style"],
            prompt="A quiet painted blue horizon",
        ),
        layout=ScreenLayout(
            layout="quiet_plate_v1",
            canvas=(64, 32),
            reserved=(("caption", Rect(8, 20, 48, 8)),),
        ),
        measured_regions=("caption",),
    )
    facts = request.validate(encode_png(Image.new("RGBA", (64, 32), "#26384a")))
    assert facts["canvas"] == {"width": 64, "height": 32}
    with pytest.raises(ValueError, match="bound image"):
        request.image_request(artifact_path=Path("plate.png"), references=())
    bound = ImageReference(url="data:image/png;base64,aW1hZ2U=")
    assert (
        request.image_request(artifact_path=Path("plate.png"), references=(bound,)).size == "64x32"
    )
    with pytest.raises(ValueError, match="unknown reserved"):
        ScreenPlateRequest(
            plate=request.plate, layout=request.layout, measured_regions=("missing",)
        )


def test_asset_scale_uses_a_caller_selected_ruler() -> None:
    scale = AssetScale(target_pixels_per_unit=80.0, minimum=0.1)
    result = calibrate_subject(
        magnitude=ResolvedMagnitude(2.0, "authored"),
        subject_extent_px=320,
        measured_sha256="0" * 64,
        scale=scale,
        subject="tree",
    )
    assert result.source_px_per_unit == 160
    assert result.downscale_ratio == 2
    with pytest.raises(ValidationError):
        AssetScale(target_pixels_per_unit=float("nan"))


def test_audio_asset_requests_exclude_gameplay_response_fields() -> None:
    effect = SoundEffectRequest(
        kind="generated_clip_v1", prompt="A soft wooden tap", duration_seconds=1.0
    )
    speech = SpeechRequest(
        kind="spoken_line_v1", text="The path is clear.", voice_id="narrator", max_seconds=4.0
    )
    for request in (effect, speech):
        assert "gain" not in request.model_dump()
        assert "strength_pitch_multiplier" not in request.model_dump()
        with pytest.raises(ValidationError):
            type(request).model_validate({**request.model_dump(), "strength_pitch_multiplier": 0.5})
