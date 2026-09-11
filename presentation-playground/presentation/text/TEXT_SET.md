# Text Set

A small instance-local dictionary lookup. It receives language sets and returns
text by stable key. It knows no game, scene, font, story, file path, global
locale, or UI. Afterlight supplies English and Korean JSON dictionaries; its
root and routes own language selection and rendering.

## Contract

| API | Behavior |
| --- | --- |
| `configure(sets, preferred_language = "en", fallback_language = "en")` | Validate and copy flat string dictionaries. Returns errors; invalid configuration leaves the instance unchanged. Selected and fallback sets must exist. |
| `set_language(code)` | Select a configured set; unknown codes return errors without mutation. |
| `get_language()` | Read the selection. |
| `text(key, values = {})` | Resolve current language, then fallback, then visible `[key]`. Substitute named `{values}` without executing code. |
| `text_in_language(key, language, values = {})` | Resolve a specified language with the same fallback, without changing the selection. |
| `missing_keys(language)` | Sorted keys absent from a set, for review/checks. |

The fallback set defines the keys. Extra translated keys, non-string/empty
values, and mismatched named placeholders are rejected. Partial translations
may omit keys for fallback; Afterlight's pair currently covers every key.
Placeholder names use lower_snake_case inside braces, such as `{guest}` and
`{progress}`. Missing supplied values remain visible as placeholders.

This utility does not perform plural selection, grammatical inflection,
date/number formatting, locale detection, translation generation, or text reveal.
Never use translated strings as actor, choice, route, or story identifiers.

## Afterlight integration

The root reads its own `text/en.json` and `text/ko.json`, binds story text using
actor/choice/monologue IDs, and provides a fresh Text Set per route. It retains
language during route changes for this run. New runs default to English;
`--language ko` selects Korean. No language preference is written to disk and
Command Link's text is unchanged.

The host's button or F6 refreshes static labels and dynamic text in place.
World state, camera clocks, guest and choice IDs remain unchanged. Story
monologues retain reveal phase and normalized fractional progress. Restoring
an older route snapshot validates text against its stable key/source language,
then maps progress into the selected translation. In the Intertitle study,
the authored sample translates; player-entered text and its timing stay intact.

Typography remains host-owned. Route-local SystemFont searches installed
Hangul-capable fonts: Apple SD Gothic Neo, Noto Sans CJK KR, Noto Sans KR,
Malgun Gothic, then sans-serif. Native checks verify every current Hangul
syllable on this Mac. No system font is copied into the project; portable export
needs an available CJK font or a licensed bundled font. Godot-owned widget
internals, such as the color picker popup, are outside the host's text set.
Internal diagnostic strings remain English.

## Check

```sh
Godot --headless --path presentation-playground --script res://qa/afterlight_language_checks.gd -- --game bishoujo_afterlight
```

For native Korean rendering, scaled input, and captures, omit `--headless` and
add `--capture-language` after the `--` separator.
