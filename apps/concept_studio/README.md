# Concept Studio

An optional application that uses Stage Gen image services to explore a game
concept and select cover art. It has its own Python distribution and CLI; the core
asset SDK does not depend on it.

```sh
uv sync --group apps
uv run --group apps stage-gen-concept --help
uv run --group apps stage-gen-concept --root /tmp/my-concepts init --help
```

`--root` selects a caller-owned workspace root outside this checkout. When omitted,
the app uses the checkout when available and otherwise the current directory.
Drafts remain separate from accepted pipeline inputs. Live image work requires
explicit authorization; selecting a cover is not publication approval.

The existing [concept workspace](../../concept-studio/README.md) documents the
concept artifact format and curated gallery. Run the app gate with
`uv run --group apps python scripts/check.py --scope apps`.
