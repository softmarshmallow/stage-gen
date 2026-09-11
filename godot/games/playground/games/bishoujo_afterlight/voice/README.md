# Afterlight voice policy and recordings

This directory belongs to Afterlight. It resolves this game's actual speakers,
localized story lines and prepared recordings. The shared
[Text Reveal Audio presenter](../../../presentation/narrative/TEXT_REVEAL_AUDIO.md)
receives streams and owns playback only. There is no runtime TTS request,
automatic text/audio synchronization, or promoted voice module.

## Authored inputs

| Source | Ownership |
| --- | --- |
| `../story_beats.gd` and `../text/en.json`, `ko.json` | Stable story text IDs, beat structure and approved subtitles. |
| [voices.json](voices.json) | Speaker policy defaults, per-line speaker/policy overrides, and optional speech scripts keyed by language and stable text ID. |
| [cast.json](cast.json) | Selected existing provider voice and generation settings for each character/language. Descriptive casting notes do not change a recording's identity. |
| `manifest.json` | Prepared clip status, original path, source revision and artifact/provenance hashes. Missing manifest is a pending preparation state, not a request to generate. |
| [voice_policy.gd](voice_policy.gd) | Atomic source validation, actual-speaker resolution, freshness states and ready-stream lookup. No UI or network ownership. |

The current 57 beats contain 58 distinct story text IDs per language. Forty
character lines in each language use `voice_policy: "generated"`; eighteen
protagonist lines use explicit `voice_policy: "none"`. Both alternative replies
are included. The two choice-button labels in each language are excluded, as
are menus and technical demos. There are 80 recordings and 36 intentional
localized skips in this pass.

Speaker defaults cover Nami, Yuzu, Sena, Riko, Eira, the Keeper and the
protagonist. `line_overrides` can set `speaker`, `voice_policy`, and a descriptive
`reason` at a stable text ID. This handles the distinction between the visible
actor and the person speaking: `episode.a_hand_to_hold` is protagonist narration
over Nami's portrait, while `episode.nami_beyond_the_wall` is Nami speaking with
no actor present. The protagonist's policy cannot be changed to generated in
this host. An explicit `none` always takes precedence over a recording file.

`speech_scripts` contains fourteen sparse overrides across English and Korean.
When an override is absent, the approved display text is sent verbatim. The
current overrides add supported performance tags or a short pause while keeping
the spoken words aligned with the subtitles. Tags never enter displayed text.
Changes to displayed text do not silently edit an existing speech override;
the author reviews both before requesting a refresh.

## Current-source states

| State | Meaning and runtime behavior |
| --- | --- |
| `none` | Intentionally unvoiced. Skip generation and use the host's typewriter/fallback policy. Never report a missing recording. |
| `pending` | A voiced line has no prepared record, or is explicitly pending. Use fallback. |
| `stale` | Recorded source revision differs from current text, speech, speaker, language or selected provider profile. Use fallback; preserve the old file for review. |
| `missing` | A current ready record points to an absent or invalid local path. Use fallback. |
| `failed` | The record failed preparation, has invalid data, a hash mismatch, or an unsupported/undecodable recording. Use fallback. |
| `ready` | A current recorded source resolves to a usable stream. In `auto`, play it and show the complete subtitle. |

The source revision includes stable line ID, language, actual speaker, explicit
policy, display text, resolved speech text, and the selected generation profile:
provider, model, voice, language code, stability and output format. It excludes
file status, playback position and descriptive casting notes. Revisions detect
changes; they do not watch files or schedule provider work. The resolver reloads
when this host is configured, while the manual status command reads current
files afresh. An already-running game is not a live content editor.

Removing a story line leaves its well-formed speech script, policy override,
and recording inactive. The status report lists `unused_configuration` and
`unused_recordings` separately from active line counts. Those entries do not
block play, enter generation inventory, or bind a stream. Nothing is deleted
automatically; authors can review retained material during a later manual sync.

Inspect current authored status from the repository root:

```sh
/Users/universe/.local/bin/Godot --headless --path godot/games/playground --script res://games/bishoujo_afterlight/voice/export_inventory.gd -- --status
```

This reports counts and each stable line's status/reason without modifying
source, preparing recordings, or making a provider call. Optional `--output`
writes that report to a chosen local file. Without `--status`, the same script
exports the resolved generation inventory for a later authorized preparation
pass. The [manual preparation contract](../../../tools/AFTERLIGHT_VOICE_PREPARATION.md)
documents budget reservations, attempt accounting and verified output reuse.

## Host playback and continuity

The root binds `CONTENT.voiceovers` as language → stable text ID → ready stream.
The story resolves the selected alternate reply before looking up speech.
`CONTENT.text_audio` sets `auto`, `typing`, or `silent`, with an optional per-beat
`text_audio` override. These decisions are game-owned and do not alter the
shared presenter's contract.

In `auto`, a ready voice starts once and the full subtitle appears immediately.
There are no typing taps over that line, including after its audio completes.
Intentional `none` or unavailable recordings keep progressive text and the
configured typing fallback. A cinematic waits until its caption is visible
before starting speech; its first manual advance may still finish the motion.
The audio component never advances a beat, chooses an option, or confirms
fingertip contact. P97's optional [host autoplay](../AUTOPLAY.md) waits for
playback to finish, then starts its reading delay before continuing. With
autoplay off, completion alone leaves the current beat in place. Advancing
to another beat stops the preceding recording.

Menu pause stops playback time. A same-language checkpoint with the same source
revision resumes at its saved audio position; a completed clip stays completed.
Historical beat replay rebuilds visuals silently and begins only the current
cue. A language change preserves the story/effects and starts the replacement
language's current recording at the beginning. Lab detours retain the story
checkpoint and do not borrow its live streams. This is in-session continuity,
not a durable save format or word-level subtitle alignment.

Paused playback snapshots the real cursor before pausing the Godot player, so
a checkpoint taken from the pause menu retains its position. Returning from
the Lab resumes under the host's existing policy rather than preserving an
open pause menu.

## Preparation evidence and limits

The P95 pass prepared 80 admitted recordings in 81 returned provider attempts,
with one technical retry for Korean `episode.no_ordinary_post` and no final
generation failures. The 7,174 submitted text characters including that retry
have a $0.7174 estimate at the verified published API rate. The provider receipts
separately report 3,946 subscription credits; those credit units must not be
mistaken for submitted text characters or an additional cash invoice.
The pass conservatively accounts $1.4348 against its $10 ceiling. Subscription
counters confirm the same 3,946-credit consumption within existing quota.

Existing voices were used without paid auditions, custom voice creation or
artistic retakes. Original MP3s and their canonical provenance remain unchanged.
Decoding, source/hash checks and playback lifecycle evidence do not establish
pronunciation, acting quality or character fit. No listening verdict has been
performed; no listening or user quality approval is inferred.

See the [generation report](GENERATION_REPORT.md) and
[playback verification](../../../qa/voiceovers/REVIEW.md) for the completed pass.

## Runtime transmission processing (P99)

Afterlight's root selects Transmission Voice strength 0.65 for a projected
speaker whose display profile requests that preset. The story coordinates the
actual recorded speaker and current projection state. Eira's four ready lines
in each language route through the processor; protagonist replies remain
explicit `none`, and other voices/typing stay dry. Text Reveal Audio's optional
`voice_bus` separates that routing from its ordinary `bus`.

Stop the previous source before resetting filter history or deleting its private
bus. Pause/resume retains the route; language changes and replay rebind the
current ready recording, and Lab return creates a fresh isolated processor.
Effects never change source revisions or request generation. Dry/wet playback
and tuning use the same original files. [Processor contract](../../../presentation/audio/VOICE_PROCESSING.md)
and [native DSP evidence](../../../qa/transmission-audio/REVIEW.md) describe
verification; a listening-quality verdict has not been performed.
