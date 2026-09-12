"""Installed character CLI with explicit input/output roots and frozen execution."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import sys
import uuid
from pathlib import Path
from typing import Any, cast

from stage_gen.components.character_3d.io import (
    confined,
    digest,
    read_json,
    verified_input,
    write_json,
)
from stage_gen.components.character_3d.package_resources import (
    installed_inventory,
    resource,
    snapshot_code,
    verify_snapshot,
)
from stage_gen.recipes.character_3d.experiment import validate_experiment
from stage_gen.recipes.character_3d.runner import CharacterRun, validate_provider_submit_stop

from .runtime_services import create_services
from .support_admission import AdmissionMode, admit_support, support_target

LAUNCH_PATH = Path(__file__).resolve()


def host_record(
    args: argparse.Namespace, input_root: Path, run_root: Path
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    if bool(args.support_record) != bool(args.support_record_sha256):
        raise ValueError("Support record path and SHA-256 must be supplied together")
    record = None
    descriptor = None
    if args.support_record:
        descriptor = {"path": args.support_record, "sha256": args.support_record_sha256}
        path = verified_input(input_root, descriptor)
        if path.is_relative_to(run_root):
            raise ValueError("Host support records must be outside the writable run")
        record = read_json(path)
    return descriptor, record


def admission(
    args: argparse.Namespace,
    experiment: dict[str, Any],
    input_root: Path,
    run_root: Path,
    inventory: dict[str, Any],
) -> dict[str, Any]:
    descriptor, record = host_record(args, input_root, run_root)
    if args.admission_mode == "supported" and record is None:
        raise ValueError("Supported execution requires a reviewed host support record")
    profile_path = resource(experiment["profile"]["path"])
    if digest(profile_path) != experiment["profile"]["sha256"]:
        raise ValueError("Installed profile content differs from the experiment")
    target = support_target(
        package_closure_sha256=inventory["package_closure_sha256"],
        blender_executable_sha256=digest(args.blender.resolve(strict=True)),
        python_version=sys.version.split()[0],
        runtime_dependencies=inventory["dependencies"],
        experiment=experiment,
        profile=read_json(profile_path),
        routes=create_services().upstream_bindings().bindings,
    )
    result = admit_support(
        mode=cast(AdmissionMode, args.admission_mode), target=target, support_record=record
    )
    result["host_record_input"] = descriptor
    return result


def run_class(mode: str, *, provider_rig: bool = False) -> type[CharacterRun]:
    if provider_rig:
        from stage_gen.recipes.character_3d.provider_runner import (
            ProviderBriefRun,
            ProviderFullRun,
            ProviderRigRun,
        )

        return {
            "brief_to_rig": ProviderBriefRun,
            "parts_to_rig": ProviderFullRun,
            "rig": ProviderRigRun,
        }[mode]
    from stage_gen.recipes.character_3d.brief_runner import BriefRun
    from stage_gen.recipes.character_3d.full_runner import FullRun
    from stage_gen.recipes.character_3d.rig_runner import RigRun
    from stage_gen.recipes.character_3d.runner import CharacterRun

    if mode == "rig_review_calibration":
        from stage_gen.recipes.character_3d.calibration_runner import ReviewCalibrationRun

        return ReviewCalibrationRun
    return {
        "assembly": CharacterRun,
        "rig": RigRun,
        "parts_to_rig": FullRun,
        "brief_to_rig": BriefRun,
    }[mode]


async def execute(args: argparse.Namespace) -> int:
    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("An active launch task is required")
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, task.cancel, f"signal_{signum}")
    raw = read_json(args.experiment)
    experiment = raw if args.resume and not args.frozen else validate_experiment(raw)
    stop_after_submit = getattr(args, "stop_after_provider_submit", False)
    if stop_after_submit:
        validate_provider_submit_stop(
            experiment,
            admission_mode=args.admission_mode,
            live=args.live,
            prepare_only=args.prepare_only,
            resume=args.resume,
        )
    if args.live and os.environ.get("STAGE_GEN_RUN_LIVE") != "1":
        raise ValueError("Live execution requires both --live and STAGE_GEN_RUN_LIVE=1")
    if not args.live and not args.prepare_only:
        raise ValueError("Offline execution requires --prepare-only")
    input_root = args.input_root.resolve(strict=True)
    requested = args.run_root.absolute()
    if any(path.is_symlink() for path in (requested, *requested.parents)):
        raise ValueError("Run paths cannot contain symlinked ancestors")
    run_root = requested.resolve()
    if not run_root.is_relative_to(input_root) or run_root == input_root:
        raise ValueError("Run root must be a confined child of the declared input root")
    if args.frozen:
        runtime = verify_snapshot(run_root)
        current = admission(args, experiment, input_root, run_root, runtime)
        if runtime.get("support_admission") != current:
            raise ValueError("Frozen execution requires its unchanged admission decision")
        if run_root / "code/stage_gen/orchestration/character_3d/launch.py" != LAUNCH_PATH:
            raise ValueError("Frozen execution must import its own verified run snapshot")
        if read_json(confined(run_root, "experiment.json")) != experiment:
            raise ValueError("The saved experiment changed")
        cls = run_class(
            experiment.get("pipeline_mode", "assembly"), provider_rig="rigging" in experiment
        )
        run = cls(
            package_root=run_root / "code",
            input_root=input_root,
            run_root=run_root,
            experiment=experiment,
            blender=args.blender.resolve(strict=True),
            live=args.live,
            dotenv=args.dotenv,
            services=create_services(live=args.live, dotenv=args.dotenv),
        )
        if stop_after_submit:
            ok = await run.run(stop_after_provider_submit=True, admission_mode=args.admission_mode)
        else:
            ok = await run.run(prepare_only=args.prepare_only, resume=args.resume)
        print(json.dumps({"run": run_root.name, "ok": ok, "scope": experiment["scope"]}))
        return 0 if ok else 1
    if args.resume:
        runtime = verify_snapshot(run_root)
        descriptor, _ = host_record(args, input_root, run_root)
        saved = runtime.get("support_admission", {})
        if saved.get("mode") != args.admission_mode or saved.get("host_record_input") != descriptor:
            raise ValueError("Resume requires unchanged admission mode and host record")
        # The frozen child owns full target evaluation against its original
        # profile, routes and source closure, even after the installed package changes.
        if read_json(confined(run_root, "experiment.json")) != experiment:
            raise ValueError("Resume requires the unchanged saved experiment")
    else:
        if run_root.exists():
            raise ValueError("Run output must be fresh unless --resume is explicit")
        inventory = installed_inventory()
        current = admission(args, experiment, input_root, run_root, inventory)
        for field in ("profile", "pricing"):
            source = resource(experiment[field]["path"])
            if hashlib.sha256(source.read_bytes()).hexdigest() != experiment[field]["sha256"]:
                raise ValueError("Installed profile/pricing content differs from the experiment")
        for part in experiment.get("parts", []):
            verified_input(input_root, part["source"])
        if experiment.get("reference"):
            verified_input(input_root, experiment["reference"])
        if experiment.get("assembly_input"):
            for field in ("source", "review"):
                verified_input(input_root, experiment["assembly_input"][field])
        run_root.mkdir(parents=True, exist_ok=False)
        write_json(run_root / "experiment.json", experiment)
        snapshot_code(None, run_root, support_admission=current)
    code = run_root / "code"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(code)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable,
        "-s",
        "-P",
        "-m",
        "stage_gen.orchestration.character_3d.launch",
        "--frozen",
        "--experiment",
        str(run_root / "experiment.json"),
        "--input-root",
        str(input_root),
        "--run-root",
        str(run_root),
        "--blender",
        str(args.blender.resolve(strict=True)),
        "--admission-mode",
        args.admission_mode,
    ]
    for field in ("live", "prepare_only", "resume", "stop_after_provider_submit"):
        if getattr(args, field, False):
            command.append("--" + field.replace("_", "-"))
    if args.dotenv:
        command.extend(["--dotenv", str(args.dotenv.absolute())])
    if args.support_record:
        command.extend(
            [
                "--support-record",
                args.support_record,
                "--support-record-sha256",
                args.support_record_sha256,
            ]
        )
    child = await asyncio.create_subprocess_exec(*command, cwd=code, env=environment)
    try:
        return await child.wait()
    except BaseException:
        if child.returncode is None:
            child.terminate()
            try:
                await asyncio.wait_for(child.wait(), 15)
            except TimeoutError:
                child.kill()
                await child.wait()
        raise


async def tracked_execute(args: argparse.Namespace) -> int:
    existed = args.run_root.exists()
    try:
        return await execute(args)
    except BaseException as error:
        # Persist a terminal launch failure without leaking exception text or
        # inventing a zero-call/cost claim after a frozen child may have run.
        report = {
            "status": "launch_failed",
            "error_type": type(error).__name__,
            "provider_dispatches": None,
            "accepted": False,
        }
        root = args.run_root.absolute()
        try:
            allowed = args.input_root.resolve(strict=True)
            if (
                (not existed or args.frozen or args.resume)
                and root.is_dir()
                and root.resolve().is_relative_to(allowed)
                and root.resolve() != allowed
                and not any(path.is_symlink() for path in (root, *root.parents))
            ):
                target = root / "outcome.json"
                if target.exists():
                    target = root / "invocations" / ("launch-" + uuid.uuid4().hex) / "outcome.json"
                write_json(target, report)
        except (OSError, ValueError):
            pass
        print(json.dumps(report), flush=True)
        return 130 if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--dotenv", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--stop-after-provider-submit",
        action="store_true",
        help="Development only: stop at the first committed rig task before collection",
    )
    parser.add_argument(
        "--admission-mode",
        choices=("supported", "development", "qualification"),
        default="supported",
    )
    parser.add_argument(
        "--support-record", help="Host-reviewed portable input path outside the run"
    )
    parser.add_argument("--support-record-sha256")
    parser.add_argument("--frozen", action="store_true", help=argparse.SUPPRESS)
    raise SystemExit(asyncio.run(tracked_execute(parser.parse_args())))


if __name__ == "__main__":
    main()
