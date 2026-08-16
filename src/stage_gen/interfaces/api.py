"""FastAPI-compatible local HTTP/SSE interface."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from stage_gen.capabilities import HeadlessRuntime, generate_image_artifact
from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.orchestration.service import (
    GenerateRequest,
    PreparedGenerateRequest,
    generate_prepared,
    prepare_generate_request,
)
from stage_gen.recipes.base import RunSummary
from stage_gen.recipes.registry import list_recipes
from stage_gen.reliability import (
    CancellationError,
    CancellationToken,
    assert_safe_path_segment,
    resolve_relative_path_within_root,
    resolve_writable_path_within_root,
)

MAX_JSON_BODY_BYTES = 64 * 1024
RunState = Literal["queued", "running", "done", "failed", "cancelled"]
PreparedExecutor = Callable[[PreparedGenerateRequest, StageGenConfig], Awaitable[RunSummary]]


@dataclass(slots=True)
class RunRecord:
    id: str
    recipe: str
    tag: str
    transparency_mode: TransparencyMode
    status: RunState = "queued"
    events: list[str] = field(default_factory=list)
    summary: RunSummary | None = None
    error: str | None = None
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    subscribers: set[asyncio.Queue[str | None]] = field(default_factory=set)
    task: asyncio.Task[None] | None = None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "recipe": self.recipe,
            "tag": self.tag,
            "transparencyMode": self.transparency_mode,
            "status": self.status,
            "error": self.error,
            "summary": self.summary.to_dict() if self.summary is not None else None,
        }


class RequestBodyError(ValueError):
    def __init__(self, message: str, status: int) -> None:
        self.status = status
        super().__init__(message)


def create_app(
    config: StageGenConfig,
    *,
    runtime: HeadlessRuntime | None = None,
    execute_prepared: Callable[..., Awaitable[RunSummary]] = generate_prepared,
) -> FastAPI:
    app = FastAPI(title="stage-gen", docs_url=None, redoc_url=None)
    runs: dict[str, RunRecord] = {}
    app.state.stage_gen_runs = runs

    def emit(record: RunRecord, event: str, data: object) -> None:
        frame = f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"
        record.events.append(frame)
        for subscriber in tuple(record.subscribers):
            subscriber.put_nowait(frame)

    def finish(record: RunRecord) -> None:
        for subscriber in tuple(record.subscribers):
            subscriber.put_nowait(None)
        record.subscribers.clear()

    async def execute(record: RunRecord, prepared: PreparedGenerateRequest) -> None:
        if record.cancellation.cancelled:
            record.status = "cancelled"
            record.error = record.cancellation.reason
            emit(record, "run-status", {"status": record.status, "error": record.error})
            finish(record)
            return
        record.status = "running"
        emit(record, "run-status", {"status": record.status})
        try:
            record.summary = await execute_prepared(
                prepared,
                config,
                log=lambda line: emit(record, "log", {"line": line}),
                runtime=runtime,
                cancellation=record.cancellation,
            )
            if record.cancellation.cancelled:
                record.status = "cancelled"
                record.error = record.cancellation.reason
            elif record.summary.ok:
                record.status = "done"
            else:
                record.status = "failed"
                record.error = record.summary.failed_stage
        except (CancellationError, asyncio.CancelledError):
            record.status = "cancelled"
            record.error = record.cancellation.reason
        except Exception as error:
            record.status = "failed"
            record.error = str(error)
        emit(
            record,
            "run-status",
            {"status": record.status, "error": record.error},
        )
        finish(record)

    @app.get("/healthz")
    async def health() -> dict[str, object]:
        return {"ok": True, "service": "stage-gen"}

    @app.get("/v1/recipes")
    async def recipes() -> dict[str, object]:
        return {"recipes": list_recipes()}

    @app.get("/v1/capabilities")
    async def capabilities() -> dict[str, object]:
        return {"capabilities": ["generate-image", "remove-background", "generate-music"]}

    @app.post("/v1/runs")
    async def start_run(request: Request) -> JSONResponse:
        try:
            body = await _read_json_body(request)
        except RequestBodyError as error:
            return _json_error(str(error), error.status)
        if not isinstance(body, dict):
            return _json_error("request body must be an object", 400)
        try:
            prepared = prepare_generate_request(
                GenerateRequest(
                    recipe=str(body.get("recipe", "scrolling-preview")),
                    input=body.get("input"),
                    transparency_mode=body.get("transparencyMode"),
                ),
                config,
            )
            tag = assert_safe_path_segment(prepared.tag, "recipe tag")
        except Exception as error:  # validation error shape is intentionally flat
            return _json_error(str(error), 400)
        run_id = f"{prepared.recipe.id}--{tag}"
        existing = runs.get(run_id)
        if existing is not None and existing.status in {"queued", "running"}:
            return JSONResponse(existing.public(), status_code=200)
        record = RunRecord(
            id=run_id,
            recipe=prepared.recipe.id,
            tag=tag,
            transparency_mode=prepared.input["transparencyMode"],
        )
        runs[run_id] = record
        record.task = asyncio.create_task(execute(record, prepared))
        return JSONResponse(record.public(), status_code=202)

    @app.get("/v1/runs/{run_id}")
    async def run_status(run_id: str) -> JSONResponse:
        record = runs.get(run_id)
        if record is None:
            return _json_error("run not found", 404)
        return JSONResponse(record.public())

    @app.post("/v1/runs/{run_id}/cancel")
    async def cancel_run(run_id: str) -> JSONResponse:
        record = runs.get(run_id)
        if record is None:
            return _json_error("run not found", 404)
        if record.status in {"queued", "running"}:
            record.cancellation.cancel("run cancelled by request")
            if record.task is not None:
                record.task.cancel()
        return JSONResponse(record.public(), status_code=202)

    @app.get("/v1/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request) -> Response:
        record = runs.get(run_id)
        if record is None:
            return _json_error("run not found", 404)

        async def stream() -> AsyncIterator[str]:
            for historical_frame in record.events:
                yield historical_frame
            if record.status in {"done", "failed", "cancelled"}:
                return
            queue: asyncio.Queue[str | None] = asyncio.Queue()
            record.subscribers.add(queue)
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        queued_frame = await asyncio.wait_for(queue.get(), timeout=1.0)
                    except TimeoutError:
                        continue
                    if queued_frame is None:
                        break
                    yield queued_frame
            finally:
                record.subscribers.discard(queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform"},
        )

    @app.get("/v1/runs/{run_id}/artifacts/{name}")
    async def artifact(run_id: str, name: str) -> Response:
        record = runs.get(run_id)
        if record is None:
            return _json_error("run not found", 404)
        if record.summary is None:
            return _json_error("run has no artifacts", 409)
        try:
            safe_name = assert_safe_path_segment(name, "artifact name")
            lexical = resolve_relative_path_within_root(
                record.summary.run_dir, safe_name, "artifact name"
            )
            root, resolved = await asyncio.to_thread(
                _resolve_artifact_path, Path(record.summary.run_dir), lexical
            )
        except FileNotFoundError:
            return _json_error("artifact not found", 404)
        except ValueError as error:
            return _json_error(str(error), 400)
        try:
            resolved.relative_to(root)
        except ValueError:
            return _json_error("forbidden", 403)
        if not resolved.is_file():
            return _json_error("artifact not found", 404)
        return FileResponse(resolved)

    @app.post("/v1/capabilities/generate-image")
    async def generate_image(request: Request) -> JSONResponse:
        try:
            body = await _read_json_body(request)
        except RequestBodyError as error:
            return _json_error(str(error), error.status)
        if not isinstance(body, dict):
            return _json_error("request body must be an object", 400)
        prompt = body.get("prompt", "")
        output_path = body.get("outputPath", "")
        aspect_ratio = body.get("aspectRatio", "1:1")
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or not isinstance(output_path, str)
            or not output_path.strip()
        ):
            return _json_error("prompt and outputPath are required", 400)
        if not isinstance(aspect_ratio, str) or not (
            aspect_ratio == "auto" or _is_positive_aspect_ratio(aspect_ratio)
        ):
            return _json_error("aspectRatio must be auto or positive <width>:<height>", 400)
        try:
            output = resolve_writable_path_within_root(
                config.out_dir, output_path.strip(), "outputPath"
            )
        except ValueError as error:
            return _json_error(str(error), 400)
        try:
            result = await generate_image_artifact(
                prompt=prompt.strip(),
                output_path=str(output),
                aspect_ratio=aspect_ratio,
                config=config,
                runtime=runtime,
            )
        except Exception as error:  # provider failures map to gateway failure
            return _json_error(str(error), 502)
        return JSONResponse(result.to_dict(), status_code=201)

    return app


async def _read_json_body(request: Request) -> object:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = 0
        if declared > MAX_JSON_BODY_BYTES:
            raise RequestBodyError(f"request body exceeds {MAX_JSON_BODY_BYTES} bytes", 413)
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_JSON_BODY_BYTES:
            raise RequestBodyError(f"request body exceeds {MAX_JSON_BODY_BYTES} bytes", 413)
        chunks.append(chunk)
    if size == 0:
        raise RequestBodyError("invalid JSON", 400)
    try:
        return json.loads(b"".join(chunks).decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RequestBodyError("invalid JSON", 400) from error


def resolve_server_binding(
    *, hostname: str | None = None, port: int = 4317, allow_public: bool = False
) -> tuple[str, int]:
    host = hostname.strip() if hostname is not None and hostname.strip() else "127.0.0.1"
    if port < 1 or port > 65535:
        raise ValueError("--port must be an integer between 1 and 65535")
    if host not in {"127.0.0.1", "::1", "localhost"} and not allow_public:
        raise ValueError("non-loopback --host requires the explicit --public flag")
    return host, port


def _json_error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def _is_positive_aspect_ratio(value: str) -> bool:
    parts = value.split(":")
    return len(parts) == 2 and all(
        part.isdigit() and int(part) > 0 and not part.startswith("0") for part in parts
    )


def _resolve_artifact_path(root: Path, lexical: Path) -> tuple[Path, Path]:
    return root.resolve(strict=True), lexical.resolve(strict=True)
