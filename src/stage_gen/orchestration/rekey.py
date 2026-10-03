"""Carry paid v1 results into a ported workflow's call cache, once, without a provider.

Porting a workflow to a workflow file changes every identity it has, so its paid calls
would be made again. This replays the ported workflow offline with handlers that answer
each paid call from the provider results of old v1 runs, but only from the result that was
made from exactly this request: the same provider and model, the same route, prompt and
input pictures, and the same size and background for a picture, or length, resolution
and aspect ratio for a clip, as the old result's provenance sidecar records them, and
bytes that still match the sidecar. A structured answer must be the model's own (not a
record the caller rewrote from it), and needs the same system prompt,
token limit and request policy, the pictures in the same order, and a schema that holds an
answer to the same constraints (both inlined and made canonical, as a provider is sent
them; the schema's name is a label). The answer is written to gnode's call cache as the
same bytes, or the same JSON, noting the artifact it was rekeyed from. A call no old
result answers is refused, never made, and the report prices it: that is what a live run
would bill.

The v1 formula goes in M9, and this with it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gnode import (
    CallRecord,
    CallRefused,
    CapabilityHandler,
    FileValue,
    HostServices,
    Plan,
    Route,
    RunOutcome,
    Store,
    WorkflowRun,
    canonicalize_strict_json_schema,
)
from stage_gen.orchestration.gnode_plugin import StructuredQuestion
from stage_gen.pipeline.structured_transport import inline_local_schema_refs

#: Provenance sidecars of v1 artifacts; the artifact sits beside its sidecar.
SIDECAR_SUFFIX = ".meta.json"


@dataclass(frozen=True, slots=True)
class OldResult:
    """One provider result of a v1 run, and the request its sidecar says made it."""

    artifact: Path
    media_type: str
    provider: str
    model: str
    route_id: str | None
    prompt_sha256: str
    #: The digests of its input files, in the order they were sent.
    sent: tuple[str, ...]
    #: The request's settings, as the sidecar recorded them.
    params: Mapping[str, Any]

    @property
    def inputs(self) -> frozenset[str]:
        return frozenset(self.sent)


def _old_result(sidecar: Path) -> OldResult | None:
    try:
        record = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or record.get("provider") in {None, "local"}:
        return None
    artifact = sidecar.with_name(sidecar.name.removesuffix(SIDECAR_SUFFIX))
    recorded = record.get("artifact") or {}
    digest = recorded.get("sha256")
    if not artifact.is_file() or not isinstance(digest, str):
        return None
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != digest:
        return None  # the bytes are not the ones the provider returned
    params = record.get("params") or {}
    binding = params.get("route_binding") or {}
    return OldResult(
        artifact=artifact,
        media_type=str(recorded.get("media_type") or "image/png"),
        provider=str(record["provider"]),
        model=str(record.get("model")),
        route_id=binding.get("route_id"),
        prompt_sha256=str(record.get("prompt_sha256")),
        sent=tuple(str(item["sha256"]) for item in record.get("inputs") or []),
        params=params,
    )


def old_results(runs: Iterable[Path]) -> list[OldResult]:
    """Every provider result under the old run folders whose bytes still match their record."""

    found = []
    for run in runs:
        for sidecar in sorted(run.rglob(f"*{SIDECAR_SUFFIX}")):
            result = _old_result(sidecar)
            if result is not None:
                found.append(result)
    return found


@dataclass(frozen=True, slots=True)
class Answer:
    capability: str
    route: str
    take: int
    old: Path | None
    high_usd: float


@dataclass
class RekeyReport:
    old: Sequence[OldResult] = ()
    answers: list[Answer] = field(default_factory=list)
    #: Old artifacts some call record in the cache was rekeyed from, this time or before.
    paired: set[Path] = field(default_factory=set)

    @property
    def unpaired(self) -> list[OldResult]:
        """Old provider results no call of the ported workflow was ever answered with."""

        return [result for result in self.old if result.artifact not in self.paired]

    @property
    def answered(self) -> list[Answer]:
        return [answer for answer in self.answers if answer.old is not None]

    @property
    def refused(self) -> list[Answer]:
        return [answer for answer in self.answers if answer.old is None]

    @property
    def would_bill_usd(self) -> float:
        return round(sum(answer.high_usd for answer in self.refused), 6)


def _files(request: Mapping[str, Any]) -> frozenset[str]:
    digests: set[str] = set()
    for value in request.values():
        items = value if isinstance(value, list) else [value]
        digests.update(item.digest for item in items if isinstance(item, FileValue))
    return frozenset(digests)


def _same_settings(old: OldResult, capability: str, request: Mapping[str, Any]) -> bool:
    params = old.params
    if capability == "video.generate":
        return (
            params.get("duration_seconds") == request.get("duration")
            and params.get("resolution") == request.get("resolution")
            and params.get("aspect_ratio") == request.get("aspect_ratio")
        )
    return params.get("size") == request.get("size") and params.get("background") in {
        None,
        request.get("background"),
    }


def _same_question(old: OldResult, route: Route, request: Mapping[str, Any]) -> bool:
    try:
        question = StructuredQuestion.of(request)
    except ValueError:
        return False
    params = old.params
    recorded = params.get("schema")
    policy = (params.get("metadata") or {}).get("request_policy")
    return (
        # A record the caller rewrote from the answer is not what the model said.
        params.get("artifact_value") != "caller-canonicalized"
        and (old.provider, old.model) == (route.provider, route.model)
        and old.prompt_sha256 == hashlib.sha256(question.prompt.encode("utf-8")).hexdigest()
        and old.sent == tuple(picture.digest for picture in question.pictures)
        and params.get("system") == question.system
        and params.get("max_tokens") == question.max_tokens
        and policy == route.contract.get("request_policy")
        and isinstance(recorded, dict)
        and canonicalize_strict_json_schema(inline_local_schema_refs(recorded))
        == question.sent_schema()
    )


def _matches(old: OldResult, capability: str, route: Route, request: Mapping[str, Any]) -> bool:
    if capability == "structured.generate":
        return old.media_type == "application/json" and _same_question(old, route, request)
    prompt = request.get("prompt")
    if not isinstance(prompt, str):
        return False
    return (
        (old.provider, old.model) == (route.provider, route.model)
        and old.route_id in {None, route.contract.get("route_id")}
        and old.prompt_sha256 == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        and old.inputs == _files(request)
        and _same_settings(old, capability, request)
    )


def rekey_handlers(
    capabilities: Sequence[str], old: Sequence[OldResult], store: Store, report: RekeyReport
) -> dict[str, CapabilityHandler]:
    """Handlers that answer only from ``old``; they never reach a provider."""

    def handler(capability: str) -> CapabilityHandler:
        async def answer(route: Route, request: Mapping[str, Any], take: int) -> CallRecord:
            high = route.cost(request)[1]
            # A later take is a new draw: no old result was made for it.
            found = (
                next((o for o in old if _matches(o, capability, route, request)), None)
                if take == 1
                else None
            )
            report.answers.append(
                Answer(
                    capability,
                    route.route_id,
                    take,
                    None if found is None else found.artifact,
                    high,
                )
            )
            if found is None:
                raise CallRefused(
                    f"no v1 result answers this {capability} call on {route.route_id} "
                    f"(take {take}); a live run would bill up to ${high:.2f}"
                )
            source = {"rekeyed_from": found.artifact.as_posix(), "attempts": 0}
            if capability == "structured.generate":
                value = json.loads(found.artifact.read_text(encoding="utf-8"))
                return CallRecord({}, {"json": value, **source}, 0.0)
            name = found.media_type.split("/", 1)[0]
            answer = store.put_file(found.artifact, kind=found.media_type, name=name)
            return CallRecord({name: answer}, source, 0.0)

        return answer

    return {capability: handler(capability) for capability in capabilities}


async def rekey(
    plan: Plan, runs: Sequence[Path], *, run_dir: Path
) -> tuple[RunOutcome, RekeyReport]:
    """Run ``plan`` with every paid call answered from ``runs``, or refused and priced."""

    old = old_results(runs)
    report = RekeyReport(old=old)
    store = plan.planner.store
    services = HostServices(
        store=store,
        capabilities=rekey_handlers(plan.planner.routes.capabilities(), old, store, report),
        live=True,
    )
    outcome = await WorkflowRun(plan, run_dir=run_dir, services=services).run()
    by_path = {result.artifact.as_posix(): result.artifact for result in old}
    for _, record in store.calls():
        source = record.data.get("rekeyed_from") if isinstance(record.data, Mapping) else None
        if isinstance(source, str) and source in by_path:
            report.paired.add(by_path[source])
    return outcome, report


__all__ = ["Answer", "OldResult", "RekeyReport", "old_results", "rekey", "rekey_handlers"]
