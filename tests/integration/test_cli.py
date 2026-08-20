from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from stage_gen.capabilities import CapabilityArtifactResult
from stage_gen.interfaces.cli import main
from stage_gen.recipes.base import StageContext


class CliRuntime:
    def __init__(self) -> None:
        self.phases: list[str] = []
        self.inputs: list[dict[str, object]] = []

    async def run_scrolling_preview_stage(
        self, stage_name: str, context: StageContext
    ) -> tuple[str, ...]:
        self.phases.append(stage_name)
        self.inputs.append(dict(context.input))
        path = context.run_dir / f"{stage_name}.txt"
        path.write_text(stage_name, encoding="utf-8")
        return (str(path),)

    async def generate_image(self, **_kwargs: object) -> CapabilityArtifactResult:
        raise NotImplementedError

    async def remove_background(self, **_kwargs: object) -> CapabilityArtifactResult:
        raise NotImplementedError

    async def generate_music(self, **_kwargs: object) -> CapabilityArtifactResult:
        raise NotImplementedError


def test_cli_offline_surfaces_and_legacy_prompt(monkeypatch: object, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline")  # type: ignore[attr-defined]
    monkeypatch.setenv("OUT_DIR", str(tmp_path))  # type: ignore[attr-defined]
    output = StringIO()
    assert main(["recipes"], stdout=output) == 0
    assert "scrolling-preview" in output.getvalue()
    output = StringIO()
    assert main(["benchmark", "smoke"], stdout=output) == 0
    assert '"ok": true' in output.getvalue()
    output = StringIO()
    assert (
        main(
            ["original", "neutral", "ruins", "--transparency", "chroma"],
            runtime=CliRuntime(),
            stdout=output,
        )
        == 0
    )
    assert "stage-gen: done recipe=scrolling-preview" in output.getvalue()


@pytest.mark.parametrize(
    ("suffix", "document"),
    [
        (
            ".json",
            json.dumps(
                {
                    "prompt": "ink-lined moonlit ruins",
                    "theme": {"hostile_action": 3, "threat_disturbance": 2},
                }
            ),
        ),
        (
            ".input",
            json.dumps(
                {
                    "prompt": "ink-lined moonlit ruins",
                    "theme": {"hostile_action": 3, "threat_disturbance": 2},
                }
            ),
        ),
        (
            ".toml",
            'prompt = "ink-lined moonlit ruins"\n\n'
            "[theme]\n"
            "hostile_action = 3\n"
            "threat_disturbance = 2\n",
        ),
    ],
)
def test_cli_input_accepts_json_and_toml_theme_documents(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    suffix: str,
    document: str,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    input_path = tmp_path / f"generation{suffix}"
    input_path.write_text(document, encoding="utf-8")
    runtime = CliRuntime()
    output = StringIO()

    assert (
        main(
            ["generate", "--input", str(input_path), "--transparency", "chroma"],
            runtime=runtime,
            stdout=output,
        )
        == 0
    )

    assert runtime.phases[0] == "theme-compile"
    assert runtime.phases.count("theme-compile") == 1
    assert runtime.inputs[0]["theme"] == {
        "sexual_content": 0,
        "nudity_exposure": 0,
        "hostile_action": 3,
        "injury_detail": 0,
        "substance_depiction": 0,
        "threat_disturbance": 2,
    }
    assert "stages=7" in output.getvalue()


def test_doctor_consumes_cwd_dotenv_without_exposing_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("OPENROUTER_API_KEY", "FAL_KEY", "_STAGE_GEN_DISABLE_DOTENV"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=doctor-openrouter\nFAL_KEY=doctor-fal\n",
        encoding="utf-8",
    )
    output = StringIO()

    assert main(["doctor", "--json"], stdout=output) == 0

    rendered = output.getvalue()
    report = json.loads(rendered)
    assert report["ok"] is True
    assert report["capabilities"] == {"openrouter": True, "fal": True}
    assert "doctor-openrouter" not in rendered
    assert "doctor-fal" not in rendered
