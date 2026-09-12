"""Public CLI checkpoint stop/resume with real graph, recovery and mock provider HTTP.

Synthetic upstream decisions and an in-process frozen child keep this test offline.
No Blender, credentials, remote task, or semantic quality claim is involved.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import pytest

from gnode import Graph, Node, NodeExecutionContext, NodeExecutionResult, NodeTypeRegistry
from stage_gen.components.character_3d import package_resources
from stage_gen.components.character_3d.budget_pool import BudgetPool
from stage_gen.components.character_3d.io import canonical_digest, digest, read_json, write_json
from stage_gen.orchestration.character_3d import launch
from stage_gen.orchestration.character_3d.provider_execution import ProviderRigExecutor
from stage_gen.recipes.character_3d.provider_runner import ProviderBriefRun, RigExecutor
from stage_gen.recipes.character_3d.qualification import Trial, collect_qualification
from stage_gen.recipes.character_3d.runner import node_type
from tests.unit.recipes.character_3d.test_character_provider_execution import factory
from tests.unit.recipes.character_3d.test_character_provider_flow import experiment
from tests.unit.recipes.character_3d.test_character_provider_rig import Provider, glb_fixture

JsonObject = dict[str, Any]


class OfflinePipeline(ProviderBriefRun):
    """Keep production topology/submission; replace upstream art and local rendering."""

    provider: ClassVar[Provider]
    prior_agent_cost: ClassVar[str] = "0"
    executor: ProviderRigExecutor | None = None

    def provider_key(self, name: str) -> str:
        assert name in {"OPENROUTER_API_KEY", "TRIPO_API_KEY"}
        return "synthetic-test-key"

    def rig_executor(self) -> RigExecutor:
        if self.executor is None:
            self.executor = ProviderRigExecutor(self, provider_factory=factory(self.provider))
        return self.executor

    def build_graph(self) -> Graph:
        graph = super().build_graph()
        original = self.registry
        self.registry = NodeTypeRegistry()
        seen = set()
        submit_type = node_type("provider_rig_submit", operation="body_rig").type_id
        for node in graph.nodes:
            if node.type_id in seen:
                continue
            seen.add(node.type_id)
            self.registry.register(
                original.node_type(node.type_id),
                self.submit_rig if node.type_id == submit_type else self.fixture_stage,
            )
        return graph

    async def fixture_stage(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        del context
        source = {"path": "source.glb", "sha256": digest(self.input_root / "source.glb")}
        if node.node_id == "references_01" and self.prior_agent_cost != "0":
            pool = self.require_run_budget()
            identity = canonical_digest(self.experiment)
            pool.reserve("agent_loop", identity, self.experiment["limits"]["agent_max_usd"])
            pool.mark_started("agent_loop", identity)
            pool.reserve("synthetic_generation", "b" * 64, "2")
            pool.mark_started("synthetic_generation", "b" * 64)
            pool.settle(
                "synthetic_generation",
                "b" * 64,
                known_actual_usd="0.30",
                unresolved_liability_usd="0",
                outcome="completed",
            )
            cost = self.prior_agent_cost
            write_json(
                self.run_root / "ledger/ledger.json",
                {
                    "dispatch_count": 1,
                    "known_cost_usd": cost,
                    "liability_usd": cost,
                    "halt_reason": None,
                    "events": [],
                    "started_at_unix": 1000,
                    "limits": {"mock_only": True},
                    "attempts": [
                        {
                            "attempt_id": "synthetic-prior-charge",
                            "status": "response",
                            "charge_status": "reported",
                            "known_cost_usd": cost,
                            "liability_usd": cost,
                            "request": {"episode_id": node.node_id},
                        }
                    ],
                },
            )
        if node.node_id == "assembly_admit":
            self.studio.assets["fixture_assembly"] = {"source": source, "role": "assembly"}
            self.studio.admitted_assembly = "fixture_assembly"
        if node.node_id == "rig_01":
            receipt = await self.rig_executor().collect(self.records["rig_submit_01"])
            return self.result(node, receipt, cost=float(receipt["known_cost_usd"]))
        return self.result(
            node,
            {"status": "synthetic_fixture", "accepted": True, "source_sha256": source["sha256"]},
        )

    def successful_outcome_status(self) -> str:
        return "offline_fixture_complete"


def child_arguments(command: Sequence[str]) -> argparse.Namespace:
    """Parse the actual forwarded options, without launching a second test process."""
    assert list(command[:5]) == [sys.executable, "-s", "-P", "-m", launch.__name__]
    parser = argparse.ArgumentParser()
    for name in ("experiment", "input-root", "run-root", "blender", "dotenv"):
        parser.add_argument("--" + name, type=Path)
    for name in ("frozen", "live", "prepare-only", "resume", "stop-after-provider-submit"):
        parser.add_argument("--" + name, action="store_true")
    parser.add_argument("--admission-mode")
    parser.add_argument("--support-record")
    parser.add_argument("--support-record-sha256")
    return parser.parse_args(command[5:])


class FrozenChild:
    def __init__(self, args: argparse.Namespace, monkeypatch: pytest.MonkeyPatch) -> None:
        self.args = args
        self.monkeypatch = monkeypatch
        self.returncode: int | None = None

    async def wait(self) -> int:
        with self.monkeypatch.context() as patch:
            patch.setattr(
                launch,
                "LAUNCH_PATH",
                self.args.run_root / "code/stage_gen/orchestration/character_3d/launch.py",
            )
            self.returncode = await launch.execute(self.args)
            return self.returncode

    def terminate(self) -> None:
        raise AssertionError("A committed boundary stop must finish without a process signal")

    def kill(self) -> None:
        raise AssertionError("Offline child must never be killed")


@pytest.fixture
def cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[str], Provider, list[argparse.Namespace]]:
    request = experiment()
    # The production gate also runs from an editable source checkout. Only that
    # explicit layout gets synthetic inventory bytes; installed wheels retain
    # their real RECORD validation and cannot fall back after corruption.
    source_root = package_resources.installed_root()
    if source_root.name == "src" and (source_root.parent / "pyproject.toml").is_file():
        payloads = [
            (path.relative_to(source_root).as_posix(), path.read_bytes())
            for folder in ("gnode", "stage_gen")
            for path in sorted((source_root / folder).rglob("*"))
            if path.is_file() and path.suffix in {".py", ".json", ".md"}
        ]
        for alias, source_ref in sorted(package_resources.package_map()["aliases"].items()):
            payload = (source_root / source_ref).read_bytes()
            if alias.startswith("worker/") and alias.endswith(".py"):
                payload = package_resources._worker_bootstrap(Path(alias).stem)
            payloads.append((alias, payload))
        monkeypatch.setattr(package_resources, "_installed_payloads", lambda: payloads)
    request["limits"]["max_review_rounds"] = 1
    request["rigging"]["poll_interval_seconds"] = 1
    request["rigging"]["reservation_usd"] = "1"
    config = tmp_path / "experiment.json"
    write_json(config, request)
    glb_fixture(tmp_path / "source.glb")
    provider = Provider(payload=glb_fixture(tmp_path / "rigged-fixture.glb", rigged=True))
    monkeypatch.setattr(OfflinePipeline, "provider", provider, raising=False)
    monkeypatch.setattr(launch, "run_class", lambda *_args, **_kwargs: OfflinePipeline)
    monkeypatch.setenv("STAGE_GEN_RUN_LIVE", "1")
    children: list[argparse.Namespace] = []

    async def spawn(*command: str, **kwargs: Any) -> FrozenChild:
        args = child_arguments(command)
        assert kwargs["cwd"] == args.run_root / "code"
        assert kwargs["env"]["PYTHONPATH"] == str(args.run_root / "code")
        children.append(args)
        return FrozenChild(args, monkeypatch)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    arguments = [
        "stage-gen-character",
        "--experiment",
        str(config),
        "--input-root",
        str(tmp_path),
        "--run-root",
        str(tmp_path / "run"),
        "--blender",
        sys.executable,
        "--admission-mode",
        "development",
        "--live",
    ]
    return arguments, provider, children


def invoke(monkeypatch: pytest.MonkeyPatch, arguments: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(SystemExit) as stopped:
        launch.main()
    assert isinstance(stopped.value.code, int)
    return stopped.value.code


@pytest.mark.parametrize("prior_agent_cost", ["0", "0.40"])
def test_public_cli_committed_stop_then_frozen_resume_is_get_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cli: tuple[list[str], Provider, list[argparse.Namespace]],
    prior_agent_cost: str,
) -> None:
    arguments, provider, children = cli
    monkeypatch.setattr(OfflinePipeline, "prior_agent_cost", prior_agent_cost)
    assert invoke(monkeypatch, [*arguments, "--stop-after-provider-submit"]) == 0
    run = tmp_path / "run"
    before = (run / "outcome.json").read_bytes()
    outcome = read_json(run / "outcome.json")
    summary = read_json(run / "summary.json")
    assert outcome["status"] == "development_checkpoint_stopped"
    assert outcome["accepted"] is False and outcome["unattended"] is False
    assert outcome["qualification_eligible"] is False
    assert summary["ok"] is True
    assert children[0].stop_after_provider_submit is True and children[0].frozen is True
    selected = {node["node_id"] for node in summary["nodes"]}
    assert "rig_submit_01" in selected and "rig_01" not in selected
    assert not (run / "recovery/rig_01.started.json").exists()
    committed = run / "recovery/rig_submit_01.completed.json"
    committed_bytes = committed.read_bytes()
    receipt = read_json(run / "nodes/rig_submit_01.json")
    assert receipt["task_id"] == "rig-task" == outcome["stop_checkpoint"]["task_id"]
    assert receipt["plan"]["plan_sha256"] == outcome["stop_checkpoint"]["plan_sha256"]
    submitted = tmp_path / receipt["submission_snapshot"]["path"]
    original_files = ProviderRigExecutor._inventory(submitted)
    assert original_files == receipt["submission_snapshot"]["files"]
    saved_experiment = (run / "experiment.json").read_bytes()
    saved_runtime = (run / "runtime.json").read_bytes()
    account = outcome["accounting"]["inclusive_run_budget"]
    assert account["closed"] is False
    assert Decimal(account["liability_usd"]) == (
        Decimal("13.30") if prior_agent_cost != "0" else Decimal("1")
    )
    parent = BudgetPool(tmp_path / "budget", "fixture", "100").snapshot()
    assert parent["liability_usd"] == "61" and parent["closed"] is False
    assert provider.count("/animations/rig") == 1
    assert not any(path.endswith("/tasks/rig-task") for _, path, _ in provider.calls)
    calls_at_stop = len(provider.calls)
    stopped_row = collect_qualification(tmp_path, [Trial("fixture", "run", "fresh")])["rows"][0]
    assert stopped_row["result"] == "development_checkpoint_stopped"
    assert stopped_row["accepted"] is False and stopped_row["fresh_accepted"] is False
    assert stopped_row["decision_kind"] == "development_controlled"
    projected = stopped_row["accounting"]
    assert projected["unsettled_agent_known_cost_usd"] == prior_agent_cost
    assert Decimal(projected["known_cost_usd"]) == (
        Decimal("0.70") if prior_agent_cost != "0" else Decimal("0")
    )
    if prior_agent_cost != "0":
        assert Decimal(projected["settled_inclusive_known_cost_usd"]) == Decimal("0.30")
        assert projected["reconciled"] is False and projected["closed"] is False
        altered = copy.deepcopy(outcome)
        altered["accounting"]["inclusive_run_budget"]["reservations"]["agent_loop"][
            "amount_usd"
        ] = "0.01"
        from stage_gen.recipes.character_3d.qualification import EvidenceError, _accounting

        with pytest.raises(EvidenceError, match="hold_does_not_cover"):
            _accounting(run, altered, read_json(run / "experiment.json"))

    assert invoke(monkeypatch, [*arguments, "--resume"]) == 0
    assert children[1].resume is True and children[1].stop_after_provider_submit is False
    assert provider.count("/animations/rig") == 1
    assert all(method == "GET" for method, _, _ in provider.calls[calls_at_stop:])
    assert any(path.endswith("/tasks/rig-task") for _, path, _ in provider.calls[calls_at_stop:])
    assert (run / "outcome.json").read_bytes() == before
    assert committed.read_bytes() == committed_bytes
    assert (run / "experiment.json").read_bytes() == saved_experiment
    assert (run / "runtime.json").read_bytes() == saved_runtime
    assert ProviderRigExecutor._inventory(submitted) == original_files
    resumed_path = next((run / "invocations").glob("*_resume_*/outcome.json"))
    resumed = read_json(resumed_path)
    assert resumed["resumed"] is True and resumed["unattended"] is False
    assert resumed["qualification_eligible"] is False
    assert resumed["accounting"]["inclusive_run_budget"]["closed"] is True
    expected_cost = Decimal("0.95") if prior_agent_cost != "0" else Decimal("0.25")
    assert (
        Decimal(resumed["accounting"]["inclusive_run_budget"]["known_actual_usd"]) == expected_cost
    )
    assert resumed["accounting"]["inclusive_run_budget"]["unresolved_liability_usd"] == "0"
    parent_after = BudgetPool(tmp_path / "budget", "fixture", "100").snapshot()
    assert (
        Decimal(parent_after["liability_usd"])
        == Decimal(parent_after["known_actual_usd"])
        == expected_cost
    )
    resumed_summary = read_json(resumed_path.with_name("summary.json"))
    trace = next(node for node in resumed_summary["nodes"] if node["node_id"] == "rig_submit_01")
    assert trace["cache"] == "hit" and trace["provider_operations"] == 0


@pytest.mark.parametrize(
    "extra,mode",
    [
        ([], "supported"),
        ([], "qualification"),
        (["--prepare-only"], "development"),
        (["--resume"], "development"),
    ],
)
def test_stop_refused_before_output_or_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cli: tuple[list[str], Provider, list[argparse.Namespace]],
    extra: list[str],
    mode: str,
) -> None:
    arguments, provider, children = cli
    arguments = arguments.copy()
    arguments[arguments.index("development")] = mode
    assert invoke(monkeypatch, [*arguments, "--stop-after-provider-submit", *extra]) == 1
    assert not (tmp_path / "run").exists()
    assert provider.calls == [] and children == []


@pytest.mark.parametrize("mutation", ["marker", "checkpoint", "input", "started_collection"])
def test_changed_or_uncommitted_evidence_refuses_resume_without_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cli: tuple[list[str], Provider, list[argparse.Namespace]],
    mutation: str,
) -> None:
    arguments, provider, _ = cli
    assert invoke(monkeypatch, [*arguments, "--stop-after-provider-submit"]) == 0
    run = tmp_path / "run"
    if mutation == "marker":
        (run / "recovery/development-stop.json").unlink()
    elif mutation == "checkpoint":
        path = run / "recovery/rig_submit_01.completed.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "input":
        path = tmp_path / "source.glb"
        path.write_bytes(path.read_bytes() + b" ")
    else:
        write_json(run / "recovery/rig_01.started.json", {"node_id": "rig_01"})
    previous_calls = copy.deepcopy(provider.calls)
    before = (run / "outcome.json").read_bytes()
    assert invoke(monkeypatch, [*arguments, "--resume"]) == 1
    assert provider.calls == previous_calls
    assert (run / "outcome.json").read_bytes() == before
