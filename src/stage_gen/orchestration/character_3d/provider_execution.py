"""Durable rig dispatch and collection, injected into the character recipe."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from gnode import BindingTable, SoftwareIdentity
from stage_gen.components.character_3d.identity import IDENTITY
from stage_gen.components.character_3d.io import (
    canonical_digest,
    confined,
    digest,
    read_json,
    write_bytes,
    write_json,
)
from stage_gen.components.character_3d.provider_contracts import (
    OperationStore,
    identifier,
)
from stage_gen.providers.character_3d.rig import (
    TripoRig,
    plan_rig,
    rig_cost,
    validate_rig_plan,
    verify_rig_result,
)

if TYPE_CHECKING:
    from stage_gen.orchestration.character_3d.upstream import ProviderRun
JsonObject = dict[str, Any]


class RigProvider(Protocol):
    async def submit_check(
        self, plan: JsonObject, *, reservation: JsonObject, live: bool = False
    ) -> JsonObject: ...

    async def collect_check(self, plan: JsonObject, *, live: bool = False) -> JsonObject: ...

    async def submit(
        self, plan: JsonObject, *, reservation: JsonObject, live: bool = False
    ) -> JsonObject: ...

    async def collect(self, plan: JsonObject, *, live: bool = False) -> JsonObject: ...

    async def aclose(self) -> None: ...


class RigProviderFactory(Protocol):
    def __call__(
        self,
        *,
        api_key: str,
        input_root: Path,
        output_root: Path,
        component: SoftwareIdentity,
        tool: SoftwareIdentity,
        bindings: BindingTable | None,
    ) -> RigProvider: ...


class ProviderRigExecutor:
    def __init__(
        self,
        run: ProviderRun,
        *,
        bindings: BindingTable | None = None,
        provider_factory: RigProviderFactory = TripoRig,
    ) -> None:
        self.run = run
        self.bindings = bindings if bindings is not None else run.upstream_bindings()
        self.provider_factory = provider_factory
        self.root = run.run_root / "upstream" / "rig_operations"
        self.root.mkdir(parents=True, exist_ok=True)
        self.submitted_root = self.root / "submitted"
        self.collected_root = self.root / "collected"
        self.submitted_root.mkdir(exist_ok=True)
        self.collected_root.mkdir(exist_ok=True)

    def plan(self, source: JsonObject, attempt: int) -> JsonObject:
        return plan_rig(
            {
                "schema_version": 1,
                "operation_id": f"body_rig_{attempt:02d}",
                "operation": "body_rig",
                "prompt": (
                    "Bind the admitted complete character with provider bones and skin weights."
                ),
                "source": {"kind": "local_mesh", **source},
                "params": {"rig_type": "biped", "spec": "mixamo", "out_format": "glb"},
                "rights_basis": self.run.experiment.get("brief", {}).get(
                    "rights_basis", "Original character generated for this authorized local study."
                ),
                "reservation_usd": float(
                    Decimal(str(self.run.experiment["rigging"]["reservation_usd"]))
                ),
                "allow_negative_check": True,
            },
            input_root=self.run.input_root,
            bindings=self.bindings,
        )

    def provider(self, *, output_root: Path) -> RigProvider:
        if self.run.live is not True:
            raise ValueError("Rig dispatch requires explicit live execution")
        return self.provider_factory(
            api_key=self.run.provider_key("TRIPO_API_KEY"),
            input_root=self.run.input_root,
            output_root=output_root,
            component=IDENTITY,
            tool=IDENTITY,
            bindings=self.bindings,
        )

    async def submit(self, source: JsonObject, attempt: int) -> JsonObject:
        plan = self.plan(source, attempt)
        account = self.run.require_run_budget()
        allocation = account.reserve(
            plan["operation_id"], plan["plan_sha256"], str(plan["reservation_usd"])
        )
        reservation = {
            "reservation_id": plan["operation_id"],
            "plan_sha256": plan["plan_sha256"],
            "amount_usd": float(plan["reservation_usd"]),
        }
        if allocation.get("status") == "settled":
            raise ValueError("Terminal rig reservation cannot authorize a new submission")
        provider = self.provider(output_root=self.submitted_root)
        try:
            if not allocation["dispatch_started"]:
                account.mark_started(plan["operation_id"], plan["plan_sha256"])
            await provider.submit_check(plan, reservation=reservation, live=True)
            while True:
                check = await provider.collect_check(plan, live=True)
                if check["status"] == "riggability_checked":
                    break
                if check["status"] not in {"queued", "running", "submitted"}:
                    account.settle(
                        plan["operation_id"],
                        plan["plan_sha256"],
                        known_actual_usd="0",
                        unresolved_liability_usd=str(plan["reservation_usd"]),
                        outcome="interrupted",
                    )
                    raise ValueError("Riggability check terminated: " + check["status"])
                await asyncio.sleep(self.run.experiment["rigging"]["poll_interval_seconds"])
            state = await provider.submit(plan, reservation=reservation, live=True)
            store = OperationStore(self.submitted_root, plan["operation_id"])
            with store.lock():
                if store.read("state.json") != state or store.read("plan.json") != plan:
                    raise ValueError("Rig submission changed before its snapshot")
                files = self._inventory(store.path)
            return {
                "status": "provider_rig_submitted",
                "plan": plan,
                "task_id": state["task_id"],
                "check": check,
                "source": source,
                "submission_snapshot": {
                    "path": store.path.relative_to(self.run.input_root).as_posix(),
                    "files": files,
                    "sha256": canonical_digest(files),
                },
            }
        finally:
            await provider.aclose()

    @staticmethod
    def _inventory(root: Path) -> list[JsonObject]:
        records = []
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("Rig submission snapshot contains a symlink")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError("Rig submission snapshot contains a nonregular file")
            records.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": digest(path),
                    "bytes": path.stat().st_size,
                }
            )
        return records

    def _collection_store(self, receipt: JsonObject) -> OperationStore:
        """Copy the immutable dispatch snapshot into this collection stage's space.

        Prior-stage files are never opened for mutation. The new operation keeps
        the same provider task/plan IDs and has no submit path in this method.
        """
        plan = receipt["plan"]
        validate_rig_plan(plan, input_root=self.run.input_root, bindings=self.bindings)
        identifier(receipt["task_id"])
        snapshot = receipt.get("submission_snapshot", {})
        expected_path = (
            (self.submitted_root / plan["operation_id"]).relative_to(self.run.input_root).as_posix()
        )
        if (
            receipt.get("status") != "provider_rig_submitted"
            or snapshot.get("path") != expected_path
            or snapshot.get("sha256") != canonical_digest(snapshot.get("files"))
        ):
            raise ValueError("Collection needs a committed submission snapshot")
        source = confined(self.run.input_root, snapshot["path"], must_exist=False)
        if not source.is_dir() or self._inventory(source) != snapshot["files"]:
            raise ValueError("Committed rig submission snapshot changed")
        source_state = read_json(confined(source, "state.json"))
        if (
            read_json(confined(source, "plan.json")) != plan
            or source_state.get("task_id") != receipt["task_id"]
            or source_state.get("plan_sha256") != plan["plan_sha256"]
            or (source_state.get("status") != "submitted")
            or (type(source_state.get("paid_submissions")) is not int)
            or (source_state["paid_submissions"] != 1)
            or (read_json(confined(source, "check-result.json")) != receipt["check"])
        ):
            raise ValueError("Snapshot does not identify the exact submitted rig task")
        target = confined(self.collected_root, plan["operation_id"], must_exist=False)
        lock_path = confined(
            self.collected_root, "." + plan["operation_id"] + ".seed.lock", must_exist=False
        )
        seed = {
            "schema_version": 1,
            "plan_sha256": plan["plan_sha256"],
            "task_id": receipt["task_id"],
            "submission_snapshot": snapshot,
        }
        with lock_path.open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Rig collection seeding is already active") from None
            try:
                if target.exists():
                    if read_json(confined(target, "submission-snapshot.json")) != seed:
                        raise ValueError("Collection directory belongs to another submitted task")
                else:
                    with tempfile.TemporaryDirectory(
                        prefix=".collect-seed-", dir=self.collected_root
                    ) as temporary:
                        staging = Path(temporary)
                        for item in snapshot["files"]:
                            original = confined(source, item["path"])
                            destination = confined(staging, item["path"], must_exist=False)
                            data = original.read_bytes()
                            if (
                                hashlib.sha256(data).hexdigest() != item["sha256"]
                                or len(data) != item["bytes"]
                            ):
                                raise ValueError("Submission changed while seeding collection")
                            write_bytes(destination, data)
                        write_json(staging / "submission-snapshot.json", seed)
                        if self._inventory(source) != snapshot["files"]:
                            raise ValueError("Submission changed during collection seeding")
                        os.rename(staging, target)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        return OperationStore(self.collected_root, plan["operation_id"])

    async def collect(self, receipt: JsonObject) -> JsonObject:
        plan = receipt["plan"]
        store = self._collection_store(receipt)
        with store.lock():
            state = store.read("state.json")
            if state is None or state.get("task_id") != receipt["task_id"]:
                raise ValueError("Rig collection requires the exact committed provider task")
            result = verify_rig_result(store, plan)
        if result is None:
            provider = self.provider(output_root=self.collected_root)
            try:
                while True:
                    result = await provider.collect(plan, live=True)
                    if result["status"] == "raw_rig_collected":
                        break
                    if result["status"] not in {"queued", "running", "submitted"}:
                        self.run.require_run_budget().settle(
                            plan["operation_id"],
                            plan["plan_sha256"],
                            known_actual_usd="0",
                            unresolved_liability_usd=str(plan["reservation_usd"]),
                            outcome="interrupted",
                        )
                        raise ValueError("Provider rig terminated: " + result["status"])
                    await asyncio.sleep(self.run.experiment["rigging"]["poll_interval_seconds"])
            finally:
                await provider.aclose()
        with store.lock():
            if verify_rig_result(store, plan) != result:
                raise ValueError("Collected rig differs from immutable provider evidence")
            known = rig_cost(store, plan, input_root=self.run.input_root, bindings=self.bindings)
        self.run.require_run_budget().settle(
            plan["operation_id"],
            plan["plan_sha256"],
            known_actual_usd=str(known if known is not None else Decimal(0)),
            unresolved_liability_usd=str(plan["reservation_usd"] if known is None else 0),
            outcome="completed",
        )
        artifact = result["artifacts"][0]

        def descriptor(field: str) -> dict[str, str]:
            path = confined(store.path, artifact[field])
            return {
                "path": path.relative_to(self.run.input_root).as_posix(),
                "sha256": digest(path),
            }

        return {
            "status": "raw_rig_collected",
            "source": descriptor("path"),
            "provenance": descriptor("provenance_path"),
            "task_id": receipt["task_id"],
            "plan_sha256": plan["plan_sha256"],
            "known_cost_usd": str(known) if known is not None else None,
            "provider_result": result,
        }
