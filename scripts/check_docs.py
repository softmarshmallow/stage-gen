"""Repository documentation, policy, and publication gate."""

from __future__ import annotations

import re
import subprocess
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


def _web_files(repo: Path, suffixes: frozenset[str]) -> list[Path] | None:
    """The web workspace's own files: tracked, plus untracked ones a commit would take.

    Build output, installs and staged catalogs (``.next``, ``out``, ``node_modules``,
    ``.catalog``, copied example media) are ignored, so they are never scanned. None when
    git cannot answer, which the caller reports instead of passing an empty walk.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "web"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return sorted(
        repo / entry
        for entry in completed.stdout.split("\0")
        if entry and Path(entry).suffix in suffixes and (repo / entry).is_file()
    )


CONSUMER_SPECS = (
    "godot/games/ember_hollow/docs/generation-v1.md",
    "godot/games/ember_hollow/docs/crafting.md",
    "godot/games/ember_hollow/docs/ground.md",
    "godot/games/ember_hollow/docs/world.md",
    "godot/games/ember_hollow/docs/seasons.md",
    "godot/games/_shared/docs/formats/ui-atlas.md",
    "godot/games/_shared/docs/formats/view-and-style-taxonomy.md",
    "godot/games/the_grain/docs/case.md",
    "godot/games/the_grain/docs/pointclick-room.md",
    "godot/games/_shared/docs/formats/host-contract.md",
    "godot/games/_shared/docs/formats/dialogue-and-cutscene-sequences.md",
    "godot/games/_shared/docs/formats/authored-contract-schema.md",
    "godot/games/iron_petal_unit/docs/fx.md",
    "godot/games/iron_petal_unit/docs/runner.md",
    "godot/games/bellweather/docs/map-generation-contract.md",
    "godot/games/bellweather/docs/generation-pipeline.md",
    "godot/games/_shared/docs/formats/ui.md",
    "godot/games/ember_hollow/docs/shell.md",
    "godot/games/the_grain/docs/dialogue-scene-assets.md",
)

CHECKED_BY_PATTERN = re.compile(r"^> \*\*Checked by:\*\* (.+)$", re.MULTILINE)

#: Where each workflow keeps its prose beside its code: page.mdx, contract.md, input notes.
WORKFLOWS_SOURCE = "src/stage_gen/workflows"
PROMPT_FIXTURES = (
    "src/stage_gen/resources/fixtures/prompts.txt",
    "src/stage_gen/resources/fixtures/styles.txt",
)

# The words decision 0071 retired from product prose, and where the lint reads. A retired word
# survives only where it is a frozen persisted string or a path: inside code spans and fenced
# blocks, in a link target, or in the glossary sections that list the retired and frozen words.
RETIRED_TERMS = re.compile(
    r"\b(?:recipes?|harness|showcase|(?:web|run) viewer)\b"
    # The gnode epic (decision 0072) retired the stage-gen command line and the old engine.
    r"|\bstage-gen (?:list|show|plan|run|inspect|view|example|catalog|capability|models|env)\b"
    r"|\bstage_gen\.pipeline\b|\bGraphExecutor\b|\bGraphBuilder\b|\brekey_v1_runs\b",
    re.IGNORECASE,
)
RETIRED_TERM_EXEMPT_PHRASES = re.compile(r"\b(?:rig|crafting) recipes?\b", re.IGNORECASE)
RETIRED_TERM_DOCUMENTS = (
    "README.md",
    "ARCHITECTURE.md",
    "CONTRIBUTING.md",
    "VERIFICATION.md",
    "docs/README.md",
    "docs/getting-started.md",
    "docs/glossary.md",
    "docs/viewer.md",
    "docs/site.md",
    "docs/spec/gnode-rings.md",
    ".agents/skills/asset-pipeline/SKILL.md",
    "docs/guide/README.md",
    "docs/guide/01-getting-started.md",
    "docs/guide/02-workflow-file.md",
    "docs/guide/03-nodes.md",
    "docs/guide/04-cost-and-cache.md",
    "docs/guide/05-views.md",
    "docs/guide/06-running.md",
    "docs/guide/07-annotations-and-judges.md",
)
GLOSSARY_EXEMPT_SECTIONS = ("## Retired terms", "## Frozen persisted strings")
# The site's own sources, whose strings and JSX text readers see (page titles, headings,
# breadcrumbs). Comments are stripped first: they may name what a port replaced.
RETIRED_TERM_SITE_SOURCES = tuple(
    f"web/site/{folder}" for folder in ("app", "components", "blocks", "lib")
)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<![:\w\"'])//.*$", re.MULTILINE)


def ignored_paths(repo: Path, candidates: set[str]) -> frozenset[str]:
    """Which of these repository-relative paths git deliberately ignores.

    One `check-ignore` for the whole set rather than one per path. Anything that
    goes wrong — no git, no repository, a tarball rather than a checkout —
    answers "none are ignored", which is the strict reading this rule had
    before the exemption existed. A gate that cannot tell should refuse rather
    than wave things through.
    """
    if not candidates:
        return frozenset()
    # Each candidate is asked about twice, as a file and as a directory. A
    # pattern that ends in "/" ignores directories only, and `check-ignore`
    # answers for a bare name by looking at what is actually on disk — so
    # `concept-studio/workspaces` matched on the machine that had the directory
    # and not in a fresh clone, which is the very machine-dependence this
    # exemption was added to remove.
    probes = sorted({candidate for candidate in candidates} | {f"{c}/" for c in candidates})
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "--stdin"],
            cwd=repo,
            input="\n".join(probes),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return frozenset()
    # 0 = some ignored, 1 = none ignored, anything else = git could not answer.
    if completed.returncode not in (0, 1):
        return frozenset()
    return frozenset(
        line.strip().rstrip("/") for line in completed.stdout.splitlines() if line.strip()
    )


def check_spec_checkers(repo: Path) -> list[str]:
    """Every specification says what checks it, and the claim is true.

    A spec under ``docs/spec``, a game-owned consumer spec, or a workflow's ``contract.md``
    opens with ``> **Checked by:** `tests/...`, ...`` naming
    the test modules that read it, or ``none.`` when nothing does. A named test must
    exist, live under ``tests/`` or be a Bun test under ``web/``, and actually name the spec,
    so a document cannot borrow a checker it never had; ``none`` is a statement a
    reader can act on rather than a pointer that quietly rotted.
    """

    failures: list[str] = []
    for spec in sorted(
        [
            *_walk_files(repo / "docs/spec", frozenset({".md"})),
            *(repo / ref for ref in CONSUMER_SPECS if (repo / ref).is_file()),
            *sorted((repo / WORKFLOWS_SOURCE).glob("*/contract.md")),
        ]
    ):
        relative = spec.relative_to(repo).as_posix()
        source = spec.read_text(encoding="utf-8")
        match = CHECKED_BY_PATTERN.search(source)
        if match is None:
            failures.append(f"{relative}: no `> **Checked by:**` line")
            continue
        claim = match.group(1).strip()
        if claim == "none.":
            continue
        named = re.findall(r"`([^`]+)`", claim)
        if not named:
            failures.append(f"{relative}: Checked by names no test in backticks")
        spec_ref = relative.removeprefix("docs/")
        for test_ref in named:
            is_test = (test_ref.startswith("tests/") and test_ref.endswith(".py")) or (
                test_ref.startswith("web/") and test_ref.endswith((".test.ts", ".test.tsx"))
            )
            if not is_test:
                failures.append(f"{relative}: Checked by names a non-test `{test_ref}`")
                continue
            test_path = repo / test_ref
            if not test_path.is_file():
                failures.append(f"{relative}: Checked by names missing test `{test_ref}`")
                continue
            if spec_ref not in test_path.read_text(encoding="utf-8", errors="ignore"):
                failures.append(
                    f"{relative}: Checked by names `{test_ref}`, which never names the spec"
                )
    return failures


def _prose_lines(source: str, *, exempt_sections: tuple[str, ...] = ()) -> list[tuple[int, str]]:
    """The prose of a Markdown or MDX document, line by line, without its code.

    Fenced blocks, code spans, link targets and HTML comments are blanked out; a line inside
    one of ``exempt_sections`` (a level-2 heading and everything up to the next) is skipped.
    """
    lines: list[tuple[int, str]] = []
    fenced = False
    exempt = False
    for number, line in enumerate(source.splitlines(), start=1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("## "):
            exempt = line.strip() in exempt_sections
        if exempt:
            continue
        text = re.sub(r"`[^`]*`", " ", line)
        text = re.sub(r"\]\([^)]*\)", "]", text)
        text = re.sub(r"<!--.*?-->", " ", text)
        lines.append((number, text))
    return lines


def check_retired_terms(repo: Path) -> list[str]:
    """Product prose speaks decision 0071's vocabulary.

    The doctrine, the cross-cutting docs and every workflow's ``page.mdx`` and ``contract.md``
    are read, and so are the site's sources with their comments stripped. History (decisions,
    plans, research) is not, because it describes what was. A scan that matched no workflow
    prose would prove nothing, so an empty one fails.
    """
    failures: list[str] = []
    workflow_prose = sorted(
        path
        for pattern in ("*/page.mdx", "*/contract.md")
        for path in (repo / WORKFLOWS_SOURCE).glob(pattern)
    )
    if not workflow_prose:
        failures.append(f"{WORKFLOWS_SOURCE}: the retired-term lint matched no page or contract")
    documents = [repo / relative for relative in RETIRED_TERM_DOCUMENTS]
    for document in [*documents, *workflow_prose]:
        if not document.is_file():
            continue
        relative = document.relative_to(repo).as_posix()
        exempt = GLOSSARY_EXEMPT_SECTIONS if relative == "docs/glossary.md" else ()
        for number, text in _prose_lines(
            document.read_text(encoding="utf-8"), exempt_sections=exempt
        ):
            for match in RETIRED_TERMS.finditer(RETIRED_TERM_EXEMPT_PHRASES.sub(" ", text)):
                failures.append(f"{relative}:{number}: retired term '{match.group(0)}'")
    site_sources = [
        path
        for folder in RETIRED_TERM_SITE_SOURCES
        for path in _walk_files(repo / folder, frozenset({".ts", ".tsx"}))
    ]
    for source in site_sources:
        relative = source.relative_to(repo).as_posix()
        code = _BLOCK_COMMENT.sub(
            lambda comment: "\n" * comment.group(0).count("\n"),
            source.read_text(encoding="utf-8"),
        )
        for number, text in enumerate(_LINE_COMMENT.sub("", code).splitlines(), start=1):
            for match in RETIRED_TERMS.finditer(RETIRED_TERM_EXEMPT_PHRASES.sub(" ", text)):
                failures.append(f"{relative}:{number}: retired term '{match.group(0)}'")
    return failures


def run_docs_check(repo: Path = REPOSITORY_ROOT) -> DocsCheckResult:
    doctrine = [
        repo / "README.md",
        repo / "CONTRIBUTING.md",
        repo / "ARCHITECTURE.md",
    ]
    governance = [repo / "AGENTS.md", repo / "TODO.md"]
    prompt_fixtures = [repo / relative for relative in PROMPT_FIXTURES]
    concept_markdown = [
        path
        for path in _walk_files(repo / "concept-studio", frozenset({".md"}))
        if "workspaces" not in path.relative_to(repo / "concept-studio").parts
    ]
    # `TODO.md` is one line per open item, each linking to the decision, plan or
    # spec that holds its context, so it is link-checked like the rest of the
    # documentation rather than only scanned for stale prose.
    # `VERIFICATION.md` names the locked gate and was in no list at all (the May
    # prototype's `DESIGN.md` is a plan under docs/plans now); `CLAUDE.md` is a symlink to
    # `AGENTS.md` and is already governance. The Godot operating manuals are documentation
    # like any other and are held to the same links and paths (decision 0061 makes them the
    # manuals for every genre).
    markdown = [
        *[path for path in doctrine if path.exists()],
        *[path for path in governance if path.exists()],
        *[path for path in (repo / "VERIFICATION.md",) if path.exists()],
        *_walk_files(repo / "docs", frozenset({".md"})),
        *_walk_files(repo / "library", frozenset({".md"})),
        # The presentation package's `history/` holds the request ledger and the
        # reviews written while its games grew up in one workspace; they cite
        # local workspace files and paths as they were. A game's `art/` and
        # `captures/` are ignored local media with their own notes. Everything
        # else under `godot/` is live documentation and is held to the same rules.
        *[
            path
            for path in _walk_files(repo / "godot", frozenset({".md"}))
            if "/history/" not in path.as_posix()
            and not any(
                part in {"art", "captures"} for part in path.relative_to(repo / "godot").parts
            )
        ],
        *concept_markdown,
        # Workflow prose lives beside its code, and a game's example pages beside the game.
        *_walk_files(repo / WORKFLOWS_SOURCE, frozenset({".md", ".mdx"})),
        *_walk_files(repo / "src/stage_gen/components", frozenset({".md"})),
        *_walk_files(repo / "src/stage_gen/pipeline", frozenset({".md"})),
        *[
            path
            for game in sorted((repo / "godot/games").glob("*/examples"))
            for path in _walk_files(game, frozenset({".mdx"}))
        ],
    ]
    failures: list[str] = []

    publication = check_generated_media_publication(
        repo, repo / "docs/generated-media-inventory.json"
    )
    failures.extend(f"generated-media: {failure}" for failure in publication.failures)

    env_example = (repo / ".env.example").read_text(encoding="utf-8")
    env_assignments = dict(re.findall(r"^([A-Z][A-Z0-9_]*)=(.*)$", env_example, re.MULTILINE))
    consumed_env_names: set[str] = set()
    for source_path in (repo / "src/stage_gen/config.py",):
        consumed_env_names.update(
            re.findall(r"""["']([A-Z][A-Z0-9_]*)["']""", source_path.read_text(encoding="utf-8"))
        )
    # The viewer's shell is where it reads its environment; a scan that matched no file
    # would prove nothing, so an empty one fails below with the no-spawn rule.
    for web_env_source in sorted((repo / "web/viewer/lib/shell").glob("*.ts")):
        consumed_env_names.update(
            re.findall(
                r"process\.env\.([A-Z][A-Z0-9_]*)", web_env_source.read_text(encoding="utf-8")
            )
        )
    for name in sorted(consumed_env_names):
        if name not in env_assignments:
            failures.append(f".env.example: missing Python/web config name {name}")
    if env_assignments.get("TRANSPARENCY_MODE") != "native":
        failures.append(".env.example: TRANSPARENCY_MODE must document the native default")
    for secret_name in (
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "FAL_KEY",
        "ELEVENLABS_API_KEY",
    ):
        if env_assignments.get(secret_name, "") != "":
            failures.append(f".env.example: {secret_name} must remain blank")

    # A record and a walked plan are history: they describe what was true when they were
    # written, and the identity contract test exempts them for the same reason. Holding
    # them to today's tree would mean amending a ruling every time the tree moved past it,
    # which `docs/decisions/README.md` forbids outright.
    history_roots = (
        "docs/decisions/",
        "docs/plans/",
        "docs/research/",
        "docs/media/",
        # Authored input documents move unchanged with their digest-bound closures.
        *(
            f"godot/games/{game}/inputs/"
            for game in ("bellweather", "iron_petal_unit", "ember_hollow", "the_grain")
        ),
    )
    link_pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    # A link to a path the repository deliberately ignores is not broken: a
    # game's review notes link the captures they judged and its README the art
    # rounds behind its images, and neither exists in a fresh clone by design.
    # The same exemption the source-path rule below carries, for the same
    # reason; the pre-push hook found 91 such links the first time it gated a
    # clean worktree. A missing tracked target still fails.
    unresolved: list[tuple[str, str, str | None]] = []
    for markdown_file in markdown:
        if markdown_file.relative_to(repo).as_posix().startswith(history_roots):
            continue
        source = markdown_file.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(source):
            target = raw_target.strip()
            if not target or re.match(r"^(?:https?:|mailto:|#)", target):
                continue
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            resolved = (markdown_file.parent / target).resolve()
            if not resolved.exists():
                relative = markdown_file.relative_to(repo).as_posix()
                candidate = (
                    resolved.relative_to(repo.resolve()).as_posix()
                    if resolved.is_relative_to(repo.resolve())
                    else None
                )
                unresolved.append((relative, raw_target, candidate))
    ignored_targets = ignored_paths(
        repo, {candidate for _, _, candidate in unresolved if candidate is not None}
    )
    for relative, raw_target, candidate in unresolved:
        if candidate is not None and candidate in ignored_targets:
            continue
        failures.append(f"{relative}: missing link {raw_target}")

    # Prose that names a source path names one that exists. Two root doctrine
    # documents kept pointing at a recipe package deleted in a rename, and four
    # specifications named modules that never came back from a refactor; a
    # reader trusts a path in backticks more than a sentence, so a wrong one
    # is worse than none. History is exempt — docs/research, docs/media, and
    # the decision and plan records, which describe what was.
    #
    # A path the repository deliberately ignores is exempt too, and it is not
    # the same exemption. `concept-studio/gallery/README.md` says exploratory
    # candidates belong under the *ignored* `concept-studio/workspaces/` tree,
    # and a published review record cites the local files it judged by digest;
    # both are correct, and neither can exist in a fresh clone. Requiring them
    # made this gate pass only on the machine that happened to hold somebody's
    # workspace — which is the failure this rule exists to prevent, pointed the
    # other way. A deleted module is never gitignored, so nothing the rule was
    # written for escapes through here.
    source_path_pattern = re.compile(
        r"`((?:src|web|scripts|tests|apps|concept-studio|godot|library)/[A-Za-z0-9_./-]+?)(?:::[^`]*)?`"
    )
    named: list[tuple[str, str, str]] = []
    for markdown_file in markdown:
        relative = markdown_file.relative_to(repo).as_posix()
        if relative.startswith(history_roots):
            continue
        source = markdown_file.read_text(encoding="utf-8")
        for match in source_path_pattern.findall(source):
            candidate = match.rstrip("/")
            if "*" in candidate or "<" in candidate or "{" in candidate:
                continue
            named.append((relative, match, candidate))
    ignored = ignored_paths(repo, {candidate for _, _, candidate in named})
    for relative, match, candidate in named:
        if candidate in ignored:
            continue
        if not (repo / candidate).exists():
            failures.append(f"{relative}: names missing path `{match}`")

    failures.extend(check_spec_checkers(repo))

    text_suffixes = frozenset({".md", ".txt", ".ts", ".tsx", ".mjs", ".js", ".jsx", ".cjs"})
    text_files: list[Path] = []
    for path in [
        *doctrine,
        *governance,
        *prompt_fixtures,
        *concept_markdown,
        repo / "docs",
        repo / "library",
    ]:
        text_files.extend(_walk_files(path, text_suffixes))
    web_text = _web_files(repo, text_suffixes)
    if web_text is None:
        failures.append("web: git could not list the workspace's files")
    else:
        text_files.extend(web_text)
    text_files = sorted(dict.fromkeys(text_files))
    stale_patterns = (
        ("legacy gateway key", re.compile("_".join(("AI", "GATEWAY", "API", "KEY")))),
        ("legacy gateway URL", re.compile(r"ai-gateway\.vercel\.sh")),
        ("legacy gateway name", re.compile(r"Vercel AI Gateway", re.IGNORECASE)),
        ("legacy gateway shorthand", re.compile(r"vercel[-\s]+ai[-\s]+gateway", re.IGNORECASE)),
        (
            "legacy pipeline workspace",
            re.compile(
                r"(?<![a-z_/-])pipeline/(?:package\.json|node_modules|src/[^\s`]*\.[cm]?[jt]sx?)"
            ),
        ),
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
        # No file is exempt. `TODO.md` used to be, because it carried the note;
        # the note is gone, so the carve-out went with it.
        if account_funding.search(source):
            failures.append(f"{relative}: account-specific funding note")

    imitation_patterns = (
        re.compile(r"\bin the style of\b", re.IGNORECASE),
        re.compile(r"\bstyle of\b", re.IGNORECASE),
        re.compile(r"\binspired by\b", re.IGNORECASE),
        re.compile(r"""\blike\s+["'A-Z]"""),
        re.compile(r"""\bmeets\s+["'A-Z]"""),
    )
    for policy_file in prompt_fixtures:
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
                f"{PROMPT_FIXTURES[0]}: every preset must explicitly request an original result"
            )
        if fixture.name == "styles.txt" and any(
            re.search(r"""["'()]|\b(?:game|film|studio|artist)\b""", line, re.IGNORECASE)
            for line in lines
        ):
            failures.append(
                f"{PROMPT_FIXTURES[1]}: style hints must remain neutral property descriptions"
            )

    readme = (repo / "README.md").read_text(encoding="utf-8")
    # The viewer is gnode's dashboard: the sentence that names it names its command.
    viewer_sentences = [
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+", " ".join(readme.split()))
        if re.search(r"\bviewer\b", sentence, re.IGNORECASE)
    ]
    if re.search(r"\bgeneral\b", readme, re.IGNORECASE) is None or not any(
        "gnode view" in sentence for sentence in viewer_sentences
    ):
        failures.append(
            "README.md: missing general-core / viewer framing (a sentence naming the "
            "viewer and `gnode view`)"
        )
    failures.extend(check_retired_terms(repo))

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
            "godot/games/_shared/docs/game-package.md",
            re.compile(r"directory or ZIP whose root contains `game\.toml`", re.IGNORECASE),
            "prepared-package CLI input",
        ),
        (
            "godot/games/_shared/docs/game-package.md",
            re.compile(
                r"--dry-run.{0,200}deterministic fake operations",
                re.IGNORECASE | re.DOTALL,
            ),
            "provider-free execution dry run",
        ),
        (
            "godot/games/_shared/docs/game-package.md",
            re.compile(r"There is no bare-prompt fallback", re.IGNORECASE),
            "removed prompt fallback",
        ),
        (
            "godot/games/_shared/docs/game-package.md",
            re.compile(
                r"without `--dry-run`.{0,160}fails before provider",
                re.IGNORECASE | re.DOTALL,
            ),
            "fail-closed live package boundary",
        ),
        (
            "docs/spec/agent-prompts.md",
            re.compile(
                r"`native` is the default.{0,240}transparent background",
                re.IGNORECASE | re.DOTALL,
            ),
            "native-alpha prompt",
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
            "docs/viewer.md",
            re.compile(
                r"(?:web/` (?:starts|launches|plays) no run|does not (?:start|launch|generate)"
                r"|never (?:starts|launches|generates))",
                re.IGNORECASE,
            ),
            "web is not a generation authority",
        ),
        (
            "docs/viewer.md",
            re.compile(r"no gameplay", re.IGNORECASE),
            "web holds no game logic",
        ),
    )
    # The viewer consumes published contracts; it must not be able to start a run. A shell
    # that can spawn a process is one refactor away from being a second generator, so the
    # absence of the capability is checked rather than described. A scan that matched no
    # file proves nothing, so an empty one fails too.
    web_shell = sorted((repo / "web/viewer/lib/shell").glob("*.ts"))
    if not web_shell:
        failures.append("web/viewer/lib/shell: the no-spawn rule matched no file")
    for source_path in web_shell:
        source = source_path.read_text(encoding="utf-8")
        if "node:child_process" in source or "Bun.spawn" in source:
            relative = source_path.relative_to(repo).as_posix()
            failures.append(f"{relative}: web shell must not spawn a generation process")
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
