"""A qualification cohort: several briefs run serially under one configuration.

The cohort file names the settings every run shares and the briefs that vary:

    settings: { profile: sd_human_fixed_hands_v1, partition: whole, quality_bar: low }
    briefs: [briefs/one.md, briefs/two.md]

Every brief is planned first, and the cohort is refused unless every plan has the same support
target: one closure, one set of settings. ``--dry-run`` stops there and writes the manifest
with each plan's price. A live cohort then runs the plans one at a time, each under its own
ceiling, and stops at the first run that is not accepted; a run already accepted in an
earlier invocation is not run again. The manifest is evidence a support record names by
digest, so it holds digests, prices and outcomes, never a credential or a machine path.

    python -m stage_gen.workflows.character_3d.cohort cohort.yaml --out cohort-01 --dry-run
    python -m stage_gen.workflows.character_3d.cohort cohort.yaml --out cohort-01 \\
        --live --max-usd-each 30
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from gnode import Plan, run
from gnode import plan as make_plan
from stage_gen.workflows.character_3d.support import (
    WORKFLOW_ID,
    SupportRefused,
    blender_build,
    support_target,
)

MANIFEST = "cohort.json"
KIND = "character-3d-cohort-v1"


def _digest(value: object) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def read_cohort(path: Path) -> tuple[dict[str, Any], list[Path]]:
    """The shared settings and the brief files, relative to the cohort file."""

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"settings", "briefs"}:
        raise SupportRefused("a cohort file has exactly settings and briefs")
    settings, briefs = document["settings"], document["briefs"]
    if not isinstance(settings, dict) or {"brief", "parts"} & set(settings):
        raise SupportRefused("cohort settings are shared inputs; the briefs vary")
    if not isinstance(briefs, list) or len(briefs) < 2:
        raise SupportRefused("a cohort runs at least two briefs")
    paths = [(path.parent / str(brief)).resolve() for brief in briefs]
    stems = [brief.stem for brief in paths]
    if len(set(stems)) != len(stems):
        raise SupportRefused("each brief in a cohort needs its own file name")
    return settings, paths


def plan_cohort(
    cohort: Path, out: Path, *, blender: dict[str, Any], max_usd_each: float | None, project: Path
) -> tuple[dict[str, Any], list[tuple[str, Plan]]]:
    """Plan every brief and hold them to one support target: the manifest and the plans."""

    settings, briefs = read_cohort(cohort)
    inputs = out / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    planned: list[tuple[str, Plan]] = []
    episodes: list[dict[str, Any]] = []
    targets: dict[str, str] = {}
    target: dict[str, Any] = {}
    for brief in briefs:
        episode = brief.stem
        written = inputs / f"{episode}.yaml"
        written.write_text(
            yaml.safe_dump({**settings, "brief": str(brief)}, sort_keys=True), encoding="utf-8"
        )
        plan = make_plan(WORKFLOW_ID, input_files=[written], max_usd=max_usd_each, cwd=project)
        target = support_target(plan, blender=blender)
        targets[episode] = _digest(target)
        low, high = plan.estimate()
        episodes.append(
            {
                "episode_id": episode,
                "brief_sha256": hashlib.sha256(brief.read_bytes()).hexdigest(),
                "estimate_usd": [low, high],
                "ceiling_usd": plan.ceiling_usd,
            }
        )
        planned.append((episode, plan))
    if len(set(targets.values())) != 1:
        raise SupportRefused(f"the cohort's plans have different support targets: {targets}")
    manifest = {
        "schema_version": 1,
        "kind": KIND,
        "target": target,
        "target_sha256": next(iter(targets.values())),
        "episodes": episodes,
    }
    return manifest, planned


def _result(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "outputs" / "result.json"
    if not path.is_file():
        return None
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


def run_cohort(
    manifest: dict[str, Any], planned: Sequence[tuple[str, Plan]], out: Path
) -> dict[str, Any]:
    """Run each plan live in turn; stop at the first run that is not accepted."""

    episodes = {entry["episode_id"]: entry for entry in manifest["episodes"]}
    for episode, plan in planned:
        entry = episodes[episode]
        run_dir = out / "runs" / episode
        earlier = _result(run_dir)
        if earlier is None or earlier.get("status") != "accepted":
            result = run(plan, live=True, run_dir=run_dir)
            entry["cost_usd"] = round(result.cost, 6)
            earlier = _result(run_dir)
        entry["status"] = (earlier or {}).get("status", "failed")
        entry["result_sha256"] = (
            hashlib.sha256((run_dir / "outputs/result.json").read_bytes()).hexdigest()
            if earlier is not None
            else None
        )
        if entry["status"] != "accepted":
            manifest["stopped_at"] = episode
            break
    manifest["complete"] = all(e.get("status") == "accepted" for e in manifest["episodes"])
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stage_gen.workflows.character_3d.cohort")
    parser.add_argument("cohort", type=Path, help="the cohort file: settings and briefs")
    parser.add_argument("--out", type=Path, required=True, help="the cohort's folder")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="plan every brief; spend nothing")
    mode.add_argument("--live", action="store_true", help="run the plans; paid")
    parser.add_argument("--max-usd-each", type=float, default=None, help="each run's ceiling")
    parser.add_argument("--blender", default=None)
    parser.add_argument("--project", type=Path, default=None, help="where gnode.yaml is")
    arguments = parser.parse_args(argv)
    out: Path = arguments.out
    project: Path = arguments.project or out
    if arguments.project is None and not (out / "gnode.yaml").is_file():
        # The cohort is its own gnode project: its runs and its call cache stay inside it.
        out.mkdir(parents=True, exist_ok=True)
        (out / "gnode.yaml").write_text("gnode: project/v1\n", encoding="utf-8")
    try:
        if arguments.live and arguments.max_usd_each is None:
            raise SupportRefused("a live cohort needs --max-usd-each")
        manifest, planned = plan_cohort(
            arguments.cohort,
            out,
            blender=blender_build(arguments.blender),
            max_usd_each=arguments.max_usd_each,
            project=project,
        )
        manifest["dry_run"] = bool(arguments.dry_run)
        if arguments.live:
            manifest = run_cohort(manifest, planned, out)
    except SupportRefused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    for entry in manifest["episodes"]:
        low, high = entry["estimate_usd"]
        print(
            f"{entry['episode_id']:24} ${low:.2f} - ${high:.2f}  {entry.get('status', 'planned')}"
        )
    print(f"target {manifest['target_sha256']}  manifest {out / MANIFEST}")
    return 0 if arguments.dry_run or manifest.get("complete") else 3


if __name__ == "__main__":
    raise SystemExit(main())
