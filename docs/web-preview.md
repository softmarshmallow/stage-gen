# Prepared-game web preview

`web/` is an optional consumer of the exact-current prepared runtime manifest. It does not plan,
generate, review, or publish game media and never receives provider credentials.

## Runtime input

The preview route is `/preview/<run-tag>`. The run directory is `out/<run-tag>/` and must contain
`manifest.json` with this identity:

```json
{
  "schema_version": 10,
  "kind": "prepared-game-runtime-v10"
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
map, player, mob, NPC, prop, item, projectile, UI, and soundtrack groups. It does not use
directory scans, filename conventions, `run.json`, `WorldSpec`, retry controls, or pipeline
events. Images open in an alpha-aware lightbox and soundtrack artifacts use native audio
controls. The home page also discovers prepared packages from this manifest, without requiring a
legacy prompt-run summary.

The page accounts for the whole closure, each artifact under the
[role](spec/game/generation-pipeline.md#runtime-closure-roles) the producer published it as.
Artifacts published as `provenance` are listed as records rather than presented as content, and a
record with nothing to render is shown as a file instead of a broken image. An `asset` no group
claims is listed as ungrouped and counted in the header: a package that grew a family this view
has not learned yet is this view falling behind, and the page says so rather than refusing to
render the rest of the run. Completeness of the classification is the producer's invariant,
enforced when the manifest is assembled; the page never has to infer a role from a path or a
media type.

This explorer is intentionally runtime-closure-only. Producer review evidence, contact sheets,
map composites, authored references, and reports outside the published closure remain in their
checkpoint artifact roots; they must not be copied into the gameplay closure merely to populate
this page. A future review explorer needs its own explicit review-manifest boundary.

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

The console below the canvas switches the developer kit, and K cycles the same choice from the
keyboard. This exists because a weapon class and the character's drawn equipment are one authored
decision, so trying the other arm by editing TOML means re-rendering the whole player domain -
sixteen provider operations - while the question a developer is usually asking is just "how does
the other arm play on this map".

The controls are buttons acting on the running scene, not links, and the page does not navigate or
reload. That is the point: a kit comparison is a question about the map already on screen, and
answering it by reloading would throw away the map, the level, and the position that made the
question worth asking. Selecting the kit marked `·authored` clears the override rather than setting
another one, so returning to what shipped is the same control.

It is an override and never an authored fact. The parsed gameplay contract is untouched; only the
scene's own decision about which class it is holding changes, so nothing published moves. What is
offered comes from what the run reports it can play, so a run that drew no projectile has exactly
one kit and shows no console at all - as every run generated before the projectile catalog existed
does. The override is refused under fixed-frame automation, in both the scene and the boot call, so
a capture is always a recording of the run as published.

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

`[combat] weapon_class` names how the character fights. `melee_dps_v1` swings the `basic_action`
strip over a band a little under a tile and a half wide; `ranged_dps_v1` throws on the
`secondary_action` strip. Both deal the same damage — distance is what the throwing class buys, and
a character that kills from five tiles never walks into contact and never pays the contact-damage
tax. Neither costs an extra generated image: both attack poses are already drawn for every
combat-enabled package. A package that names no class swings, which is what every run published
before the field did.

The class is not free to pick, though, because the character has to be drawn able to use it. The
player catalog declares `equipment` — `hand_weapon_v1`, `unarmed_v1`, `thrown_kit_v1`, or
`focus_implement_v1` — and package resolution refuses a combination the two closed vocabularies do
not admit, so a figure carrying a sword cannot be given a throwing class. Bellweather is the
`hand_weapon_v1` case and therefore swings: the wayfarer is drawn with a wooden training sword, on
a cover that the whole player domain is generated from. The equipment does not reach the runtime
manifest at all — it decides what gets drawn, and the runtime learns how the character fights from
`weapon_class` alone.

What flies is a **projectile**, authored in `content/projectiles.toml` and drawn as its own
generated sprite. Each entry names three facets the director varies independently. `silhouette`
says what is drawn and along which axis — `radial_v1` has no leading end and is spun in flight,
`axial_v1` is drawn pointing right and is mirrored and aimed along its arc, `irregular_v1` tumbles.
`flight` says how it moves — `flat_bolt_v1` crosses six tiles level and fast, `lobbed_arc_v1` falls
so it can clear a lip, `drifting_orb_v1` is slow enough to walk around. `impact` says what arrival
resolves against — `single_target_v1`, `burst_v1` for everything the box touches on the frame it
lands, or `piercing_v1`, which keeps flying. Only the silhouette reaches the image model; changing
how an object moves or lands regenerates nothing.

The two weapon classes disagree about height, and deliberately. A swing compares feet and reaches
one terrain level either way. A thrown object is simply where it is, so it connects with whatever
body its flight path crosses — roughly one deck up and one deck down for a common creature, and
further below for a tall one. A shot expires at its range, at the edge of the map, or against a
rising hillside, using the same terrain query a dropped item settles on.

The preview plays itself. Auto-play is on by default and hands the controls back the moment a key
is touched, holding them for the human for a second and a half after the last input, so inspecting
the run by hand needs no mode change; P switches the bot off entirely and says so in the stat log.
A fixed-frame automation run gets no bot at all, because that capture records scripted input and a
second actor inside it would be recording the bot instead. The bot fights at whatever distance the
weapon class wants: a swinging class walks all the way into contact, and a throwing class holds
station between two and a half and five and a half tiles — outside the reach of every aggression
archetype in the roster — stepping back if a creature closes inside that floor, and keeping the
target in front of it while it does. A throwing class also checks the ground: a creature standing
behind a rise is declined rather than fired at, because the shot would die in the rise and the
attack behaviour outranks the one that would have walked somewhere better.

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

## Presentation

The shell is styled with [Tailwind CSS](https://tailwindcss.com) v4 and carries no hand-written
stylesheet. [`app/globals.css`](../web/app/globals.css) is the Tailwind configuration, not a
theme: it imports Tailwind, names the source globs, declares the design tokens
(`--color-bg`, `--color-fg`, `--color-dim`, `--color-accent`, `--color-error`, `--color-border`,
plus the `vn-` palette of the demo-only visual-novel route), and defines the three patterns no
utility class can spell — the alpha checkerboard and that route's sky and star field. Everything
else is written on the element that wears it, so a rule cannot outlive its markup.

[`app/ui.ts`](../web/app/ui.ts) holds the class strings shared by more than one file: the page
frame, the bracket-button, the Play CTA, the asset slot and its states. They are values, not a
cascade — nothing there overrides anything else, and an unused one is a dead export.

Tailwind emits its utilities inside `@layer utilities`, so unlayered third-party CSS outranks them
whatever the specificity. `ol.css` is the only such import; the atlas viewport marks its OpenLayers
control overrides `!` for that reason and says so in place.

## Legacy boundary

The former prompt-launching live Generate view, scrolling manifest V7 parser, `WorldSpec`,
`VillageSpec`, map-book adapter, and slot-derived filename scene are not authorities for prepared
package runs. They remain repository code only for historical prompt runs while their independent
tests and evidence are retired safely. Prepared `/generate/<run-tag>` routes use the manifest
asset explorer, and `/preview/<run-tag>` boots `PreparedStageScene` exclusively.

No backward-compatible prepared-input translation exists. A directory or ZIP with root
`game.toml` is the package root, and `prepared-game-runtime-v10` is the only manifest
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
