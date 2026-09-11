# The games tier

Branded games built on the packages. Each is its own Godot project with its own
`project.godot`, shell, Lab, tests and tools, and each links the presentation
package at `addons/game_presentation`. They are the examples of the line: a
contract's dependence on its assets is visible here and nowhere else, which is
why they exist in the tree at all.

| Game | What it is | Run |
| --- | --- | --- |
| [`afterlight/`](afterlight/README.md) | Bishōjo: Afterlight, *The Address Beyond*: a 57-beat ensemble adventure | `Godot --path godot/games/afterlight -- --language ko` |
| [`command_link/`](command_link/README.md) | Command Link: a tactical, commander-led story with a video opening | `Godot --path godot/games/command_link` |

This document is the anchor for how a game's files are kept. It describes the
present arrangement, states what a fresh clone can and cannot do, and records
the deferred decision about committing media, so nobody has to rediscover any
of it.

## What Git holds, and what stays on the machine

Git holds everything authored and everything that describes the media. It holds
no media bytes.

| In Git | Local only, ignored |
| --- | --- |
| scripts, scenes, shaders, UID sidecars | `assets/**` image, audio and video bytes and their `.import` sidecars |
| catalogs and manifests: `assets/**/*.json`, `voice/*.json`, `text/*.json` | `art/`: generation rounds, prompts, raw returns, previews, recordings |
| the digest of every bound file, inside those catalogs and manifests | `captures/`: evidence frames from native checks |
| reviews and records that already sit outside `art/` | `tests/**` outputs other than suites and review notes |
| suites (`tests/*.gd`), review notes (`tests/**/*.md`), Python tests | `.godot/` import caches |

Afterlight's bound set is 13 active images, placeholders, the Manpu marks and 80
recordings, about 110 MB. Command Link's is 20 images plus two opening videos,
about 119 MB, of which the videos are 98 MB. Generation rounds and evidence add
roughly 740 MB more that will never be candidates for Git.

Two gaps in this arrangement are known and accepted for now:

- The review notes and active-selection records under each game's `art/` are
  ignored with the bytes around them, so the approval basis of the active images
  is not in Git. They belong there; moving them is part of the adoption below.
- `.import` sidecars are ignored, so a machine that receives the bytes re-imports
  them with default settings. Exact source-pixel parity is available through the
  external content root, which decodes raw files.

## What a fresh clone can do

Open either project, read every contract, run every suite that needs no media,
and see the game refuse cleanly. Without its media a game does not show an empty
stage: Afterlight lists every missing binding in its dialogue line and Command
Link disables its stage and prints the bindings in its hint bar. Both come from
the content adapter validating each bound path before the scene is staged.

Playing needs the media on the machine. There are two ways to get it, both from
a machine that has it:

1. Copy `godot/games/<game>/assets` and `godot/games/<game>/art` into the same
   places. The bindings are relative to the project, so nothing else changes.
2. Prepare an external content root and point the game at it. Afterlight's tool
   copies the bound files with a hash inventory and no scripts, and the game
   reads that directory instead of `res://`:

```sh
python3 godot/games/afterlight/tools/prepare_example_content.py --output /private/tmp/afterlight-content
Godot --path godot/games/afterlight -- --language ko --content-root /private/tmp/afterlight-content
```

The content root mirrors the project layout: `assets/`, `text/`, `voice/` and
`art/voiceovers-p95/clips/`. It is a host convention, not a package schema. The
files backend never falls back to the project's own media, so a wrong root is a
refusal, not a silent mix.

Media is never generated during play, status or replay. New images, recordings
and videos come from explicit tool runs, are reviewed by the user against
rendered previews, and are adopted by replacing the bound file and updating the
catalog digest. Provenance for every adopted file lives in its round record
under `art/`.

## The deferred decision: media in Git

The user's direction is that the bound media should eventually live in Git so
that a clone plays and a contract's asset dependence is visible in the tree.
The concern is history bloat, because game media is replaced often. Committing
is deferred until the game has landed; nothing is adopted now.

When it happens, this is the discipline, in the order it applies:

1. **Only bound bytes.** A binary is tracked only when a tracked catalog,
   manifest or scene references it. A closure test enforces both directions:
   every referenced file exists, every tracked binary is referenced. Rounds,
   candidates, previews, captures and raw returns stay under `art/` and ignored.
2. **Replacement, never accumulation.** A revised file lands at the same path,
   one commit per review round, after candidates were compared outside the tree.
3. **Written budgets.** 8 MiB per file, 150 MiB per game's bound set, enforced by
   a gate and changed only by a commit that says why.
4. **The opening video stays external.** The selected variant alone is 51 MB and
   Command Link already falls back to a title without it.
5. **Lossless, optimized once at adoption.** PNG through an optimizer or lossless
   WebP; recordings as delivered; `.import` sidecars tracked with the bytes.
6. **Rights ride with the bytes.** The game's `assets/` becomes a declared
   publication root; a sidecar is generated from the round record and the review
   verdict; the redistribution decision is attested by the user, once per round.
   ElevenLabs redistribution terms are confirmed before recordings go public.
7. **LFS is decided once, before the first public push.** Plain Git keeps clones
   dependency-free, which [the storage policy](../../docs/repository-storage.md)
   chose on purpose. Migrating a media family to LFS rewrites history, cheap
   before publication and painful after, so the media share of history is
   measured then and the question closed.

Until then, the storage policy's rules apply unchanged: no media bytes in Git,
every committed binary needs a reason, provenance and rights status, and the
publication gate governs any generated file that does enter a declared root.
