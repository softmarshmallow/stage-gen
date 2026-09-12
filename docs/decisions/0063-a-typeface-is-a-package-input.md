# 0063 — A typeface is a package input, and a typeface is media

*Ruled 2026-09-07, while the game shell was being contracted.*

## Fact

This repository already treats a typeface as a design constraint rather than a
setting. [0017](0017-the-numeral-face-is-a-typeface-constraint.md) moved the
arcade numerals to Luckiest Guy because a stroke eats a glyph's counters from
both sides and Fredoka's close before the edge reads, and it committed the face
to do it. Two faces sit under `web/public/fonts/` today, each with its licence
text and a README recording family, copyright, licence, upstream source,
retrieval date and SHA-256.

Two things have changed underneath that.

The first is where the games run.
[0061](0061-every-genre-runs-on-godot-and-web-is-the-viewer.md) makes every
genre's host a Godot host, and `web/` the viewer that keeps no gameplay. The two
committed faces serve a runtime that is being deleted one genre at a time. On the
side that replaces it there is no face at all:
`godot/hosts/oblique_survival/hud/ui_kit.gd:163` builds a `SystemFont` from
`["ui-monospace", "SF Mono", "SFMono-Regular", "Menlo", …]`. Every string the
survival host draws is set in whichever of those the machine happens to have.
That is precisely the bug 0017 found by accident — "the committed font had no
caller and there was no font face declared in the app's CSS, so every damage
number ever drawn was set in the first fallback the machine had" — except that
here it is not an oversight. It is the designed state of every Godot host.

The second is that a face is about to carry a game's name. The shell contract
composites the title wordmark rather than drawing it, because every UI role in
this repository declares `text_free` and every package's `[style].avoid` forbids
"text pseudo-text logos signatures or watermarks". A wordmark set in the host
machine's monospace fallback is not a title screen.

There is also a quieter fact. `.ttf` and `.otf` appear in neither `MEDIA_SUFFIXES`
nor `_media_family` (`tests/contract/test_packaged_resources.py:57`, `:587`), and
`docs/repository-storage.md` names one location for package binaries —
`godot/games/<game>/inputs/references/` — with no arm for a face. The two committed
faces are 232,504 bytes that the aggregate media ceiling does not count and the
location assertions never see. Nothing is wrong with those two files; the gate
simply has a hole where fonts are, and a policy that counts every PNG while a
159 KB binary walks past it is not being enforced, it is being performed.

## Challenge

The cheap and genuinely attractive move is to ship one face inside the Godot
template. One file, no contract, no per-package duplication, no gate change, and
the template is code the host contract already lets a template carry.

It is wrong on the seam. A template-owned face makes every game this repository
generates speak in one voice, which is the opposite of what a per-game art
direction is for — and it puts a look decision on the consumer side of a boundary
that 0057 and 0061 spent two records keeping reversible. The host contract is
explicit that a template "contains no run and no media"; a face is media, and one
that determines how a game's own name is set is not host furniture. The
duplication the alternative avoids is not a cost worth the trade: OFL and Apache
both permit redistributing the font file, a package is already a capture root
whose references are package-relative, and `references/cover.png` is duplicated
across packages today for exactly the same reason.

## Ruling

**A typeface is an authored package input, bound by digest like every other
reference, and republished into the run as an artifact the host resolves below
the run root.**

1. **Location.** A face lives at `godot/games/<game>/inputs/fonts/<face>.ttf` or
   `.otf`, with its licence file beside it. The storage policy's package-binary
   rule gains that arm; it is the second place a package may hold a binary, and
   like the first it is named rather than inferred.
2. **Rights.** The face's licence must permit redistributing the font file
   itself, because publishing a run copies it. The authored contract records
   family, copyright, licence, licence file, upstream source, retrieval date and
   SHA-256 — the block the two existing READMEs already use, promoted from a
   README convention into a contract table so a resolver can refuse an incomplete
   one offline.
3. **A typeface is media.** `.ttf` and `.otf` join `MEDIA_SUFFIXES` under a
   `font` family with its own per-file ceiling, so a face counts against the
   aggregate limit and obeys a location rule like every other tracked binary.
   The two faces under `web/public/fonts/` become counted rather than invisible;
   they need no other change, because `web/public` is already an allowed root.
4. **Not the publication gate.** A font is a third-party input with a rights
   basis, not provider output published as art. It gets no
   `generated-media-inventory.json` entry and no `.meta.json` sidecar, exactly as
   `references/` art does not.

What this does not rule: which face any game uses, whether a host may fall back
to a system font when a package declares none (it may, and it says so — a missing
role draws the plain fallback *and* reports what was missing), or anything about
subsetting. The complete upstream file is retained, as both existing READMEs
already state.

## Evidence

- The fallback measured: `ui_kit.gd:163` is a `SystemFont` over a five-name
  monospace stack; no `FontFile` is loaded anywhere under `godot/`.
- The gate hole measured: `.ttf` is absent from `MEDIA_SUFFIXES`
  (`test_packaged_resources.py:57`) and `_media_family` returns `"image"` for any
  unrecognised suffix (`:587`), so `fredoka-variable.ttf` (159,184 bytes) and
  `LuckiestGuy-Regular.ttf` (73,320 bytes) are outside both the 100 MiB aggregate
  and the per-root location assertions. After this change they are inside both,
  at 232,504 bytes against 100 MiB.
- The precedent this extends rather than invents: `web/public/fonts/*/README.md`
  already records family, copyright, licence, source, retrieval date and SHA-256
  per face, and 0017 already ruled the face itself a constraint.
- Cost: zero provider operations, and no contract identity moves in this record.
  The authored binding arrives with `game-shell-v1`; this record is the policy it
  will stand on, landed first because its evidence is already in hand.

## Falsifier

A licence a package wants whose terms forbid the redistribution that publishing a
run performs. That does not overturn the rule — the resolver refuses the face
offline and the rule is what did the refusing — so the real falsifier is the
opposite shape: **if every generated game converges on the same face, the
per-package input is ceremony and the face belongs in the template after all.**
The observation that would show it is three or more packages declaring one
identical `source_sha256`, with no package having ever declared a different one.
