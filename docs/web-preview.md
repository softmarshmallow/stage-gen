# Prepared-game web preview

`web/` is an optional consumer of the exact-current prepared runtime manifest. It does not plan,
generate, review, or publish game media and never receives provider credentials.

## Runtime input

The preview route is `/preview/<run-tag>`. The run directory is `out/<run-tag>/` and must contain
`manifest.json` with this identity:

```json
{
  "schema_version": 1,
  "kind": "prepared-game-runtime-v1"
}
```

[`prepared-manifest.ts`](../web/lib/runtime/prepared-manifest.ts) is the browser boundary parser.
It rejects unresolved entry maps, unsafe artifact paths, invalid digests, malformed stable IDs,
non-4-by-1 motion strips, and contradictory source-facing/mirroring policy. Artifact paths are
portable paths below the selected run. The asset route permits nested paths only after run-tag,
path-segment, containment, regular-file, and realpath checks.

The Python producer is
[`prepared_manifest.py`](../src/stage_gen/recipes/scrolling_preview/prepared_manifest.py). It
searches accepted artifact roots in caller priority order, validates the complete package-derived
media closure before writing, assembles in a temporary sibling directory, and atomically renames
the complete run into place. Integration is provider-free:

```sh
stage-gen generate \
  --input library/games/bellweather \
  --checkpoint integration \
  --artifact-root /path/to/corrective-actor-run \
  --artifact-root /path/to/complete-content-run \
  --artifact-root /path/to/complete-world-run \
  --output out/bellweather-prepared-v1
```

The first root containing an expected relative artifact wins. This is how a narrowly regenerated
motion run can replace stale motion without copying unrelated older content into it or rerunning
providers. Every selected byte is recorded once in `closure.artifacts` with path, SHA-256, byte
count, media type, and image dimensions. The closure list has its own canonical digest.

## Consumer ownership

[`prepared-scene.ts`](../web/lib/runtime/prepared-scene.ts) owns preview-specific implementation:

- 1280-by-720 viewport and horizontal follow camera;
- a 12,800-pixel consumer world for each authored map;
- map-local parallax layer stacks and ground-material projection;
- 4-by-1 player, mob, and NPC motion strips with runtime mirroring;
- stable-ID prop, item, soundtrack, spawn, placement, loot, transition, interaction, sequence,
  expression, and effect bindings;
- keyboard movement, jumping, attacks, contact damage, drops, pickup, inventory, portals, and
  proximity dialogue.

Those are browser-demo choices. They must not leak into authored TOML, provider-neutral
components, image prompts, or the generic dependency executor. Conversely, the scene may not
invent entity relationships or infer artifacts from positional filenames. Array positions are
local iteration order only; authored relationships resolve through IDs in the manifest.

The current controls are Left/Right or A/D to move, Shift to run, Space to jump, J/X/Z to attack,
E or Enter to interact/advance dialogue, and Up or W to travel at a map boundary. Generated audio
starts only after a keyboard gesture because browsers block autoplay.

## Legacy boundary

The former prompt-launching Generate view, scrolling manifest V7 parser, `WorldSpec`,
`VillageSpec`, map-book adapter, and slot-derived filename scene are not authorities for prepared
package runs. They remain repository code only while their independent historical tests and
evidence are retired safely; `/preview/<run-tag>` boots `PreparedStageScene` exclusively.

No backward-compatible prepared-input translation exists. A directory or ZIP with root
`game.toml` is the only game-generation input, and `prepared-game-runtime-v1` is the only manifest
accepted by the active preview.

## Verification

Credential-free gates for this boundary are:

```sh
cd web
bun run check
bun test
bun run build
```

Python manifest tests prove closure priority, stable-ID topology, portable output, and rollback of
incomplete assembly. HTTP evidence may prove that the preview page, manifest, and nested assets
are served. It does not prove visual or gameplay quality; browser interaction evidence remains a
separate review gate.
