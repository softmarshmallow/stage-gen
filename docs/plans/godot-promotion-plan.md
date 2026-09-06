# The Godot promotion: the path

Status: in flight. Steps 0 to 3 and the kernel have landed; the table marks them. Companion to [the host contract](../spec/game/host-contract.md)
(the end state) and
[decision 0061](../decisions/0061-every-genre-runs-on-godot-and-web-is-the-viewer.md)
(the ruling). This document is the path, and it dies when the path is walked.

Four browser games become four Godot hosts; `web/` keeps the run list, the run
view, the inspector and the gallery, and plays nothing. Hosting — an upload, a
channel, a catalogue, a URL — is out of scope and stays in
[issue 8](https://github.com/softmarshmallow/stage-gen/issues/8).

## The rules that hold across every step

- **Zero provider operations.** Every input is a run already under `out/` or a
  fixture serialised from a browser test. No art is regenerated, no manifest
  kind moves, no published run is dropped by a consumer change.
- **The incumbent is the reference until it is gone.** Before a genre is
  ported, the browser side commits its own per-step state for a scripted seed
  as `<script>.web.jsonl`, plus design-space stills. The host replays the same
  script and the diff must be empty. The browser game is deleted in the change
  that lands its host, so no genre is ever played twice.
- **A retirement is a numbered record**, carrying the parity line count, the
  picture sheet, the smoke, and the check count against the tests it replaces.
- **The gate is green at every boundary.** A commit that leaves `bun run check`
  or `uv run python scripts/check.py` red is not a boundary.
- **A record is written in the commit that holds its evidence**, never earlier.

## The steps

| # | Commit | What lands | The gate |
| --- | --- | --- | --- |
| 0 ✔ | A | The rulings that have their evidence today (0061, 0062), the host contract, the doc moves, the history exemption in the docs gate | `check_docs.py`, the docs contract tests |
| 1 ✔ | B | The viewer is decoupled: the home index stops importing genre readers, `/packages` goes, `/runs/<tag>/artifacts` arrives, dead platformer modules go, every run with a plan gets an execution view | `bun run check`, `bun test`, `check.py` |
| 2 ✔ | C | Survival's instruments pinned on the unmoved tree: three parity scripts as goldens, one capture sheet | the goldens reproduce twice, byte for byte |
| 3 ✔ | D | The mono-project: one `godot/project.godot`, the layers as directories, the survival host relocated by text edits, names prefixed, paths edited | goldens byte-identical, capture sheet mean 0.0 / p99 0.0 |
| 4 | E | The export factory proved on survival: the exporter, the release record, the run root rule, the bridge, the web shell | an export opens standalone and answers all six verbs; two exports agree on the closure digest |
| 5 ✔ | F | The kernel in GDScript, and survival sealed: declarations, a derived order equal to the pasted one, the event queue, refusals as values, the interface writing through the latch | the goldens unchanged line for line |
| 6 | G | The suite enters the locked gate: a supervisor per test file, fixtures with synthesised media, the CI job | `check.py` fails without the engine; an injected error and an injected hang both turn it red |
| 7 ◐ | H | The browser instruments: the platformer's slice list, every fixture and reference committed, stills taken | the references reproduce; the fixtures carry current identities |
| 8 | I | **The runner**, and the browser runner is deleted | parity N/N, sealed order equal to the documented one, stills, smoke, export |
| 9 | J | **The platformer**, and the browser platformer is deleted | the same, per map, plus the map-scope reset |
| 10 | K | **The room, the scene and the case**, and their browser surfaces are deleted together | the same, plus an episode played end to end with a save and a resume |
| 11 | L | The sweep: the last web references, the census rows, the identities regenerated | `check.py` green; no `phaser` anywhere under `web/` |

**Two reorderings, with their reasons.** Step 5 (the kernel) landed before step 4
(the export factory): the kernel was ready and the factory needed a 1.3 GB
toolchain download, and nothing in the ports depends on the factory. Step 6 (the
gate) is next rather than the factory, because the gate protects every port that
follows it while the factory protects nothing until there is something to export.

**What step 6 turns out to cost.** Nearly every one of the twenty-nine Godot test
files reads the real run — through `TestFixtures.world()` if not directly — so a
suite that runs in CI needs a media-free fixture document, a small world, and
synthesised media at the sizes that document declares, with the real-run count
pins moving to tier 2 behind `--run`. That is a restructuring of the suite rather
than a wrapper around it, and it is why the step is its own commit.

**Step 7 is half done.** The runner's and the platformer's references are
committed, and the platformer's exclusion list is settled and measured: 103 leaf
fields survive it, which is the floor its port must match. The room, the scene
and the case get theirs in the change before their port rather than all at once,
because an instrument taken early is an instrument that can drift, and the risk
it guards against — deleting a game before its reference exists — is covered as
long as each genre's capture precedes its own port. The stills are not taken
yet; they need the browser's WEBGL renderer rather than its capture mode, whose
canvas path draws no tint at all.

Steps 8 to 10 each carry their retirement record. The order is the two
kernel-sealed genres first, while the families port is fresh, then the three
turn-based surfaces, which carry no floating-point state and retire together
because the case cannot outlive the leaves it plays.

## What is deliberately not here

The upload, channel pointers, a catalogue, cache and CORS policy, rights
activation on published bytes, and any web route that serves an executable. A
block table for the room, the bundle and the survival manifest, and the survival
document's schema number, are each their own later record, provider-free, with
the cache-key golden as the proof that they cost nothing.
