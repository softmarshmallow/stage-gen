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

Afterlight's bound set is 13 active images, the Manpu marks and 80 recordings
under `voice/clips/`, about 90 MB. Command Link's is 20 images plus two opening videos,
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

The content root mirrors the project layout: `assets/`, `text/` and `voice/`
with `voice/clips/`. It is a host convention, not a package schema. The
files backend never falls back to the project's own media, so a wrong root is a
refusal, not a silent mix.

Media is never generated during play, status or replay. New images, recordings
and videos come from explicit tool runs, are reviewed by the user against
rendered previews, and are adopted by replacing the bound file and updating the
catalog digest. Provenance for every adopted file lives in its round record
under `art/`.

## The decision, and what is deferred

The bound media will live in Git as plain objects, like any Godot project's,
with no LFS, no `.meta.json` sidecars, no inventory entries and no rights
records: whatever a game ships is its own asset. Git LFS was tried and
rejected, because GitHub meters LFS downloads to the repository owner with no
exemption for public repositories, while plain Git clones are free.

What is deferred is where that Git history lives. About 160 MB of media per
art round does not belong in the generator's history, so the Godot line, the
presentation SDK with its template and games, is proposed to move to its own
repository; the topology and the steps are in
[issue #14](https://github.com/softmarshmallow/stage-gen/issues/14). Until
that is settled, the media stays on the authoring machine and this repository
tracks only code, catalogs and digests, with the storage policy unchanged.
Only what a game reaches is tracked: `python3 godot/tools/unused_assets.py
godot/games/*` lists any tracked asset or catalog no scene, script or catalog
names, and a contract test fails when it lists anything.
