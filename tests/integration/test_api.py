from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from stage_gen.capabilities import CapabilityArtifactResult
from stage_gen.config import StageGenConfig
from stage_gen.interfaces.api import MAX_JSON_BODY_BYTES, create_app, resolve_server_binding
from stage_gen.recipes.base import StageContext


class ApiRuntime:
    async def run_recipe_stage(
        self, recipe_id: str, stage_name: str, context: StageContext
    ) -> tuple[str, ...]:
        assert recipe_id == "scrolling-preview"
        path = context.run_dir / f"{stage_name}.txt"
        path.write_text(stage_name, encoding="utf-8")
        return (str(path),)

    async def generate_image(self, **kwargs: object) -> CapabilityArtifactResult:
        output = Path(str(kwargs["output_path"]))
        await asyncio.to_thread(output.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(output.write_bytes, b"png")
        await asyncio.to_thread(Path(f"{output}.meta.json").write_text, "{}")
        return CapabilityArtifactResult(str(output), f"{output}.meta.json", "image/png", 3, 1)

    async def remove_background(self, **_kwargs: object) -> CapabilityArtifactResult:
        raise NotImplementedError

    async def generate_music(self, **_kwargs: object) -> CapabilityArtifactResult:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_api_health_run_status_sse_and_path_limits(tmp_path: Path) -> None:
    config = StageGenConfig(
        out_dir=str(tmp_path), open_router_api_key="offline", transparency_mode="chroma"
    )
    app = create_app(config, runtime=ApiRuntime())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/healthz")).json() == {"ok": True, "service": "stage-gen"}
        start = await client.post(
            "/v1/runs",
            json={"input": {"prompt": "neutral city"}, "transparency_mode": "chroma"},
        )
        assert start.status_code == 202
        run_id = start.json()["id"]
        for _ in range(100):
            status = await client.get(f"/v1/runs/{run_id}")
            if status.json()["status"] == "done":
                break
            await asyncio.sleep(0.01)
        assert status.json()["summary"]["ok"] is True
        assert status.json()["transparency_mode"] == "chroma"
        assert status.json()["summary"]["schema_version"] == 3
        assert status.json()["summary"]["kind"] == "recipe_run_v3"
        assert "transparencyMode" not in status.json()
        assert status.json()["summary"]["run_dir"] == status.json()["tag"]
        record = app.state.stage_gen_runs[run_id]
        assert record.summary is not None
        run_dir = Path(record.summary.run_dir)
        outside = tmp_path / "outside.txt"
        await asyncio.to_thread(outside.write_text, "private", encoding="utf-8")
        await asyncio.to_thread((run_dir / "escape.txt").symlink_to, outside)
        escaped = await client.get(f"/v1/runs/{run_id}/artifacts/escape.txt")
        assert escaped.status_code == 403
        assert escaped.json() == {"error": "forbidden"}
        assert str(outside) not in escaped.text
        events = await client.get(f"/v1/runs/{run_id}/events")
        assert "event: run-status" in events.text
        assert "event: log" in events.text
        oversized = await client.post(
            "/v1/runs",
            content=b"{" + b" " * MAX_JSON_BODY_BYTES + b"}",
            headers={"content-type": "application/json"},
        )
        assert oversized.status_code == 413
        unsafe = await client.post(
            "/v1/capabilities/generate-image",
            json={"prompt": "x", "outputPath": "../escape.png"},
        )
        assert unsafe.status_code == 400


def test_public_binding_requires_explicit_opt_in() -> None:
    assert resolve_server_binding() == ("127.0.0.1", 4317)
    with pytest.raises(ValueError, match="--public"):
        resolve_server_binding(hostname="0.0.0.0")
    assert resolve_server_binding(hostname="0.0.0.0", allow_public=True) == (
        "0.0.0.0",
        4317,
    )


@pytest.mark.asyncio
async def test_api_round_trips_chroma_and_conditionally_requires_fal(tmp_path: Path) -> None:
    app = create_app(
        StageGenConfig(
            out_dir=tmp_path,
            open_router_api_key="synthetic-openrouter",
            transparency_mode="chroma",
        ),
        runtime=ApiRuntime(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        chroma = await client.post(
            "/v1/runs",
            json={"input": {"prompt": "neutral asset"}, "transparency_mode": "chroma"},
        )
        assert chroma.status_code == 202
        assert chroma.json()["transparency_mode"] == "chroma"
        assert chroma.json()["tag"].endswith("-chroma")

        ai = await client.post(
            "/v1/runs",
            json={"input": {"prompt": "neutral asset"}, "transparency_mode": "ai"},
        )
        assert ai.status_code == 400
        assert "FAL_KEY" in ai.text
        assert "synthetic-openrouter" not in ai.text


@pytest.mark.asyncio
async def test_api_rejects_invalid_mode_before_capability_checks(tmp_path: Path) -> None:
    app = create_app(StageGenConfig(out_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/runs",
            json={"input": {"prompt": "neutral asset"}, "transparency_mode": "none"},
        )
    assert response.status_code == 400
    assert response.json() == {"error": "transparency_mode must be ai or chroma"}


@pytest.mark.asyncio
async def test_run_api_rejects_legacy_camel_case_fields(tmp_path: Path) -> None:
    app = create_app(StageGenConfig(out_dir=tmp_path, open_router_api_key="offline"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/runs",
            json={"input": {"prompt": "neutral asset"}, "transparencyMode": "chroma"},
        )

    assert response.status_code == 400
    assert response.json() == {"error": "run request has unexpected fields: 'transparencyMode'"}


@pytest.mark.asyncio
async def test_api_rejects_generate_image_through_symlinked_parent(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    app = create_app(
        StageGenConfig(out_dir=root, open_router_api_key="synthetic"),
        runtime=ApiRuntime(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/capabilities/generate-image",
            json={"prompt": "neutral icon", "outputPath": "link/out.png"},
        )
    assert response.status_code == 400
    assert response.json() == {"error": "outputPath has a symlinked parent"}
    assert not (outside / "out.png").exists()
