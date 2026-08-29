# Prepared-game web preview

`web/` is an optional consumer of the exact-current prepared runtime manifest. It does not plan,
generate, review, or publish game media and never receives provider credentials.

## Runtime input

The preview route is `/preview/<run-tag>`. The run directory is `out/<run-tag>/` and must contain
`manifest.json` with this identity:

```json
{
  "schema_version": 8,
  "kind": "prepared-game-runtime-v9"
}
```

[`prepared-manifest.ts`](../web/lib/runtime/prepared-manifest.ts) is the browser boundary parser.
It rejects unresolved entry maps, unsafe artifact paths, invalid digests, malformed stable IDs,
non-4-by-1 motion strips, contradictory source-facing/mirroring policy, invalid binary occupancy,
and malformed map-local ladder or portal projection. Artifact paths are
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

Publishing a run tag is immutable by default. Republishing an identical closure over an existing
output directory is a no-op (`disposition: unchanged`); publishing different bytes under that tag
requires `--replace-output` and reports the `replaced_manifest_sha256` it destroyed.

The first root containing an expected relative artifact wins. This is how a narrowly regenerated
motion run can replace stale motion without copying unrelated older content into it or rerunning
providers. Every selected byte is recorded once in `closure.artifacts` with path, SHA-256, byte
count, media type, and image dimensions. The closure list has its own canonical digest.

## Prepared asset explorer

The details route is `/generate/<run-tag>`. For a prepared package it reads the same validated
`manifest.json` and projects every explicitly bound closure artifact exactly once into semantic
map, player, mob, NPC, prop, item, UI, and soundtrack groups. It does not use directory scans,
filename conventions, `run.json`, `WorldSpec`, retry controls, or pipeline events. Images open in
an alpha-aware lightbox and soundtrack artifacts use native audio controls. The home page also
discovers prepared packages from this manifest, without requiring a legacy prompt-run summary.

This explorer is intentionally runtime-closure-only. Producer review evidence, contact sheets,
map composites, authored references, and validation reports remain in their checkpoint artifact
roots; they must not be copied into the gameplay closure merely to populate this page. A future
review explorer needs its own explicit review-manifest boundary.

## Consumer ownership

[`prepared-scene.ts`](../web/lib/runtime/prepared-scene.ts) owns preview-specific implementation:

- 1280-by-720 viewport and a dead-zone follow camera whose permitted axes are read from the
  map's `[camera]` block rather than assumed; without a vertical axis the camera's world box
  is exactly one viewport tall, which is what holds it to the floor;
- map width derived from authored occupancy columns at the prepared adapter's tile scale;
- map-local parallax layer stacks and dynamic 47-mask terrain selection from authored occupancy;
- one-time, loop-safe layer depth treatment plus terrain-aware dynamic contact shadows;
- floating terrain runs and four-tile ladder traversal derived from the same occupancy matrix;
- map-owned portal presentation and endpoint placement resolved against gameplay-owned transitions;
- 4-by-1 player, mob, and NPC motion strips with runtime mirroring;
- stable-ID prop, item, soundtrack, spawn, placement, loot, transition, interaction, sequence,
  expression, and effect bindings;
- manifest-bound inventory-panel geometry and artwork, with a nonfatal magenta fallback;
- keyboard movement, jumping, attacks, contact damage, drops, pickup, inventory, portals, and
  proximity dialogue;
- healing consumables and a defeat screen whose way back is resolved from `item_kind` and the
  safe-hub map role;
- experience, levels, and critical hits, from the named curve and profile the contract publishes;
- an auto-play bot whose navigation graph is derived from the same authored occupancy the terrain is.

Those are browser-demo choices. They must not leak into authored TOML, provider-neutral
components, image prompts, or the generic dependency executor. Conversely, the scene may not
invent entity relationships or infer artifacts from positional filenames. Array positions are
local iteration order only; authored relationships resolve through IDs in the manifest.

The current controls are Left/Right or A/D to move, Shift to run, Down or S to crouch-walk, Space to
jump, J/X/Z to attack, Q to drink a healing consumable, I to toggle inventory, E or Enter to
interact/advance dialogue, P to toggle auto-play, and Up or W
to enter an active portal or climb from the lower end of a ladder. An airborne player overlapping
the ladder span may also press Up or W to grab it; jumping away and grabbing it again uses the same
rule rather than a separate combo. Down enters a ladder from its upper deck; Down+Space drops
through a one-way floating platform when no ladder entry takes priority. Generated audio starts
only after a keyboard gesture because browsers block autoplay. The diagnostic HP/inventory
overlay is hidden by default and toggles with Command+Backtick; it is not gameplay HUD.

Q spends the first healing consumable the player carries, in manifest order, and restores a share
of the authored pool. A drink at full health is refused rather than clamped, so the item is not
lost. Which items qualify comes from the catalog's `item_kind`; a package that ships none records a
diagnostic at load. Defeat is no longer terminal, and it is no longer silent either. After the authored death strip
finishes, a death screen names what happened and offers the way back — `Return to <map>`, because
where the run resumes is the fact worth reporting when home is derived rather than authored. The
button, or any of the keys that advance a conversation, sends the player to the game's own entry
spawn, or to the first map whose role is `safe_village_hub` when the game opens on a hostile route.
Nothing happens until it is answered: the press is recorded and drained on the next frame rather
than acted on inside the pointer callback, since a respawn tears down the objects that callback is
standing in. A run with the bot driving answers the prompt itself after a beat, because an
unattended run would otherwise stop forever at its first death. The world rebuilds and the player
returns at full health; what they were carrying survives, so defeat costs route progress rather
than the run.

`[progression] enabled` turns experience and levels on. A kill awards experience from the mob's
published rank; `experience_curve` names a pacing curve whose per-level cost is geometric, which
makes level logarithmic in total experience. A level widens the health pool by a fifth of the
authored one and fills it, and the wider pool survives map transitions and respawns. Levelling
lines appear in the transient stat log at the lower left — no panel, no background, fading on the
same simulation clock as floating combat text — and the diagnostic overlay gains an `LV`/`XP` line.
A package that leaves progression off shows neither.

`[combat] critical_profile` names how often a blow lands critical. It governs player and mob blows
alike, so a package cannot arm one side only, and the roll is a hash of the blow's ordinal and
position rather than `Math.random`, so a replayed run rolls the same criticals. A critical damage
number is drawn larger, hotter, with a heavier outline and a trailing `!`, and it punches and rises
further than an ordinary one. Reduced motion still flattens the movement for both.

The preview plays itself. Auto-play is on by default and hands the controls back the moment a key
is touched, holding them for the human for a second and a half after the last input, so inspecting
the run by hand needs no mode change; P switches the bot off entirely and says so in the stat log.
A fixed-frame automation run gets no bot at all, because that capture records scripted input and a
second actor inside it would be recording the bot instead.

What the bot presses is decided by [`bot-hunter.ts`](../web/lib/runtime/bot-hunter.ts) — stand down,
heal, engage, collect, pursue, patrol, arbitrated by priority once per frame — and where it can go
is decided by [`bot-navigation.ts`](../web/lib/runtime/bot-navigation.ts), which derives level
standing surfaces from the map's authored occupancy and joins them with the moves the character can
actually perform. A jump link exists only once the same fixed-step integration the controller runs
proves the arc, so the graph cannot promise a ledge the character falls short of, and a character
configured without a mid-air jump has no double-jump links rather than a repeated failure. Targets
are chosen by travel cost through that graph, so an unreachable mob is not pursued and the behaviour
declines instead. Nothing consults a clock it was not handed or a random number, so a replayed view
sequence produces the same intents.

## Legacy boundary

The former prompt-launching live Generate view, scrolling manifest V7 parser, `WorldSpec`,
`VillageSpec`, map-book adapter, and slot-derived filename scene are not authorities for prepared
package runs. They remain repository code only for historical prompt runs while their independent
tests and evidence are retired safely. Prepared `/generate/<run-tag>` routes use the manifest
asset explorer, and `/preview/<run-tag>` boots `PreparedStageScene` exclusively.

No backward-compatible prepared-input translation exists. A directory or ZIP with root
`game.toml` is the package root, and `prepared-game-runtime-v9` is the only manifest
accepted by the active preview.

The retired prompt-launching adapter is not an active generation authority. The legacy `{ prompt, transparency_mode }` HTTP start body is rejected instead of being translated into a prepared package.

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
