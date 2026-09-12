"""Provider stage executor: declared routes, durable reservations and source lineage."""

from __future__ import annotations

import asyncio
import copy
import re
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Protocol

from gnode import BindingTable
from stage_gen.components.character_3d.budget_pool import BudgetPool
from stage_gen.components.character_3d.identity import IDENTITY
from stage_gen.components.character_3d.io import (
    canonical_digest,
    confined,
    digest,
    read_json,
    write_json,
)
from stage_gen.components.character_3d.provider_contracts import (
    OperationStore,
    identifier,
    plan_generation,
    verify_result,
)
from stage_gen.orchestration.character_3d.policy_defaults import default_bindings
from stage_gen.providers.character_3d.images import (
    ImageBackendFactory,
    generate_reference,
)
from stage_gen.providers.character_3d.tripo import TripoParts
from stage_gen.providers.character_3d.tripo_pricing import mesh_cost

JsonObject = dict[str, Any]


class ProviderRun(Protocol):
    input_root: Path
    run_root: Path
    experiment: JsonObject
    live: bool

    def provider_key(self, name: str) -> str: ...

    def require_run_budget(self) -> BudgetPool: ...

    def upstream_bindings(self) -> BindingTable: ...


def image_cost(operation_root: Path, plan_sha256: str | None = None) -> Decimal | None:
    """Accept only a provider-reported USD cost; missing billing is not zero."""
    try:
        path = confined(operation_root, "response.json")
        response = read_json(path)
        if plan_sha256 is not None and response.get("plan_sha256") != plan_sha256:
            return None
        if digest(confined(operation_root, "response.bin")) != response["sha256"]:
            return None
        usage = response["response_metadata"]["usage"]
        if isinstance(usage["cost"], bool):
            return None
        value = Decimal(str(usage["cost"]))
    except (KeyError, TypeError, InvalidOperation, ValueError, OSError):
        return None
    return value if value.is_finite() and 0 <= value < Decimal("1e20") else None


class UpstreamExecutor:
    def __init__(
        self,
        run: ProviderRun,
        *,
        bindings: BindingTable | None = None,
        image_backend_factory: ImageBackendFactory | None = None,
    ) -> None:
        self.run = run
        self.bindings = (
            bindings
            if bindings is not None
            else run.upstream_bindings()
            if hasattr(run, "upstream_bindings")
            else default_bindings()
        )
        self.image_backend_factory = image_backend_factory
        relative = (run.run_root / "upstream" / "operations").relative_to(run.input_root).as_posix()
        self.root = confined(run.input_root, relative, must_exist=False)
        self.root.mkdir(parents=True, exist_ok=True)
        self._operations: dict[str, JsonObject] = {}
        for path in sorted(self.root.glob("*/accounting.json")):
            binding = read_json(confined(self.root, path.relative_to(self.root).as_posix()))
            self._validate_binding(binding)
            if path.parent.name != binding["operation_id"]:
                raise ValueError("Image accounting directory differs from operation identity")
            self._operations[binding["operation_id"]] = binding

    @staticmethod
    def _validate_binding(binding: JsonObject) -> None:
        if (
            not isinstance(binding, dict)
            or set(binding) != {"schema_version", "operation_id", "episode_id", "plan_sha256"}
            or type(binding["schema_version"]) is not int
            or (binding["schema_version"] != 1)
        ):
            raise ValueError("Invalid image accounting binding")
        identifier(binding["operation_id"])
        identifier(binding["episode_id"])
        if not isinstance(binding["plan_sha256"], str) or not re.fullmatch(
            "[a-f0-9]{64}", binding["plan_sha256"]
        ):
            raise ValueError("Image accounting requires immutable plan lineage")

    def _bind_episode(self, plan: JsonObject, episode_id: str | None) -> None:
        binding = {
            "schema_version": 1,
            "operation_id": plan["operation_id"],
            "episode_id": episode_id,
            "plan_sha256": plan["plan_sha256"],
        }
        self._validate_binding(binding)
        path = confined(self.root, plan["operation_id"] + "/accounting.json", must_exist=False)
        if path.exists():
            if read_json(path) != binding:
                raise ValueError("Image operation cannot change its owning episode or plan")
        else:
            write_json(path, binding)
        self._operations[plan["operation_id"]] = binding

    def _operation_accounting(self, binding: JsonObject) -> JsonObject:
        allocation = (
            self.run.require_run_budget().snapshot()["reservations"].get(binding["operation_id"])
        )
        if allocation is not None and allocation["identity_sha256"] != binding["plan_sha256"]:
            raise ValueError("Image accounting and budget plan lineage differ")
        started = allocation is not None and allocation["dispatch_started"]
        known = image_cost(self.root / binding["operation_id"], binding["plan_sha256"])
        if allocation is not None and allocation["status"] == "settled":
            recorded = Decimal(allocation["settlement"]["known_actual_usd"])
            known = max(recorded, known if known is not None else Decimal(0))
        return {
            "provider_operations": int(started),
            "known_cost_usd": str(known if started and known is not None else Decimal(0)),
        }

    def accounting(self, episode_id: str) -> JsonObject:
        identifier(episode_id)
        records = [
            self._operation_accounting(binding)
            for binding in self._operations.values()
            if binding["episode_id"] == episode_id
        ]
        with localcontext() as context:
            context.prec = 100
            known = sum((Decimal(item["known_cost_usd"]) for item in records), Decimal(0))
        return {
            "provider_operations": sum(item["provider_operations"] for item in records),
            "known_cost_usd": known,
        }

    def snapshot(self) -> JsonObject:
        body = {
            "schema_version": 1,
            "operations": {
                name: {**binding, **self._operation_accounting(binding)}
                for name, binding in sorted(self._operations.items())
            },
        }
        return {**body, "state_sha256": canonical_digest(body)}

    def restore(self, state: JsonObject) -> JsonObject:
        """Verify a host checkpoint against durable bindings; never submit anything.

        Disk may contain later operations or charges than the host checkpoint.
        Keep them, so recovering an older checkpoint cannot erase an uncertain call.
        """
        if not isinstance(state, dict) or set(state) != {
            "schema_version",
            "operations",
            "state_sha256",
        }:
            raise ValueError("Invalid upstream accounting snapshot")
        body = {key: value for key, value in state.items() if key != "state_sha256"}
        if (
            type(state["schema_version"]) is not int
            or state["schema_version"] != 1
            or canonical_digest(body) != state["state_sha256"]
            or (not isinstance(state["operations"], dict))
        ):
            raise ValueError("Upstream accounting snapshot schema or digest differs")
        for name, item in state["operations"].items():
            if not isinstance(item, dict) or set(item) != {
                "schema_version",
                "operation_id",
                "episode_id",
                "plan_sha256",
                "provider_operations",
                "known_cost_usd",
            }:
                raise ValueError("Invalid upstream operation snapshot")
            binding = {
                key: item[key]
                for key in ("schema_version", "operation_id", "episode_id", "plan_sha256")
            }
            self._validate_binding(binding)
            if name != binding["operation_id"] or self._operations.get(name) != binding:
                raise ValueError("Snapshot operation differs from durable episode lineage")
            current = self._operation_accounting(binding)
            try:
                known = Decimal(item["known_cost_usd"])
            except (TypeError, InvalidOperation):
                raise ValueError("Snapshot has invalid known image cost") from None
            if (
                type(item["provider_operations"]) is not int
                or item["provider_operations"] not in (0, 1)
                or (
                    not isinstance(item["known_cost_usd"], str)
                    or not known.is_finite()
                    or known < 0
                    or (item["provider_operations"] > current["provider_operations"])
                    or (known > Decimal(current["known_cost_usd"]))
                )
            ):
                raise ValueError(
                    "Snapshot accounting exceeds its durable dispatch or billing evidence"
                )
        return self.snapshot()

    def plan(self, spec: JsonObject, operation: str) -> JsonObject:
        spec = copy.deepcopy(spec)
        binding = self.bindings.require(operation)
        return plan_generation(
            {
                "schema_version": 1,
                "operation_id": spec["operation_id"],
                "operation": operation,
                "prompt": spec["prompt"],
                "inputs": spec["inputs"],
                "params": spec["params"],
                "rights_basis": spec["rights_basis"],
                "reservation_usd": binding.estimated_cost_high_usd,
            },
            input_root=self.run.input_root,
            bindings=self.bindings,
        )

    def descriptor(
        self, operation_id: str, artifact: JsonObject, field: str = "path"
    ) -> dict[str, str]:
        source = confined(self.root / operation_id, artifact[field])
        return {
            "path": source.relative_to(self.run.input_root).as_posix(),
            "sha256": digest(source),
        }

    def reserve(self, plan: JsonObject) -> tuple[JsonObject, JsonObject]:
        account = self.run.require_run_budget()
        amount = str(plan["reservation_usd"])
        record = account.reserve(plan["operation_id"], plan["plan_sha256"], amount)
        return (
            record,
            {
                "reservation_id": plan["operation_id"],
                "plan_sha256": plan["plan_sha256"],
                "amount_usd": float(amount),
            },
        )

    def settle(
        self,
        plan: JsonObject,
        *,
        known: Decimal | None = None,
        interrupted: bool = False,
        not_started: bool = False,
    ) -> JsonObject:
        unknown = Decimal(0) if known is not None else Decimal(str(plan["reservation_usd"]))
        if interrupted:
            unknown = max(unknown, Decimal(str(plan["reservation_usd"])) - (known or Decimal(0)))
        return self.run.require_run_budget().settle(
            plan["operation_id"],
            plan["plan_sha256"],
            known_actual_usd=str(known if known is not None else 0),
            unresolved_liability_usd="0" if not_started else str(unknown),
            outcome="not_started" if not_started else "interrupted" if interrupted else "completed",
        )

    def _verified_result(self, plan: JsonObject) -> JsonObject:
        store = OperationStore(self.root, plan["operation_id"])
        with store.lock():
            if store.read("plan.json") != plan:
                raise ValueError("Cached provider plan lineage differs")
            result = verify_result(store, plan)
        expected = (
            "reference_collected"
            if plan["operation"] == "reference_image"
            else "raw_parts_collected"
        )
        if result is None or result.get("status") != expected or (not result.get("artifacts")):
            raise ValueError(
                "Terminal operation has no validated durable output; it will not repost"
            )
        return result

    def _start(self, plan: JsonObject, allocation: JsonObject, key_name: str) -> str:
        try:
            key = self.run.provider_key(key_name)
        except BaseException:
            self.settle(
                plan,
                interrupted=allocation["dispatch_started"],
                not_started=not allocation["dispatch_started"],
            )
            raise
        self.run.require_run_budget().mark_started(plan["operation_id"], plan["plan_sha256"])
        return key

    async def generate_image(self, spec: JsonObject) -> JsonObject:
        if self.run.live is not True:
            raise ValueError("Upstream provider calls are disabled outside explicit live execution")
        plan = self.plan(spec, "reference_image")
        episode_id = getattr(self.run, "active_reference_episode", None)
        self._bind_episode(plan, episode_id)
        allocation, reservation = self.reserve(plan)
        if allocation["status"] == "settled":
            result = self._verified_result(plan)
            return self._image_receipt(plan, result)
        key = self._start(plan, allocation, "OPENROUTER_API_KEY")
        try:
            result = await generate_reference(
                plan,
                api_key=key,
                input_root=self.run.input_root,
                output_root=self.root,
                reservation=reservation,
                component=IDENTITY,
                tool=IDENTITY,
                live=True,
                bindings=self.bindings,
                backend_factory=self.image_backend_factory,
            )
            persisted = self._verified_result(plan)
            if persisted != result:
                raise ValueError("Image adapter receipt differs from durable validated output")
        except BaseException as error:
            known = image_cost(self.root / plan["operation_id"], plan["plan_sha256"])
            self.settle(
                plan, known=known, interrupted=known is None or not isinstance(error, Exception)
            )
            raise
        self.settle(plan, known=image_cost(self.root / plan["operation_id"], plan["plan_sha256"]))
        return self._image_receipt(plan, result)

    def _image_receipt(self, plan: JsonObject, result: JsonObject) -> JsonObject:
        artifact = result["artifacts"][0]
        return {
            "source": self.descriptor(plan["operation_id"], artifact),
            "provenance": self.descriptor(plan["operation_id"], artifact, "provenance_path"),
        }

    async def generate_part(
        self, role: str, views: Sequence[JsonObject], attempt: int
    ) -> JsonObject:
        if self.run.live is not True:
            raise ValueError("Upstream provider calls are disabled outside explicit live execution")
        spec = {
            "operation_id": f"mesh_{role}_{attempt:02d}",
            "prompt": f"Generate the independently reviewed {role} part from its named views.",
            "inputs": [
                dict(view=item["view"], **item["source"])
                for item in views
                if item["view"] in {"front", "back", "left", "right"}
            ],
            "params": self.run.experiment["upstream"]["mesh_params"],
            "rights_basis": self.run.experiment["brief"]["rights_basis"],
        }
        plan = self.plan(spec, "part_mesh")
        allocation, reservation = self.reserve(plan)
        if allocation["status"] == "settled":
            return self._part_receipt(plan, role, self._verified_result(plan))
        key = self._start(plan, allocation, "TRIPO_API_KEY")
        provider = None
        try:
            provider = TripoParts(
                api_key=key,
                input_root=self.run.input_root,
                output_root=self.root,
                component=IDENTITY,
                tool=IDENTITY,
                bindings=self.bindings,
            )
            await provider.submit(plan, reservation=reservation, live=True)
            while True:
                result = await provider.collect(plan, live=True)
                if result["status"] == "raw_parts_collected":
                    break
                if result["status"] not in {"queued", "running"}:
                    raise ValueError(
                        "Mesh task terminated without a usable output: " + result["status"]
                    )
                await asyncio.sleep(self.run.experiment["upstream"]["poll_interval_seconds"])
            if self._verified_result(plan) != result:
                raise ValueError("Mesh adapter receipt differs from durable validated output")
            store = OperationStore(self.root, plan["operation_id"])
            with store.lock():
                known = mesh_cost(
                    store, plan, input_root=self.run.input_root, bindings=self.bindings
                )
        except BaseException:
            self.settle(plan, interrupted=True)
            raise
        finally:
            if provider is not None:
                await provider.aclose()
        self.settle(plan, known=known)
        return self._part_receipt(plan, role, result)

    def _part_receipt(self, plan: JsonObject, role: str, result: JsonObject) -> JsonObject:
        artifacts = result["artifacts"]
        artifact = next(
            (item for item in artifacts if Path(item["path"]).suffix == ".fbx"), artifacts[0]
        )
        source = self.descriptor(plan["operation_id"], artifact)
        provenance = self.descriptor(plan["operation_id"], artifact, "provenance_path")
        record = {
            "role": role,
            "source": source,
            "provenance": provenance,
            "plan_sha256": plan["plan_sha256"],
            "operation_id": plan["operation_id"],
            "semantic_status": "unreviewed",
            "raw_artifacts": artifacts,
        }
        path = confined(self.root, plan["operation_id"] + "/selection.json", must_exist=False)
        if path.exists():
            if read_json(path) != record:
                raise ValueError("Selected mesh lineage differs from its immutable receipt")
        else:
            write_json(path, record)
        return record
