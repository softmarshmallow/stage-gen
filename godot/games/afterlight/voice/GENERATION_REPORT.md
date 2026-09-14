# Afterlight P95/P96 voice pass

This one-time preparation installed **80 recordings: 40 English and 40 Korean**
for the current main story, including both alternate replies. It kept all
approved display text unchanged. The protagonist's 18 unique lines in each
language are explicitly unvoiced (36 localized entries). Four localized choice
labels, menus, and technical studies were excluded.

| Speaker | English clips | Korean clips |
| --- | ---: | ---: |
| Nami | 14 | 14 |
| Yuzu | 9 | 9 |
| Sena | 5 | 5 |
| Riko | 6 | 6 |
| Eira | 4 | 4 |
| Keeper | 2 | 2 |

[cast.json](cast.json) records the selected existing voices, with a distinct
voice for each character within each language. No voice creation, paid audition,
or artistic retake occurred. Fourteen sparse speech scripts add supported
delivery tags or a pause; the remaining recordings use display text directly.
Removing speech-only tags preserves the original display words in every line.

## Usage and budget

- **Actual reported usage: 3,946 subscription credits.** The account counter
  increased from 36,841 to 40,787, exactly matching the 81 request receipts.
- The requests submitted **7,174 text characters**, including one technical
  retry. At the [published v3 API rate](https://elevenlabs.io/pricing/api) of
  $0.10 per 1,000 text characters, the equivalent is **$0.7174**. This is a
  published-rate valuation, not a separately observed invoice charge. Usage
  stayed within the account's existing 127,095-credit allowance.
- The $10 ceiling was a contingency. The initial six-attempt conservative
  reservation was $8.5344. The final conservative budget ledger holds $1.4348
  across all attempts; that reservation is also **not** an invoice.
- The provider's `character-cost` header measures subscription credit usage.
  Its initial conversion as text characters was corrected after reconciliation.
  Original receipts and the initial ledger are preserved; no audio or canonical
  provenance was changed during accounting reconciliation.

The sole retry was Korean `episode.no_ordinary_post`: two returned attempts,
34 credits each, followed by a validated recording. The existing speech service
owned that technical retry. Its first rejection detail was not retained, so
this report does not infer a specific decoding or level failure. There are
**zero unresolved failures** and one successful stored take per line/language.

## Verification and limits

All 80 clips passed fresh MP3 decoding and reuse checks against their audio hash,
canonical provenance, source revision, speaker, provider voice, language, and
generation settings. A credential-free preparation inspection reports all 80
ready, zero pending/blocked, and skips all 36 intentional-none entries. The
game's separate status export classifies authored freshness and media integrity.

The pass journal under the ignored `art/voiceovers-p95/` records the counts,
source text hashes, manifest digest, durations, and usage reconciliation.
[Playback QA](../tests/voiceovers/REVIEW.md) records the runtime lifecycle and
native mixer checks. The helper's six provider-free test groups verify explicit
none, lineage-aware reuse, charged rejection accounting, uncertain-outcome
stopping, path confinement, and pre-dispatch budget refusal.

**Listening review was not performed.** Decoding, native mixer output, and
subtitle screenshots do not approve acting, pronunciation, subtitle fidelity
by ear, or casting quality. Korean delivery uses the selected multilingual
voices; no claim of native-language casting or listening approval is made.
No word synchronization, voice processing for Eira's display, export packaging,
or automatic regeneration was introduced.

The runtime never imports preparation code. Changed source makes an affected
recording stale and invokes the host's fallback until a separately requested
manual refresh. Refer to the [voice contract](README.md) for policies, statuses,
and the offline status command. Immutable local MP3s, canonical sidecars, the
exported source, and request ledger remain under `art/voiceovers-p95/`; only
their portable gameplay bindings and preparation source are tracked.

## 2026-09-14 Korean recast

The 40 Korean recordings were replaced. The English recordings are unchanged.
The P95 Korean voices were chosen from account metadata and read as narration,
so each character now uses a voice a person auditioned and accepted, listed in
[ElevenLabs v3 anime voices](../../../../docs/models/elevenlabs-v3-anime-voices.md):

| Speaker | Korean clips | Voice |
| --- | ---: | --- |
| Nami | 14 | Seyana Seya |
| Yuzu | 9 | Yuki |
| Riko | 6 | Sameno |
| Sena | 5 | Aki |
| Eira | 4 | Yooni |
| Keeper | 2 | Annie |

Every Korean line now has a directed speech script in [voices.json](voices.json):
96 v3 delivery tags chosen from each line's place in the story, recorded at
stability 0 so the model follows them. Removing the tags gives the display text
word for word.

The pass used a Korean-only inventory, because the English clips' provenance
sidecars no longer sit beside them, and only the Korean manifest entries were
swapped. It submitted 3,565 characters and the provider reported 1,959 credits,
about $0.36 at the published rate. The only retry was `episode.the_signal`: two
attempts at 46 credits each. The ledger, sidecars and inventory are under the
ignored `art/voiceovers-ko-v2/`; the previous Korean takes are kept under
`art/voiceovers-p95/clips/ko/`.

The voices were accepted by ear, but the 40 recorded takes have not been listened to yet.
