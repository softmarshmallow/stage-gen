# Manual Afterlight voice preparation

[prepare_afterlight_voice.py](prepare_afterlight_voice.py) is a local preparation
command for the P95/P96 voice pass. Godot never imports it or requests speech
generation. Later wording or casting changes require an explicit manual refresh;
launching, playing, changing language, and inspecting voice status spend nothing.
This is not a new generation package, provider adapter, or background sync service.

Afterlight owns the source: its story and paired text, `voice/voices.json` policy
and separate speech scripts, and `voice/cast.json` provider casting. Its
`voice/export_inventory.gd` exports the resolved inputs. Each language/line has a
stable `line_id`, actual `speaker_id`, `display_text`, `speech_text`, explicit
`voice_policy`, selected `voice_profile`, and `source_revision`. Alternative
replies retain their actual speakers. Intentional `none` skips generation even
if a clip exists. The protagonist is unvoiced for this pass. Choice-button labels
are excluded by the host exporter.

The helper preserves the host's revision and adds a digest of immutable source
and generation fields. Status, path, and missing-asset diagnostics do not enter
that digest. A different display, speech script, language, speaker, provider,
model, selected voice, setting, or source revision gets a different preparation
identity. Existing recordings remain unchanged. Host status distinguishes current
authored freshness; a saved export only describes the source at its export time.

## Commands

Run from the repository root. Export the current authored source:

```sh
Godot --headless --path godot/games/afterlight --script res://voice/export_inventory.gd -- --output /tmp/afterlight-voice-inventory.json
```

Inspect preparation and cost without credentials, network access, or writes:

```sh
.venv/bin/python godot/games/afterlight/tools/prepare_afterlight_voice.py --inventory /tmp/afterlight-voice-inventory.json --quote godot/games/command_link/art/voiceovers-p95/quote.json
```

Paid dispatch is a separate explicit action. It uses the existing allowlisted
provider-key loader and requires both flags:

```sh
.venv/bin/python godot/games/afterlight/tools/prepare_afterlight_voice.py --inventory godot/games/command_link/art/voiceovers-p95/inventory.json --quote godot/games/command_link/art/voiceovers-p95/quote.json --live --yes
```

The default pass directory is `art/voiceovers-p95/`; generated MP3s and their
original `.meta.json` provenance stay under `clips/<language>/`. The candidate
manifest is `art/voiceovers-p95/manifest.json`. Its `res://` paths can be used
locally without copying audio. `--manifest` selects an explicit project-local
manifest destination. Every output path rejects traversal and symlink escapes.
An exclusive pass lock prevents overlapping invocations from spending twice.

## Budget and technical retries

The quote requires `schema_version: 1`, `budget_usd` at most 10,
`usd_per_character`, `max_character_cost_multiplier` at least 1, and a documented
`pricing_basis`. The P95 quote uses the verified published rate of $0.0001 per
character and a 2× reservation bound. At 7,112 spoken characters, the initial
plan is $0.7112 for one take each; the conservative reservation is $1.4224 for
one attempt each, or $8.5344 for the maximum six technical attempts. These are
rate conversions, not an assertion of a separate invoice charge when the
account consumes included subscription credits.

The entire remaining batch's six-attempt bound must fit before dispatch. The
existing `SpeechGenerationService` is the sole retry owner, with its original
maximum of six attempts and capped backoff. A small wrapper around the existing
`ElevenLabsSpeechBackend` atomically journals a reservation **before** each
request. It records every returned `character-cost` and request ID before audio
admission, so rejected charged audio is counted. That provider header reports
subscription credit units; the USD estimate separately uses submitted text
characters at the published API rate. Credits are never substituted for text
character count in that estimate. Every attempt retains the full 2× reservation
in `accounted_usd`, including returned requests; `estimated_text_usd`,
`submitted_characters` and `reported_credits` are separate measures. No artistic retakes, auditions, voice creation,
post-processing, or outer retry loop is part of this command.

A transport failure, cancellation, or provider failure with uncertain outcome
retains its conservative charge and stops the service. A later invocation will
not resend that line automatically. An interrupted reservation, partial bundle,
failed admission with no completed bundle, or exhausted line likewise blocks
the pass for reconciliation. Inspect the durable ledger and provider history,
recover an already completed response if possible, and preserve the attempt and
charge evidence. Do not delete the ledger or start a new pass merely to bypass
this guard. There is deliberately no automatic reconciliation or force-retake
command.

## Artifact admission and reuse

The existing speech route emits `mp3_44100_192`, with verbatim text, the selected
voice, language, and v3 stability. Its objective validator decodes the audio and
checks level; the existing service writes the MP3 and canonical provenance as
an atomic bundle. The helper admits reuse only when the source fields, artifact
hash and length, provider/model/voice/settings, and provenance agree, and a fresh
decode succeeds. A valid bundle recovered after interruption is reused without
another provider call. A corrupt bundle is reported for reconciliation.

Ready manifest records contain the host source revision, preparation revision,
audio/provenance hashes, original provenance path, decoded duration, actual
speaker, and provider profile. They record `listening_verdict: not_reviewed`:
decoding and level checks do not establish acting quality, pronunciation,
character fit, user approval, or publication rights. The original provenance
keeps generated media rights unreviewed.

P95 produced 80 recordings in 81 returned attempts, including one technical
retry: 7,174 submitted characters, a $0.7174 published-rate estimate, and 3,946
reported subscription credits. The final conservative budget accounting is
$1.4348, also not an invoice. Account subscription counters independently confirm
3,946 credits consumed within existing quota. The initial ledger that incorrectly
treated credit units as text units is preserved as `ledger.initial-accounting.json`;
the corrected ledger retains its original receipt values and initial estimate
for audit. These are distinct measures. There were 36
intentional localized skips and no final generation failures. A listening
verdict was not performed.

The focused provider-free check is:

```sh
.venv/bin/python -m pytest -q godot/games/afterlight/tests/python/test_afterlight_voice_preparation.py
```

The local ignore rules explicitly allow this focused Python test source to be
tracked alongside the Godot QA scripts; generated pass output remains ignored.
