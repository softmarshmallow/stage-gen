# Game Concept Studio

Game Concept Studio is the inexpensive pre-production side of Stage Gen. Start here with a short
game idea, talk it through with an agent, and leave with a readable concept plus cover art before
deciding whether to run the full generation pipeline.

It is deliberately not a recipe authoring surface. A concept workspace never contains
`game.toml`, maps, manifests, runtime assets, or implementation code.

## Start an agent here

```sh
cd concept-studio
```

The canonical `game-concept-studio` skill lives at the repository root under
`../.agents/skills/`. The repository's `../.claude/skills/` entry and the entries under this
project's `.agents/skills/` and `.claude/skills/` are discovery symlinks to that one root-owned
skill. Ask for the skill explicitly or give the agent a short game description, for example:

```text
Use game-concept-studio to imagine a 2D adventure about a rooftop courier in a flooded city.
```

The agent creates ignored work under `workspaces/`. The stable human-facing handoff is:

```text
workspaces/<concept_id>/concept.md
workspaces/<concept_id>/images/cover.png
```

From the repository root, the deterministic workspace and image commands are:

```sh
uv run stage-gen-concept init --slug <concept_id> --title "<title>" "<short brief>"
uv run stage-gen-concept image --workspace <concept_id> --name candidate-01 \
  --model x-ai/grok-imagine-image-2.0 --quality low --resolution 1K \
  --aspect-ratio 16:9 --prompt-file <prompt.txt>
uv run stage-gen-concept select --workspace <concept_id> --candidate candidate-01
uv run stage-gen-concept check --workspace <concept_id>
```

The CLI reads only allowlisted provider credentials from the repository-root `.env`; it never
copies credentials into this project. Live image calls are billable and require explicit intent.

## Gallery

`gallery/` contains only explicitly promoted, independently reviewed, provenance-complete concept
packages. A successful local image is not automatically gallery-ready.
