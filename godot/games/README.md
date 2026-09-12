# Example games

Every named game is a maintained consumer of the asset product. A game owns its
Godot project, content, gameplay, preparation and tests. It may use an independent
package or private support shared with the other games. It does not need to adopt
another game's input format or project organization.

The [Godot project charter](../CHARTER.md) defines the example project's purpose
and governs future changes to shared support, packages and game frameworks.

| Game | What it demonstrates | Inputs and preparation |
| --- | --- | --- |
| [Afterlight](afterlight/README.md) | Authored ensemble adventure and presentation Lab | Game-owned catalogs, story, bindings and tools |
| [Command Link](command_link/README.md) | Tactical story, video opening and presentation Lab | Game-owned catalogs, story, bindings and tools |
| [Bellweather](bellweather/README.md) | Side-view platformer | `inputs/default/`, `inputs/waves/`; `pipeline/prepare.py` |
| [Iron Petal Unit](iron_petal_unit/README.md) | Side-view runner | `inputs/`; `pipeline/prepare.py` |
| [Ember Hollow](ember_hollow/README.md) | Ground-plane survival | `inputs/`; `pipeline/prepare.py` |
| [The Grain](the_grain/README.md) | Investigation combining rooms and dialogue | `inputs/`; `pipeline/prepare.py` |

[Launch commands](../README.md#play-a-game) live in the Godot workspace guide.
Existing generated runs remain outside these project roots and are selected with
`--run`. Each preparation script defaults to offline planning or validation;
starting Godot never invokes generation.

`_shared/` holds private code with several game consumers. The public asset product
never imports game packages. Shared runtime and Python code never import a named
game; collection dispatch belongs to `godot/tools/`.

## Inputs and formats

The complete authored TOML and reference closure lives under its game's `inputs/`.
Bellweather keeps its two variants as intact closures. Persisted IDs and member
paths remain unchanged. A game's future changes may replace configuration with
GDScript or resources without introducing a repository-wide game contract.

Tracked, digest-bound input references and fonts retain their existing storage
and rights rules. Generated runs, caches and unreviewed media remain ignored.
The following media inventory and deferred storage decision concern Afterlight
and Command Link specifically; they are not a prohibition on the other games'
authored input references.

## What Git holds, and what stays on the machine

For Afterlight and Command Link, Git holds authored code and the catalogs that
describe their playable media. Their bound image, audio and video bytes remain local.

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

Open Afterlight or Command Link, read every contract, run every suite that needs no media,
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

The recorded proposal for those two games is to hold bound media as plain Git objects,
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
