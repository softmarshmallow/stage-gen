"""Repository documentation, policy, and publication gate."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.media_rights import check_generated_media_publication

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class DocsCheckResult:
    failures: tuple[str, ...]
    markdown_count: int
    text_count: int
    media_count: int


def _walk_files(path: Path, suffixes: frozenset[str]) -> list[Path]:
    if not path.exists():
        return []
    if path.is_file():
        return [path] if path.suffix in suffixes else []
    files: list[Path] = []
    for candidate in sorted(path.rglob("*")):
        if any(part in {".next", "node_modules", "public"} for part in candidate.parts):
            continue
        if candidate.is_file() and candidate.suffix in suffixes:
            files.append(candidate)
    return files


def run_docs_check(repo: Path = REPOSITORY_ROOT) -> DocsCheckResult:
    doctrine = [
        repo / "README.md",
        repo / "CONTRIBUTING.md",
        repo / "ARCHITECTURE.md",
        repo / "MISSION.md",
        repo / "LOOP_PROMPT.md",
    ]
    governance = [repo / "AGENTS.md", repo / "TODO.md"]
    prompt_fixtures = [repo / "fixtures/prompts.txt", repo / "fixtures/styles.txt"]
    concept_markdown = [
        path
        for path in _walk_files(repo / "concept-studio", frozenset({".md"}))
        if "workspaces" not in path.relative_to(repo / "concept-studio").parts
    ]
    markdown = [
        *[path for path in doctrine if path.exists()],
        *_walk_files(repo / "docs", frozenset({".md"})),
        *concept_markdown,
    ]
    failures: list[str] = []

    publication = check_generated_media_publication(
        repo, repo / "docs/generated-media-inventory.json"
    )
    failures.extend(f"generated-media: {failure}" for failure in publication.failures)

    env_example = (repo / ".env.example").read_text(encoding="utf-8")
    env_assignments = dict(re.findall(r"^([A-Z][A-Z0-9_]*)=(.*)$", env_example, re.MULTILINE))
    consumed_env_names: set[str] = set()
    for source_path in (
        repo / "src/stage_gen/config.py",
        repo / "src/stage_gen/recipes/scrolling_preview/cache.py",
    ):
        consumed_env_names.update(
            re.findall(r"""["']([A-Z][A-Z0-9_]*)["']""", source_path.read_text(encoding="utf-8"))
        )
    web_env_source = (repo / "web/lib/shell/runs.ts").read_text(encoding="utf-8")
    consumed_env_names.update(re.findall(r"process\.env\.([A-Z][A-Z0-9_]*)", web_env_source))
    for name in sorted(consumed_env_names):
        if name not in env_assignments:
            failures.append(f".env.example: missing Python/web config name {name}")
    if env_assignments.get("TRANSPARENCY_MODE") != "ai":
        failures.append(".env.example: TRANSPARENCY_MODE must document the ai default")
    for secret_name in ("OPENROUTER_API_KEY", "FAL_KEY"):
        if env_assignments.get(secret_name, "") != "":
            failures.append(f".env.example: {secret_name} must remain blank")

    link_pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    for markdown_file in markdown:
        source = markdown_file.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(source):
            target = raw_target.strip()
            if not target or re.match(r"^(?:https?:|mailto:|#)", target):
                continue
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not (markdown_file.parent / target).resolve().exists():
                relative = markdown_file.relative_to(repo).as_posix()
                failures.append(f"{relative}: missing link {raw_target}")

    text_files: list[Path] = []
    for path in [
        *doctrine,
        *governance,
        *prompt_fixtures,
        *concept_markdown,
        repo / "docs",
        repo / "web",
    ]:
        text_files.extend(
            _walk_files(
                path, frozenset({".md", ".txt", ".ts", ".tsx", ".mjs", ".js", ".jsx", ".cjs"})
            )
        )
    text_files = sorted(dict.fromkeys(text_files))
    stale_patterns = (
        ("legacy gateway key", re.compile("_".join(("AI", "GATEWAY", "API", "KEY")))),
        ("legacy gateway URL", re.compile(r"ai-gateway\.vercel\.sh")),
        ("legacy gateway name", re.compile(r"Vercel AI Gateway", re.IGNORECASE)),
        ("legacy gateway shorthand", re.compile(r"vercel[-\s]+ai[-\s]+gateway", re.IGNORECASE)),
        ("legacy pipeline workspace", re.compile(r"pipeline/")),
        ("legacy recording directory", re.compile(r"fixtures/bgm", re.IGNORECASE)),
        ("legacy curated recording claim", re.compile(r"BGM\s+is\s+curated", re.IGNORECASE)),
        ("legacy no-audio rule", re.compile(r"do\s+not\s+add\s+audio\s+generation", re.IGNORECASE)),
        ("pinned browser engine rule", re.compile(r"do\s+not\s+replace\s+Phaser", re.IGNORECASE)),
        ("private absolute path", re.compile(r"/Users/[A-Za-z0-9._-]+/")),
        (
            "retired synthetic showcase description",
            re.compile(r"original\s+synthetic\s+fixture\s+assets", re.IGNORECASE),
        ),
        (
            "retired synthetic showcase video digest",
            re.compile(r"ec3c200b40ccd12521b5535ed46a3b7256ec1dc4fee1acfde2ec95c1540e694c"),
        ),
        (
            "retired synthetic showcase poster digest",
            re.compile(r"6da7281ac29f91f20cb65099088af357420906946bdfde0df7974ec8e844bdec"),
        ),
        (
            "retired synthetic showcase attestation",
            re.compile(r"independent-visual-attestation-gameplay-showcase-2026-08-16"),
        ),
        (
            "unconditional exact-key background rule",
            re.compile(
                r"\b(?:all|every)\s+(?:sprite|transparent|transparency-producing)[^\n]*(?:magenta|#FF00FF)",
                re.IGNORECASE,
            ),
        ),
        (
            "automatic chroma fallback",
            re.compile(
                r"(?:automatically|silently)\s+(?:fall(?:s|ing)?\s+back|switch(?:es|ing)?)\s+to\s+chroma",
                re.IGNORECASE,
            ),
        ),
    )
    account_funding = re.compile(r"\bTOP_UP\b")
    for text_file in text_files:
        source = text_file.read_text(encoding="utf-8")
        relative = text_file.relative_to(repo).as_posix()
        for label, pattern in stale_patterns:
            if pattern.search(source):
                failures.append(f"{relative}: {label}")
        if text_file != repo / "TODO.md" and account_funding.search(source):
            failures.append(f"{relative}: account-specific funding note outside TODO.md")

    imitation_patterns = (
        re.compile(r"\bin the style of\b", re.IGNORECASE),
        re.compile(r"\bstyle of\b", re.IGNORECASE),
        re.compile(r"\binspired by\b", re.IGNORECASE),
        re.compile(r"""\blike\s+["'A-Z]"""),
        re.compile(r"""\bmeets\s+["'A-Z]"""),
    )
    for policy_file in [*prompt_fixtures, repo / "web/app/Picker.tsx"]:
        if not policy_file.exists():
            continue
        source = policy_file.read_text(encoding="utf-8")
        if any(pattern.search(source) for pattern in imitation_patterns):
            failures.append(
                f"{policy_file.relative_to(repo).as_posix()}: imitation-style prompt language"
            )
    for fixture in prompt_fixtures:
        if not fixture.exists():
            continue
        lines = [
            line.strip()
            for line in fixture.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("- ")
        ]
        if fixture.name == "prompts.txt" and any(
            not line.startswith("- Create an original ") for line in lines
        ):
            failures.append(
                "fixtures/prompts.txt: every preset must explicitly request an original result"
            )
        if fixture.name == "styles.txt" and any(
            re.search(r"""["'()]|\b(?:game|film|studio|artist)\b""", line, re.IGNORECASE)
            for line in lines
        ):
            failures.append(
                "fixtures/styles.txt: style hints must remain neutral property descriptions"
            )

    readme = (repo / "README.md").read_text(encoding="utf-8")
    if (
        re.search(r"\bgeneral\b", readme, re.IGNORECASE) is None
        or re.search(r"optional web-based scrolling-game\s+preview", readme, re.IGNORECASE) is None
    ):
        failures.append("README.md: missing general-core / optional-preview framing")

    media_policy = (repo / "docs/generated-media-publication.md").read_text(encoding="utf-8")
    policy_requirements = (
        (
            re.compile(r"runtime-unreviewed.*repository-approved", re.IGNORECASE | re.DOTALL),
            "runtime/repository status boundary",
        ),
        (
            re.compile(r"provenance.{0,160}not a redistribution grant", re.IGNORECASE | re.DOTALL),
            "provenance rights boundary",
        ),
        (
            re.compile(
                r"SynthID.{0,220}not been independently verified", re.IGNORECASE | re.DOTALL
            ),
            "SynthID verification status",
        ),
        (
            re.compile(r"BSD-3-Clause.{0,180}CC0", re.IGNORECASE | re.DOTALL),
            "no blanket source/output license claim",
        ),
    )
    for pattern, label in policy_requirements:
        if pattern.search(media_policy) is None:
            failures.append(f"docs/generated-media-publication.md: missing {label}")

    required_contracts = (
        (
            "README.md",
            re.compile(r"default[^\n]*--transparency ai", re.IGNORECASE),
            "AI CLI default",
        ),
        (
            "README.md",
            re.compile(r"--transparency chroma", re.IGNORECASE),
            "explicit chroma CLI fallback",
        ),
        (
            "README.md",
            re.compile(r"FAL_KEY.{0,160}not\s+required", re.IGNORECASE | re.DOTALL),
            "conditional FAL_KEY requirement",
        ),
        (
            "docs/spec/agent-prompts.md",
            re.compile(r"neutral gr(?:a|e)y|naturally isolated", re.IGNORECASE),
            "AI isolation prompt",
        ),
        (
            "docs/spec/agent-prompts.md",
            re.compile(r"exact `#FF00FF`", re.IGNORECASE),
            "exact degraded fallback key",
        ),
        (
            "docs/spec/agent-prompts.md",
            re.compile(r"opaque[^\n]*(?:neither|omit|bypass)", re.IGNORECASE),
            "opaque exclusion",
        ),
        (
            "docs/web-preview.md",
            re.compile(r"input\.transparency_mode"),
            "run-summary strategy field",
        ),
        (
            "docs/web-preview.md",
            re.compile(r"HTTP start body is `\{ prompt, transparency_mode \}`"),
            "web run-request strategy field",
        ),
        (
            "web/app/Picker.tsx",
            re.compile(r'''aria-label="AI background removal"'''),
            "background removal control",
        ),
        (
            "web/lib/shell/transparency.ts",
            re.compile(r'''DEFAULT_TRANSPARENCY_MODE[^\n]*= "ai"'''),
            "web default",
        ),
    )
    for relative, pattern, label in required_contracts:
        if pattern.search((repo / relative).read_text(encoding="utf-8")) is None:
            failures.append(f"{relative}: missing {label}")

    return DocsCheckResult(
        failures=tuple(failures),
        markdown_count=len(markdown),
        text_count=len(text_files),
        media_count=publication.media_count,
    )


def main() -> int:
    result = run_docs_check()
    if result.failures:
        for failure in result.failures:
            print(f"docs-check: {failure}", file=sys.stderr)
        return 1
    print(
        "docs-check: ok "
        f"({result.markdown_count} markdown files, {result.text_count} public text files, "
        f"{result.media_count} generated-media files)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
