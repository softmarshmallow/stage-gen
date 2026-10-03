"""The ``gnode`` command line.

    gnode plan <target> [inputs] [--max-usd N] [--check] [--expect-cached] [--json]
    gnode run <target> [inputs] [--live] [--max-usd N] [--yes-up-to N] [--deliver out=path]
    gnode reroll <run> <step-path>      gnode pick <run> <step-path> <take>
    gnode takes list <target> | mv <target> <old> <new>
    gnode inspect <run | workflow id> [--verify] [--json]
    gnode schema <target>               gnode nodes [type]
    gnode doctor [target]               gnode lock [where] [--same <node>] [--check]
    gnode expand | identity | price <target> [inputs]      gnode project <run>

``<target>`` is a workflow file, a workflow id in this project, or the id of a workflow an
installed plugin publishes. Inputs are the workflow's own flags
(``--max-entities 24``, the kebab-case of each input) and ``--inputs file.yaml``
(repeatable, merged in order; paths inside are relative to that file).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

import yaml

from gnode.workflow.api import run_at_plan
from gnode.workflow.document import DocumentError, load_workflow, read_yaml
from gnode.workflow.host import HostServices, resolve_tool, tool_name
from gnode.workflow.inputs import FILE_TAG, InputError, compile_inputs, flag_name
from gnode.workflow.plan import (
    BUILDER_TARGET,
    Plan,
    PlanError,
    Planner,
    Project,
    find_workflow,
    make_plan,
    make_planner,
    read_takes,
    takes_path,
)
from gnode.workflow.plugins import Composition, load_plugins
from gnode.workflow.registry import BUILTIN, Registry
from gnode.workflow.routes import RouteTable, route_table_from_document
from gnode.workflow.run import (
    EVENTS_FILE,
    PLAN_FILE,
    RunRefused,
    WorkflowRun,
    instance_document,
)
from gnode.workflow.runview import RunFolderError, project_run, read_plan, verify_run
from gnode.workflow.store import Store, StoreError, files_in
from gnode.workflow.values import Collection, FileValue

PROG = "gnode"


class UsageError(ValueError):
    pass


# ----------------------------------------------------------------------- arguments


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="a workflow file, or a workflow id in this project")
    parser.add_argument(
        "--inputs",
        action="append",
        type=Path,
        default=[],
        help="a YAML file of inputs (repeatable; later files win; paths are relative to it)",
    )
    parser.add_argument(
        "--routes",
        action="append",
        type=Path,
        default=[],
        help="add the routes of a 'gnode: routes/v1' file to the ones gnode ships",
    )
    parser.add_argument(
        "--arg",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="an argument for a Python builder target (file.py:function)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG, description="Plan and run gnode workflows.")
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="<command>")

    plan = verbs.add_parser("plan", help="expand, check and price a workflow; never spends")
    _common(plan)
    plan.add_argument("--max-usd", type=float, help="the run's ceiling")
    plan.add_argument("--check", action="store_true", help="exit non-zero on any problem")
    plan.add_argument(
        "--expect-cached",
        action="store_true",
        help="exit non-zero unless every step whose identity is known is in the cache",
    )
    plan.add_argument("--json", action="store_true", help="print the expanded graph as JSON")

    run = verbs.add_parser("run", help="run a workflow; --live admits paid calls")
    _common(run)
    run.add_argument("--live", action="store_true", help="admit paid provider calls")
    run.add_argument("--max-usd", type=float, help="the run's ceiling")
    run.add_argument(
        "--yes-up-to", type=float, help="approve each phase while the run's total stays under N"
    )
    run.add_argument(
        "--deliver",
        action="append",
        default=[],
        metavar="OUTPUT=PATH",
        help="copy an output there after the run; {key} names each element of a collection",
    )
    run.add_argument("--run", type=Path, dest="run_dir", help="the run folder (default: new)")

    reroll = verbs.add_parser("reroll", help="draw the next take of one step")
    reroll.add_argument("run", type=Path)
    reroll.add_argument("step")
    reroll.add_argument("--live", action="store_true")
    reroll.add_argument("--max-usd", type=float)

    pick = verbs.add_parser("pick", help="use one take of a step from now on")
    pick.add_argument("run", type=Path)
    pick.add_argument("step")
    pick.add_argument("take", type=int)

    takes = verbs.add_parser("takes", help="list or repair a takes file")
    takes_verbs = takes.add_subparsers(dest="takes_verb", required=True)
    takes_list = takes_verbs.add_parser("list")
    takes_list.add_argument("target")
    takes_mv = takes_verbs.add_parser("mv")
    takes_mv.add_argument("target")
    takes_mv.add_argument("old")
    takes_mv.add_argument("new")

    jobs = verbs.add_parser("jobs", help="long provider jobs submitted and not collected")
    jobs.add_argument(
        "--forget",
        metavar="KEY",
        help="drop one job's record so its call is submitted again (check the provider first)",
    )

    schema = verbs.add_parser("schema", help="the JSON Schema a workflow's inputs compile to")
    schema.add_argument("target")

    nodes = verbs.add_parser("nodes", help="the node types gnode knows")
    nodes.add_argument("type", nargs="?")

    doctor = verbs.add_parser("doctor", help="the tools and routes a workflow needs")
    doctor.add_argument("target", nargs="?")

    lock = verbs.add_parser("lock", help="pin versioned node types to their source")
    lock.add_argument(
        "where", nargs="?", help="a project folder, or a published workflow's id (default: here)"
    )
    lock.add_argument(
        "--same",
        metavar="NODE",
        action="append",
        default=[],
        help="confirm a source change keeps behaviour (repeatable)",
    )
    lock.add_argument(
        "--check", action="store_true", help="refuse an unlocked change; write nothing"
    )

    for name, summary in (
        ("expand", "the expanded graph, as JSON"),
        ("identity", "each instance's identity, as JSON"),
        ("price", "the plan's price by phase, as JSON"),
    ):
        verb = verbs.add_parser(name, help=summary)
        _common(verb)
        verb.add_argument("--max-usd", type=float)

    project = verbs.add_parser("project", help="a run's record projected to its state, as JSON")
    project.add_argument("run", type=Path)

    inspect = verbs.add_parser("inspect", help="a run's summary, from its own folder")
    inspect.add_argument("run", type=Path, help="a run folder, or a workflow id for its newest run")
    inspect.add_argument(
        "--verify", action="store_true", help="re-check every file against its recorded digest"
    )
    inspect.add_argument("--json", action="store_true", help="the run's view, as JSON")
    return parser


def _arguments(pairs: Sequence[str]) -> dict[str, str]:
    arguments: dict[str, str] = {}
    for pair in pairs:
        name, separator, value = pair.partition("=")
        if not separator or not name:
            raise UsageError(f"--arg {pair}: write NAME=VALUE")
        arguments[name] = value
    return arguments


def _input_flags(target: str, rest: Sequence[str], cwd: Path) -> dict[str, Any]:
    """Parse the workflow's own flags out of what argparse did not know."""

    if not rest:
        return {}
    if BUILDER_TARGET.fullmatch(target):
        raise UsageError(f"unknown flag {rest[0]}; a builder takes its arguments as --arg")
    project = Project.find(cwd)
    try:
        document = load_workflow(find_workflow(target, project, load_plugins().workflows))
    except (DocumentError, PlanError) as error:
        raise UsageError(str(error)) from error
    schema = compile_inputs(document.inputs)
    parser = argparse.ArgumentParser(prog=f"{PROG} {target}", add_help=False)
    for name, field in schema["properties"].items():
        kind = field.get("type")
        if isinstance(kind, list):
            kind = next(item for item in kind if item != "null")
        tag = field.get(FILE_TAG)
        if kind == "integer":
            parser.add_argument(flag_name(name), dest=name, type=int)
        elif kind == "number":
            parser.add_argument(flag_name(name), dest=name, type=float)
        elif kind == "boolean":
            parser.add_argument(flag_name(name), dest=name, type=_boolean)
        elif kind == "string":
            parser.add_argument(flag_name(name), dest=name)
        elif tag is not None and tag.get("many"):
            parser.add_argument(flag_name(name), dest=name, action="append")
    try:
        parsed, unknown = parser.parse_known_args(list(rest))
    except SystemExit as error:
        raise UsageError(f"bad input flag in {' '.join(rest)}") from error
    if unknown:
        raise UsageError(
            f"unknown input flag {unknown[0]}; lists and maps of {target} come from --inputs"
        )
    return {name: value for name, value in vars(parsed).items() if value is not None}


def _boolean(text: str) -> bool:
    lowered = text.lower()
    if lowered in {"true", "yes", "1"}:
        return True
    if lowered in {"false", "no", "0"}:
        return False
    raise argparse.ArgumentTypeError(f"{text} is not true or false")


# --------------------------------------------------------------------------- plans


def _routes(composition: Composition, extra: Sequence[Path]) -> RouteTable:
    catalog = composition.routes
    for path in extra:
        raw = read_yaml(path)
        if not isinstance(raw, dict):
            raise UsageError(f"{path.name} is not a route catalog")
        catalog = catalog.merged(route_table_from_document(raw))
    return catalog


def _planner(args: argparse.Namespace, rest: Sequence[str], cwd: Path) -> Planner:
    composition = load_plugins()
    return make_planner(
        args.target,
        arguments=_arguments(args.arg),
        inputs=_input_flags(args.target, rest, cwd),
        input_files=[path if path.is_absolute() else cwd / path for path in args.inputs],
        cwd=cwd,
        builtins=composition.builtins,
        routes=_routes(composition, [p if p.is_absolute() else cwd / p for p in args.routes]),
        facts_reader=composition.facts_reader,
        published=composition.workflows,
        views=composition.views,
    )


async def _plan(args: argparse.Namespace, rest: Sequence[str], cwd: Path) -> Plan:
    planner = _planner(args, rest, cwd)
    return await make_plan(planner, max_usd=getattr(args, "max_usd", None), plan_time=run_at_plan)


def _expanded(plan: Plan) -> dict[str, Any]:
    low, high = plan.estimate()
    return {
        "gnode": "graph/v2",
        "workflow": plan.planner.workflow.id,
        "instances": [instance_document(instance) for instance in plan.instances],
        "pending": [
            {"path": r.path, "max": r.max, "phase": r.phase, "high_usd": r.high_usd}
            for r in plan.expansion.pending
        ],
        "estimate": {"low_usd": low, "high_usd": high, "ceiling_usd": plan.ceiling_usd},
        "problems": [{"where": p.where, "message": p.message} for p in plan.problems],
    }


def _price(plan: Plan) -> dict[str, Any]:
    low, high = plan.estimate()
    return {
        "phases": [
            {
                "phase": s.phase,
                "steps": s.steps,
                "calls": [s.calls_low, s.calls_high],
                "low_usd": s.low_usd,
                "high_usd": s.high_usd,
                "then": list(s.pending),
            }
            for s in plan.phases()
        ],
        "estimate": {"low_usd": low, "high_usd": high},
        "ceiling_usd": plan.ceiling_usd,
    }


def _print_json(stdout: TextIO, value: Any) -> None:
    stdout.write(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


# ----------------------------------------------------------------------- commands


def cmd_plan(args: argparse.Namespace, rest: Sequence[str], cwd: Path, out: TextIO) -> int:
    plan = asyncio.run(_plan(args, rest, cwd))
    if args.json:
        _print_json(out, _expanded(plan))
    else:
        out.write(plan.render() + "\n")
    status = 0
    if args.check and plan.problems:
        status = 1
    if args.expect_cached:
        known = [
            i for i in plan.instances if i.identity is not None and i.state in {"planned", "maybe"}
        ]
        missing = [i.id for i in known if i.id not in plan.cached]
        unknown = [
            i.id for i in plan.instances if i.identity is None and i.state in {"planned", "maybe"}
        ]
        if missing or unknown or plan.expansion.pending:
            out.write(f"not cached: {', '.join(missing + unknown) or 'pending repeats'}\n")
            status = 1
    return status


def _new_run_dir(planner: Planner) -> Path:
    stamp = dt.datetime.now().strftime("%Y-%m-%d")
    base = planner.project.runs_dir / planner.workflow.id
    index = 1
    while (base / f"{stamp}-{index}").exists():
        index += 1
    return base / f"{stamp}-{index}"


def cmd_run(args: argparse.Namespace, rest: Sequence[str], cwd: Path, out: TextIO) -> int:
    plan = asyncio.run(_plan(args, rest, cwd))
    if not plan.ok:
        out.write(plan.render() + "\n")
        return 1
    composition = load_plugins()
    run_dir = (cwd / args.run_dir) if args.run_dir else _new_run_dir(plan.planner)
    services = HostServices(
        store=plan.planner.store,
        capabilities=composition.capabilities(plan.planner.store) if args.live else {},
        live=args.live,
    )
    out.write(plan.render() + "\n")
    try:
        outcome = asyncio.run(
            WorkflowRun(plan, run_dir=run_dir, services=services, yes_up_to=args.yes_up_to).run()
        )
    except RunRefused as error:
        out.write(f"refused: {error}\n")
        return 1
    match = BUILDER_TARGET.fullmatch(args.target)
    builder = (
        {"function": match["name"], "arguments": _arguments(args.arg)}
        if match is not None
        else None
    )
    _remember_inputs(plan, run_dir, builder)
    out.write(f"run       {run_dir}\n")
    out.write(
        f"result    {'ok' if outcome.ok else 'incomplete' if outcome.incomplete else 'failed'}"
        f"   spent ${outcome.cost_usd:.2f}\n"
    )
    for failed in outcome.failed:
        result = outcome.results.get(failed)
        out.write(f"failed    {failed}: {result.error if result else ''}\n")
    if outcome.stopped:
        out.write(f"stopped   {outcome.stopped}\n")
    delivered_ok = _deliver(outcome.outputs, args.deliver, cwd, plan.planner, out)
    return 0 if outcome.ok and delivered_ok else 1


def _remember_inputs(plan: Plan, run_dir: Path, builder: dict[str, Any] | None = None) -> None:
    """Keep the run's inputs (by content) so reroll and pick can plan it again."""

    planner = plan.planner
    for file in files_in(planner.inputs):
        if not planner.store.has(file) and file.location is not None:
            planner.store.put_file(Path(file.location), kind=file.kind, name=file.name)
    document = json.loads((run_dir / PLAN_FILE).read_text(encoding="utf-8"))
    document["target"] = str(planner.workflow_path)
    document["project"] = str(planner.project.root)
    document["builder"] = builder
    document["input_values"] = _encode_inputs(planner.inputs)
    (run_dir / PLAN_FILE).write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")


def _encode_inputs(value: Any) -> Any:
    if isinstance(value, FileValue):
        return {
            "$file": {
                "digest": value.digest,
                "kind": value.kind,
                "name": value.name,
                "size": value.size,
            }
        }
    if isinstance(value, dict):
        return {key: _encode_inputs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode_inputs(item) for item in value]
    return value


def _decode_inputs(store: Store, value: Any) -> Any:
    if isinstance(value, dict) and "$file" in value:
        entry = value["$file"]
        return store.file(
            entry["digest"], kind=entry["kind"], name=entry["name"], size=entry["size"]
        )
    if isinstance(value, dict):
        return {key: _decode_inputs(store, item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_inputs(store, item) for item in value]
    return value


def _deliver(
    outputs: dict[str, Any], requests: Sequence[str], cwd: Path, planner: Planner, out: TextIO
) -> bool:
    ok = True
    for request in requests:
        name, separator, pattern = request.partition("=")
        if not separator or name not in outputs:
            raise UsageError(f"--deliver {request}: name one of {', '.join(sorted(outputs))}")
        value = outputs[name]
        files: list[tuple[str | None, FileValue]] = []
        if isinstance(value, FileValue):
            files = [(None, value)]
        elif isinstance(value, Collection):
            files = [(key, item) for key, item in value.items if isinstance(item, FileValue)]
        elif isinstance(value, list):
            files = [
                (item.key or str(i), item)
                for i, item in enumerate(value)
                if isinstance(item, FileValue)
            ]
        if not files:
            out.write(f"missing   {name}: the run did not produce it\n")
            ok = False
            continue
        for key, file in files:
            if key is None and "{key}" in pattern:
                raise UsageError(f"--deliver {request}: {name} is one file, so no {{key}}")
            if key is not None and "{key}" not in pattern and len(files) > 1:
                raise UsageError(f"--deliver {request}: name each element with {{key}}")
            target = cwd / pattern.replace("{key}", key or "")
            source = planner.store.file_path(file.digest)
            if target.is_file() and target.read_bytes() == source.read_bytes():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            out.write(f"delivered {target}\n")
    return ok


def _planner_of_run(run: Path) -> tuple[Planner, dict[str, Any]]:
    document = json.loads((run / PLAN_FILE).read_text(encoding="utf-8"))
    if "target" not in document:
        raise UsageError(f"{run} was not started by gnode run")
    composition = load_plugins()
    target = Path(document["target"])
    project = Project.find(Path(document.get("project") or target))
    store = Store(project.cache_dir, facts_reader=composition.facts_reader)
    builder = document.get("builder")
    planner = make_planner(
        f"{target}:{builder['function']}" if builder else target,
        arguments=builder["arguments"] if builder else None,
        cwd=target.parent,
        project_root=project.root,
        builtins=composition.builtins,
        routes=composition.routes,
        facts_reader=composition.facts_reader,
        values=_decode_inputs(store, document.get("input_values", {})),
        views=composition.views,
    )
    return planner, document


def _write_takes(planner: Planner, choices: dict[str, dict[str, Any]]) -> Path:
    path = planner.takes_path
    header = f"# {path.name}: written by `gnode reroll` and `gnode pick`; commit it\n"
    body = yaml.safe_dump(choices, sort_keys=True, allow_unicode=True) if choices else ""
    path.write_text(header + body, encoding="utf-8")
    return path


def _current_takes(planner: Planner) -> dict[str, dict[str, Any]]:
    return {
        step: {"take": choice.take, **({"result": choice.result} if choice.result else {})}
        for step, choice in planner.takes.items()
    }


def _latest_take(run: Path, step: str) -> int:
    latest = 0
    for line in (run / EVENTS_FILE).read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event") == "node_started" and event.get("path") == step:
            take = event.get("take") or [1]
            latest = max(latest, int(take[-1]))
    return latest


def cmd_reroll(args: argparse.Namespace, cwd: Path, out: TextIO) -> int:
    planner, _ = _planner_of_run(cwd / args.run)
    latest = _latest_take(cwd / args.run, args.step)
    if latest == 0:
        raise UsageError(f"{args.run} never ran a step {args.step}")
    choices = _current_takes(planner)
    choices[args.step] = {"take": latest + 1}
    path = _write_takes(planner, choices)
    out.write(f"{path.name}: {args.step} uses take {latest + 1} from now on\n")
    out.write(f"next      gnode run {planner.workflow.id}{' --live' if args.live else ''}\n")
    return 0


def cmd_pick(args: argparse.Namespace, cwd: Path, out: TextIO) -> int:
    planner, _ = _planner_of_run(cwd / args.run)
    if args.take < 1:
        raise UsageError("a take is 1 or more")
    result = None
    for line in (cwd / args.run / EVENTS_FILE).read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if (
            event.get("event") == "node_finished"
            and event.get("path") == args.step
            and (event.get("id") or "").endswith(f"#{args.take}")
        ):
            files = [v["file"]["digest"] for v in event.get("outputs", {}).values() if "file" in v]
            result = f"sha256:{files[0]}" if files else None
    choices = _current_takes(planner)
    choices[args.step] = {"take": args.take, **({"result": result} if result else {})}
    path = _write_takes(planner, choices)
    out.write(f"{path.name}: {args.step} uses take {args.take}\n")
    return 0


def cmd_takes(args: argparse.Namespace, cwd: Path, out: TextIO) -> int:
    project = Project.find(cwd)
    workflow_path = find_workflow(args.target, project, load_plugins().workflows)
    document = load_workflow(workflow_path)
    path = takes_path(workflow_path, document, project)
    choices = read_takes(path)
    if args.takes_verb == "list":
        for step, choice in sorted(choices.items()):
            out.write(
                f"{step}  take {choice.take}{f'  {choice.result}' if choice.result else ''}\n"
            )
        return 0
    if args.old not in choices:
        raise UsageError(f"{path.name} has no entry {args.old}")
    entries = {
        step: {"take": c.take, **({"result": c.result} if c.result else {})}
        for step, c in choices.items()
    }
    entries[args.new] = entries.pop(args.old)
    header = f"# {path.name}: written by `gnode reroll` and `gnode pick`; commit it\n"
    path.write_text(header + yaml.safe_dump(entries, sort_keys=True), encoding="utf-8")
    out.write(f"{path.name}: {args.old} is now {args.new}\n")
    return 0


def cmd_jobs(args: argparse.Namespace, cwd: Path, out: TextIO) -> int:
    store = Store(Project.find(cwd).cache_dir)
    if args.forget:
        if store.load_job(args.forget) is None:
            raise UsageError(f"the cache holds no job {args.forget}")
        store.clear_job(args.forget)
        out.write(f"forgot job {args.forget}; its call is submitted again on the next run\n")
        return 0
    for job in store.jobs():
        out.write(f"{job.key}  {job.state}  {job.capability} on {job.route}, take {job.take}\n")
    return 0


def cmd_schema(args: argparse.Namespace, cwd: Path, out: TextIO) -> int:
    project = Project.find(cwd)
    document = load_workflow(find_workflow(args.target, project, load_plugins().workflows))
    _print_json(out, compile_inputs(document.inputs))
    return 0


def cmd_nodes(args: argparse.Namespace, out: TextIO) -> int:
    composition = load_plugins()
    routes = composition.routes
    for builtin in sorted(composition.builtins, key=lambda b: b.spec.name):
        spec = builtin.spec
        uses = f"gnode/{spec.name}@{builtin.major}"
        if args.type and args.type not in {spec.name, uses}:
            continue
        kind = "judge" if spec.judge else "paid" if spec.paid else "free"
        out.write(f"{uses:34} {kind}\n")
        if args.type:
            for name, port in spec.inputs.items():
                out.write(f"  input   {name}: {port.notation()}\n")
            for name, schema in spec.params.items():
                out.write(f"  setting {name}: {json.dumps(schema, sort_keys=True)}\n")
            for name, port in spec.outputs.items():
                out.write(f"  output  {name}: {port.notation()}\n")
            if spec.capability:
                served = [route.route_id for route in routes.routes(spec.capability)]
                out.write(f"  routes  {', '.join(served) or 'none installed'}\n")
    return 0


def cmd_doctor(args: argparse.Namespace, cwd: Path, out: TextIO) -> int:
    problems = 0
    composition = load_plugins()
    out.write(f"plugins   {', '.join(p.name for p in composition.plugins) or 'none'}\n")
    if args.target is None:
        return 0
    planner = make_planner(
        args.target,
        cwd=cwd,
        builtins=composition.builtins,
        routes=composition.routes,
        facts_reader=composition.facts_reader,
        published=composition.workflows,
        views=composition.views,
    )
    seen: set[str] = set()
    for step in _all_steps(planner.workflow.steps):
        if step.uses is None or step.uses in seen or BUILTIN.fullmatch(step.uses):
            continue
        seen.add(step.uses)
        try:
            resolved = planner.registry.node_type(step.uses, planner.home.root)
        except ValueError as error:
            out.write(f"missing   {step.uses}: {error}\n")
            problems += 1
            continue
        spec = getattr(resolved, "spec", None)
        for entry in getattr(spec, "tools", ()):
            name = tool_name(entry)
            found = resolve_tool(name)
            out.write(f"tool      {name:12} {found or 'NOT FOUND'}\n")
            problems += found is None
    return 1 if problems else 0


def _all_steps(steps: dict[str, Any]) -> list[Any]:
    found = []
    for step in steps.values():
        found.append(step)
        if step.steps:
            found.extend(_all_steps(step.steps))
    return found


def cmd_lock(args: argparse.Namespace, cwd: Path, out: TextIO) -> int:
    """Pin each versioned node type to its source; a change without a bump is refused.

    ``--same NODE`` (repeatable) confirms that NODE's source changed without changing what it
    makes;
    ``--check`` reports what is not locked and writes nothing.
    """

    composition = load_plugins()
    where = cwd
    if args.where:
        published = composition.workflows.get(args.where)
        where = published if published is not None else cwd / args.where
    project = Project.find(where)
    registry = Registry(
        project_root=project.root,
        builtins=composition.builtins,
        sources=project.document.sources,
    )
    lock = project.root / "gnode.lock"
    raw = yaml.safe_load(lock.read_text(encoding="utf-8")) if lock.is_file() else None
    locked: dict[str, str] = dict((raw or {}).get("nodes", {}))
    nodes = project.root / project.document.nodes
    status = 0
    for path in sorted(nodes.rglob("*.py")) if nodes.is_dir() else []:
        module = registry.modules.load(path)
        relative = path.relative_to(project.root).as_posix()
        for name, value in vars(module).items():
            spec = getattr(value, "gnode_spec", None)
            if spec is None or spec.version is None:
                continue
            key = f"{relative}#{name}@{spec.version}"
            source = registry.source_identity(path, spec)
            if args.check and key not in locked:
                out.write(f"unlocked  {relative}#{name}@{spec.version}: run gnode lock\n")
                status = 1
                continue
            if locked.get(key, source) != source and f"{relative}#{name}" not in args.same:
                out.write(
                    f"changed   {relative}#{name}: its source changed but version "
                    f"{spec.version} did not; bump it, or confirm with --same {relative}#{name}\n"
                )
                status = 1
                continue
            locked[key] = source
    if args.check:
        if status == 0:
            out.write(f"gnode.lock: {len(locked)} versioned node types, all locked\n")
        return status
    lock.write_text(
        "# gnode.lock: the source behind each versioned node type; commit it\n"
        + yaml.safe_dump({"nodes": dict(sorted(locked.items()))}, sort_keys=True),
        encoding="utf-8",
    )
    out.write(f"gnode.lock: {len(locked)} versioned node types\n")
    return status


def cmd_expand(args: argparse.Namespace, rest: Sequence[str], cwd: Path, out: TextIO) -> int:
    plan = asyncio.run(_plan(args, rest, cwd))
    if args.verb == "expand":
        _print_json(out, _expanded(plan))
    elif args.verb == "identity":
        _print_json(
            out,
            {i.id: i.identity for i in plan.instances if i.state in {"planned", "maybe", "done"}},
        )
    else:
        _print_json(out, _price(plan))
    return 1 if plan.problems else 0


def cmd_project(args: argparse.Namespace, cwd: Path, out: TextIO) -> int:
    run = cwd / args.run
    states: dict[str, dict[str, Any]] = {}
    summary: dict[str, Any] = {}
    for line in (run / EVENTS_FILE).read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        name = event.get("event")
        identifier = event.get("id")
        if name == "node_started" and isinstance(identifier, str):
            states[identifier] = {"state": "running", "path": event.get("path")}
        elif name == "node_finished" and isinstance(identifier, str):
            states[identifier] = {
                "state": "succeeded",
                "path": event.get("path"),
                "cache": event.get("cache"),
                "facts": event.get("facts", {}),
            }
        elif name in {"node_failed", "node_skipped"} and isinstance(identifier, str):
            states[identifier] = {
                "state": "failed" if name == "node_failed" else "skipped",
                "path": event.get("path"),
                "error": event.get("error") or event.get("reason"),
            }
        elif name in {"run_started", "run_finished", "run_canceled"}:
            summary[name] = {k: v for k, v in event.items() if k not in {"kind", "schema_version"}}
    _print_json(out, {"instances": states, "run": summary})
    return 0


def _run_folder(given: Path, cwd: Path) -> Path:
    """A run folder, or a workflow id: that workflow's newest run in this project."""

    folder = cwd / given
    if folder.is_dir() or given.parts != (given.name,):
        return folder
    runs = Project.find(cwd).runs_dir / given.name
    found = sorted(
        (run for run in runs.iterdir() if (run / PLAN_FILE).is_file()) if runs.is_dir() else (),
        key=lambda run: (run / PLAN_FILE).stat().st_mtime,
    )
    if not found:
        raise UsageError(f"no run folder {given}, and no runs of a workflow {given} here")
    return found[-1]


def cmd_inspect(args: argparse.Namespace, cwd: Path, out: TextIO) -> int:
    """What a run did, read only from its folder; ``--verify`` re-checks every file."""

    run = _run_folder(args.run, cwd)
    try:
        view = project_run(run)
    except RunFolderError as error:
        raise UsageError(str(error)) from error
    problems = verify_run(run) if args.verify else []
    if args.json:
        document: dict[str, Any] = {"view": view.model_dump(mode="json")}
        if args.verify:
            document["verification"] = {"verified": not problems, "problems": problems}
        _print_json(out, document)
        return 1 if problems else 0
    plan = read_plan(run)
    counts = ", ".join(f"{count} {state}" for state, count in view.state_counts.items())
    out.write(f"{plan['workflow']['id']}  ·  {run.name}\n")
    out.write(f"state     {view.run_state}   {len(view.nodes)} steps: {counts or 'none'}\n")
    if view.known_cost_usd is not None:
        out.write(f"spent     ${view.known_cost_usd:.2f}\n")
    failed = [node for node in view.nodes if node.state == "failed"]
    for node in failed:
        out.write(f"failed    {node.node_id}: {node.error or 'no reason recorded'}\n")
    if args.verify:
        files = sum(len(node.artifacts) for node in view.nodes)
        for problem in problems:
            out.write(f"differs   {problem}\n")
        if not problems:
            out.write(f"verified  {files} files\n")
    return 1 if problems else 0


# ---------------------------------------------------------------------------- main


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    cwd: Path | None = None,
) -> int:
    out, errors = stdout or sys.stdout, stderr or sys.stderr
    here = (cwd or Path.cwd()).resolve()
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        args, rest = parser.parse_known_args(arguments)
        if rest and args.verb not in {"plan", "run", "expand", "identity", "price"}:
            parser.error(f"unrecognized arguments: {' '.join(rest)}")
        if args.verb == "plan":
            return cmd_plan(args, rest, here, out)
        if args.verb == "run":
            return cmd_run(args, rest, here, out)
        if args.verb == "reroll":
            return cmd_reroll(args, here, out)
        if args.verb == "pick":
            return cmd_pick(args, here, out)
        if args.verb == "takes":
            return cmd_takes(args, here, out)
        if args.verb == "jobs":
            return cmd_jobs(args, here, out)
        if args.verb == "schema":
            return cmd_schema(args, here, out)
        if args.verb == "nodes":
            return cmd_nodes(args, out)
        if args.verb == "doctor":
            return cmd_doctor(args, here, out)
        if args.verb == "lock":
            return cmd_lock(args, here, out)
        if args.verb in {"expand", "identity", "price"}:
            return cmd_expand(args, rest, here, out)
        if args.verb == "project":
            return cmd_project(args, here, out)
        if args.verb == "inspect":
            return cmd_inspect(args, here, out)
    except (
        UsageError,
        PlanError,
        InputError,
        DocumentError,
        RunRefused,
        StoreError,
        OSError,
    ) as error:
        errors.write(f"{PROG}: {error}\n")
        return 2
    except KeyboardInterrupt:
        return 130
    return 2


def entrypoint() -> None:
    raise SystemExit(main())


__all__ = ["build_parser", "entrypoint", "main"]
