"""Collect an already successful Tripo task into a new, unreviewed recovery bundle.

This utility never regenerates, changes the source operation, or reconciles its
budget liability. The CLI needs explicit --live; completed bundles reuse offline.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import os
import tempfile
from collections.abc import Collection
from pathlib import Path
from typing import Any

import httpx

from gnode import BindingTable, ModelRef, RetryPolicy
from stage_gen.components.character_3d.identity import (
    COLLECT_RECOVERY_IDENTITY as IDENTITY,
)
from stage_gen.components.character_3d.io import (
    confined,
    digest,
    read_json,
    write_bytes,
    write_json,
)
from stage_gen.components.character_3d.provider_contracts import (
    OperationStore,
    identifier,
    positive_amount,
    validate_plan,
    verify_result,
)
from stage_gen.providers.character_3d.tripo import API_ROOT, TripoParts

JsonObject = dict[str, Any]


def _inventory(root: Path, *, exclude: Collection[str] = ()) -> list[JsonObject]:
    records = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ValueError("Recovery evidence must not contain symlinks")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Recovery evidence must contain regular files only")
        if relative not in exclude:
            records.append({"path": relative, "sha256": digest(path), "bytes": path.stat().st_size})
    return records


def _directory(root: Path, path: Path, *, exists: bool) -> Path:
    ref = path.relative_to(root).as_posix() if path.is_absolute() else path.as_posix()
    target = confined(root, ref, must_exist=False)
    if exists and (not target.is_dir()):
        raise ValueError("Source operation must be an existing directory")
    return target


def _input_root(path: Path) -> Path:
    path = path.absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Input root must not contain symlinks")
    return path.resolve(strict=True)


def _source(
    input_root: Path, source: Path, bindings: BindingTable | None
) -> tuple[JsonObject, str, JsonObject]:
    plan = read_json(confined(source, "plan.json"))
    state = read_json(confined(source, "state.json"))
    validate_plan(plan, input_root, bindings)
    if plan["operation"] != "part_mesh" or ModelRef.parse(plan["route"]).provider != "tripo":
        raise ValueError("Collection recovery requires an existing Tripo mesh plan")
    task_id = identifier(state.get("task_id"))
    reservation = state.get("reservation")
    if (
        state.get("plan_sha256") != plan["plan_sha256"]
        or state.get("status") != "success"
        or type(state.get("paid_submissions")) is not int
        or (state["paid_submissions"] != 1)
        or (not isinstance(reservation, dict))
        or (set(reservation) != {"reservation_id", "plan_sha256", "amount_usd"})
        or (reservation["plan_sha256"] != plan["plan_sha256"])
        or (positive_amount(reservation["amount_usd"]) < plan["reservation_usd"])
    ):
        raise ValueError("Recovery needs one successful saved task and its original reservation")
    identifier(reservation["reservation_id"])
    if (source / "result.json").exists():
        raise ValueError("Source already has a result; validate and reuse it instead")
    return (
        plan,
        task_id,
        {
            "operation_path": source.relative_to(input_root).as_posix(),
            "files": _inventory(source),
            "task_id": task_id,
            "plan_sha256": plan["plan_sha256"],
            "paid_submissions": 1,
        },
    )


class GetOnlyTransport(httpx.AsyncBaseTransport):
    """Refuse paid methods and credential forwarding before the underlying transport."""

    def __init__(self, transport: httpx.AsyncBaseTransport, task_id: str) -> None:
        self.transport = transport
        self.task_url = httpx.URL(API_ROOT + "/tasks/" + identifier(task_id))
        self.task_queries = 0
        self.download_requests = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            raise ValueError("Collection recovery permits GET only")
        if request.url == self.task_url:
            self.task_queries += 1
        else:
            if "authorization" in request.headers or request.url.host == self.task_url.host:
                raise ValueError("Recovery download must not carry API authorization")
            self.download_requests += 1
        return await self.transport.handle_async_request(request)

    async def aclose(self) -> None:
        await self.transport.aclose()


def _existing(output: Path, source_evidence: JsonObject, plan: JsonObject) -> JsonObject:
    receipt = read_json(confined(output, "recovery.json"))
    if receipt.get("source") != source_evidence:
        raise ValueError("Recovery source evidence changed")
    if receipt.get("files") != _inventory(output, exclude=("recovery.json",)):
        raise ValueError("Recovered output changed or contains unexpected files")
    result = verify_result(OperationStore(output / "operations", plan["operation_id"]), plan)
    if (
        result is None
        or result.get("task_id") != source_evidence["task_id"]
        or result.get("status") != "raw_parts_collected"
        or (not result.get("artifacts"))
    ):
        raise ValueError("Recovery has no validated collected result")
    return receipt


async def recover_collection(
    *,
    input_root: Path,
    source_operation: Path,
    output_root: Path,
    api_key: str | None = None,
    live: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    bindings: BindingTable | None = None,
) -> JsonObject:
    """One collect attempt; retries belong to the adapter, never to generation."""
    if live is not True:
        raise ValueError("Collection recovery requires explicit live=True")
    input_root = _input_root(input_root)
    source = _directory(input_root, source_operation, exists=True)
    output = _directory(input_root, output_root, exists=False)
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Recovery output must be separate from its source operation")
    plan, task_id, source_evidence = _source(input_root, source, bindings)
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = confined(output.parent, "." + output.name + ".recovery.lock", must_exist=False)
    with lock_path.open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Collection recovery is already running") from None
        try:
            if output.exists():
                return _existing(output, source_evidence, plan)
            if not api_key or not api_key.strip():
                raise ValueError("A Tripo key is required to collect the saved task")
            with tempfile.TemporaryDirectory(prefix=".collect-", dir=output.parent) as temporary:
                staging = Path(temporary)
                operations = staging / "operations"
                operations.mkdir()
                store = OperationStore(operations, plan["operation_id"])
                for name in ("plan.json", "state.json"):
                    write_bytes(store.path / name, confined(source, name).read_bytes())
                guard = GetOnlyTransport(transport or httpx.AsyncHTTPTransport(retries=0), task_id)
                async with httpx.AsyncClient(
                    transport=guard, timeout=180, follow_redirects=False
                ) as client:
                    adapter = TripoParts(
                        api_key=api_key,
                        input_root=input_root,
                        output_root=operations,
                        client=client,
                        retry_policy=retry_policy,
                        bindings=bindings,
                        component=IDENTITY,
                        tool=IDENTITY,
                    )
                    result = await adapter.collect(plan, live=True)
                if result.get("status") != "raw_parts_collected" or not result.get("artifacts"):
                    raise ValueError("Saved task did not return a collectible completed result")
                if _source(input_root, source, bindings)[2] != source_evidence:
                    raise ValueError("Source operation changed during collection")
                receipt = {
                    "schema_version": 1,
                    "kind": "tripo_collection_recovery",
                    "source": source_evidence,
                    "semantic_status": "unreviewed",
                    "local_import_required": True,
                    "regeneration_performed": False,
                    "liability_reconciled": False,
                    "source_operation_modified": False,
                    "request_counts": {
                        "task_get": guard.task_queries,
                        "download_get": guard.download_requests,
                        "paid_post": 0,
                    },
                    "result_path": f"operations/{plan['operation_id']}/result.json",
                    "software": [
                        {"name": "collect_recovery.py", "sha256": digest(Path(__file__))},
                        {
                            "name": "tripo.py",
                            "sha256": digest(Path(__file__).with_name("tripo.py")),
                        },
                    ],
                    "files": _inventory(staging),
                }
                write_json(staging / "recovery.json", receipt)
                if output.exists():
                    raise ValueError(
                        "Recovery output appeared during collection; overwrite refused"
                    )
                os.rename(staging, output)
                return _existing(output, source_evidence, plan)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--source-operation", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dotenv", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; this command never submits a generation")
    from stage_gen.provider_env import load_provider_dotenv

    values = load_provider_dotenv(args.dotenv) if args.dotenv else {}
    receipt = asyncio.run(
        recover_collection(
            input_root=args.input_root,
            source_operation=args.source_operation,
            output_root=args.output_root,
            api_key=os.environ.get("TRIPO_API_KEY") or values.get("TRIPO_API_KEY"),
            live=True,
        )
    )
    print("Recovered unreviewed mesh; no regeneration or liability reconciliation.")
    print("Paid submissions:", receipt["request_counts"]["paid_post"])


if __name__ == "__main__":
    main()
