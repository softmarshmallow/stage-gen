"""Host support for character-3d: the closure a qualification binds, and admission.

A support record is a reviewed deployment decision kept outside any run folder; no model
writes it. It says one configuration was qualified. That configuration is a closure, not
a hash of every installed file: the node types as ``gnode.lock`` pins their source, the
workflow file, the core contract versions, each route with its contract and price, the
Blender build, and the settings the cohort ran with. The brief, the reference picture and
the supplied parts may vary.

A run is supported only when its plan has exactly the recorded closure. Anything else runs
in development and claims nothing. ``run_supported`` admits a plan and then runs that same
plan, so nothing can change between the check and the run.

    python -m stage_gen.workflows.character_3d.support target --inputs inputs.yaml
    python -m stage_gen.workflows.character_3d.support run --record support.json \\
        --inputs inputs.yaml --live --max-usd 30
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from gnode import (
    RUN_EVENTS_SCHEMA_VERSION,
    RUN_VIEW_SCHEMA_VERSION,
    Plan,
    RunResult,
    resolve_tool,
    run,
)
from gnode import plan as make_plan

type JsonObject = dict[str, Any]

WORKFLOW_ID = "character-3d"
#: The inputs that are the character, not the configuration: they may differ from the cohort.
CHARACTER_INPUTS = frozenset({"brief", "parts", "reference"})
_EVIDENCE = frozenset(
    {"cohort_manifest", "qualification_report", "calibration_report", "release_review"}
)
_RECORD_FIELDS = frozenset({"schema_version", "decision", "qualification_id", "target", "evidence"})


class SupportRefused(ValueError):
    """A support record that does not cover this configuration, or is not a valid decision."""


def _digest(value: object) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def blender_build(executable: str | Path | None = None) -> JsonObject:
    """The Blender build a run would use: its executable's bytes."""

    found = executable or resolve_tool("blender")
    if found is None or not Path(found).is_file():
        raise SupportRefused("no Blender to bind: install it or set GNODE_TOOL_BLENDER")
    return {"sha256": _sha256_file(Path(found))}


def closure(plan: Plan, *, blender: JsonObject) -> JsonObject:
    """What a qualification of this plan binds, apart from its settings."""

    if not plan.ok:
        problems = "; ".join(str(problem) for problem in plan.problems)
        raise SupportRefused(f"the plan is refused, so it has no closure: {problems}")
    planner = plan.planner
    if planner.workflow.id != WORKFLOW_ID:
        raise SupportRefused(f"support binds {WORKFLOW_ID}, not {planner.workflow.id}")
    types = {i.uses: i.type_identity for i in plan.instances if i.type_identity is not None}
    routes: dict[str, JsonObject] = {}
    for instance in plan.instances:
        for capability, route in instance.routes.items():
            routes[capability] = {
                "route": route.route_id,
                "fingerprint": route.fingerprint,
                "price": [route.price.low_usd, route.price.high_usd, route.price.unit],
            }
    return {
        "workflow_sha256": _sha256_file(planner.workflow_path),
        "lock": dict(sorted(planner.registry.locks.items())),
        "types": dict(sorted(types.items())),
        "contracts": {
            "workflow_document": planner.workflow.gnode,
            "run_events": RUN_EVENTS_SCHEMA_VERSION,
            "run_view": RUN_VIEW_SCHEMA_VERSION,
        },
        "routes": dict(sorted(routes.items())),
        "blender": dict(blender),
    }


def settings(plan: Plan) -> JsonObject:
    """The settings a cohort ran with: every input except the character itself."""

    inputs = plan.planner.inputs
    chosen = {k: v for k, v in inputs.items() if k not in CHARACTER_INPUTS}
    chosen["entry"] = "brief" if inputs.get("brief") is not None else "parts"
    plain: JsonObject = json.loads(json.dumps(chosen, sort_keys=True, default=str))
    return plain


def support_target(plan: Plan, *, blender: JsonObject) -> JsonObject:
    """The exact target a support record must name for this plan to be supported."""

    return {"closure": closure(plan, blender=blender), "settings": settings(plan)}


def admit(record: Mapping[str, Any] | None, target: Mapping[str, Any]) -> JsonObject:
    """Supported when ``record`` qualifies exactly ``target``; development without one."""

    if record is None:
        return {
            "schema_version": 1,
            "mode": "development",
            "support_qualified": False,
            "target_sha256": _digest(target),
        }
    if set(record) != _RECORD_FIELDS:
        raise SupportRefused("a support record has exactly " + ", ".join(sorted(_RECORD_FIELDS)))
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["decision"] != "qualified_for_support"
        or not isinstance(record["qualification_id"], str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", record["qualification_id"]) is None
    ):
        raise SupportRefused("the support decision is invalid or not qualified")
    evidence = record["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != _EVIDENCE:
        raise SupportRefused("a support decision names its complete reviewed evidence")
    if not all(_is_sha(value) for value in evidence.values()):
        raise SupportRefused("support evidence is named by SHA-256")
    if record["target"] != target:
        changed = sorted(
            key
            for part in ("closure", "settings")
            for key in set(record["target"].get(part, {})) | set(target.get(part, {}))
            if record["target"].get(part, {}).get(key) != target.get(part, {}).get(key)
        )
        raise SupportRefused(
            "the support record covers another configuration; changed: " + ", ".join(changed)
        )
    return {
        "schema_version": 1,
        "mode": "supported",
        "support_qualified": True,
        "target_sha256": _digest(target),
        "support_record_sha256": _digest(dict(record)),
        "qualification_id": record["qualification_id"],
    }


def run_supported(
    plan: Plan,
    record: Mapping[str, Any],
    *,
    blender: JsonObject,
    run_dir: Path | None = None,
    **options: Any,
) -> tuple[JsonObject, RunResult]:
    """Admit ``plan`` against ``record``, then run that same plan; refuses before any spend."""

    admission = admit(record, support_target(plan, blender=blender))
    result = run(plan, run_dir=run_dir, **options)
    (result.outcome.run_dir / "support.json").write_text(json.dumps(admission, indent=2) + "\n")
    return admission, result


# ------------------------------------------------------------------------------ command


def _plan(arguments: argparse.Namespace) -> Plan:
    return make_plan(
        WORKFLOW_ID,
        input_files=arguments.inputs,
        max_usd=arguments.max_usd,
        cwd=Path(arguments.project) if arguments.project else None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stage_gen.workflows.character_3d.support")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("target", "check", "run"):
        command = commands.add_parser(name)
        command.add_argument("--inputs", action="append", default=[], required=True)
        command.add_argument("--blender", default=None)
        command.add_argument("--project", default=None)
        command.add_argument("--max-usd", type=float, default=None)
        if name != "target":
            command.add_argument("--record", required=True)
        if name == "run":
            command.add_argument("--live", action="store_true")
            command.add_argument("--run-dir", default=None)
    arguments = parser.parse_args(argv)
    try:
        planned = _plan(arguments)
        blender = blender_build(arguments.blender)
        target = support_target(planned, blender=blender)
        if arguments.command == "target":
            print(json.dumps(target, indent=2, sort_keys=True))
            return 0
        record = yaml.safe_load(Path(arguments.record).read_text(encoding="utf-8"))
        if arguments.command == "check":
            print(json.dumps(admit(record, target), indent=2, sort_keys=True))
            return 0
        run_dir = Path(arguments.run_dir) if arguments.run_dir else None
        admission, _ = run_supported(
            planned,
            record,
            blender=blender,
            run_dir=run_dir,
            live=arguments.live,
            max_usd=arguments.max_usd,
        )
        print(json.dumps(admission, indent=2, sort_keys=True))
        return 0
    except SupportRefused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
