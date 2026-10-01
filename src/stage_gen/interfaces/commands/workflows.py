"""``stage-gen list`` and ``stage-gen show WORKFLOW``.

``list`` reads only the installed ``workflow.toml`` manifests, so it imports no workflow.
``show`` builds one workflow's catalog entry in memory: its steps, identity, offline sample
plan and examples, read from the code and the local example store.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, TextIO


def register_list(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="print the manifests as JSON")
    parser.set_defaults(handler=list_workflows)


def register_show(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("workflow")
    parser.add_argument("--examples", type=Path, dest="examples_dir", help="the example store")
    parser.add_argument("--json", action="store_true", help="print the catalog entry as JSON")
    parser.set_defaults(handler=show_workflow)


def list_workflows(args: argparse.Namespace, stdout: TextIO) -> int:
    from stage_gen.workflows._registry import discover

    workflows = discover()
    if args.json:
        rows = [
            {
                "id": found.id,
                "title": found.manifest.title,
                "promise": found.manifest.promise,
                "related": found.manifest.related,
                "examples": [entry.id for entry in found.manifest.examples],
            }
            for found in workflows
        ]
        stdout.write(json.dumps(rows, indent=2) + "\n")
        return 0
    width = max(len(found.id) for found in workflows)
    for found in workflows:
        stdout.write(f"{found.id:<{width}}  {found.manifest.title}: {found.manifest.promise}\n")
    return 0


def show_workflow(args: argparse.Namespace, stdout: TextIO) -> int:
    from stage_gen.workflows._catalog import default_examples_dir, describe

    document = describe(args.workflow, examples_dir=args.examples_dir or default_examples_dir())
    stdout.write(json.dumps(document, indent=2) + "\n" if args.json else _page(document))
    return 0


def _page(document: dict[str, Any]) -> str:
    manifest = document["manifest"]
    lines = [f"{manifest['title']} ({document['id']})", manifest["promise"], ""]
    lines += [manifest["summary"].strip(), ""]
    if document["plan_refusal"]:
        lines += [f"Plan: {document['plan_refusal']}", ""]
    lines.append("Steps")
    for step in document["steps"]:
        titles = ", ".join(member["title"] for member in step["members"])
        lines += [f"  {step['label']}: {titles}", f"    {step['note']}"]
    if manifest["outputs"]:
        lines += ["", "Outputs"]
        lines += [f"  {o['artifact_ref']}  {o['description']}" for o in manifest["outputs"]]
    if manifest.get("try"):
        lines += ["", "Try it", f"  input: {manifest['try']['input']}"]
        lines += [f"  {command}" for command in manifest["try"]["commands"]]
    if document["examples"]:
        lines += ["", "Examples"]
        for example in document["examples"]:
            state = example["currency"] or ("present" if example["present"] else "not in store")
            lines.append(f"  {example['id']}  {example['title']} [{example['status']}, {state}]")
    if manifest["related"]:
        lines += ["", "Related: " + ", ".join(manifest["related"])]
    return "\n".join(lines) + "\n"
