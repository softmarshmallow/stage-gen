# progression API

Every function is static unless noted; every result that can refuse carries `errors: Array[String]`,
empty on success. `catalog` is a configured `design/catalog.gd` instance; `doc` the ledger document;
`now` an integer unix second the consumer supplies; `draw` a `Callable() -> float` in [0, 1).

## design/catalog.gd (instance)

| Call | Answers |
| --- | --- |
| `configure(design: Dictionary, text_keys: Array = []) -> Array[String]` | validates the whole design; keeps the previous one on any error |
| `item(id)`, `curve(name)`, `measurement_type(name)`, `table(id)`, `source(id)`, `mail_template(id)` | the validated entry or an empty value |
| `sources_for(trigger) -> Array` | source ids listening to a trigger, in id order |
| `exp_to_leave(curve, level) -> int` | the step for that level; the last step repeats; 0 for an unknown curve |
| `validate_bundle(bundle, where, errors, known_items = items, known_tables = tables) -> Array` | the clean copy of a bundle |
| static `merge(bundles) -> Array` | concrete entries summed by item, first-seen order; table entries kept |
| static `is_concrete(bundle) -> bool` | no table entry left |

## design/builder.gd (instance, chainable)

`item(id, type, rarity, stack, name_key)`, `curve(name, steps)`, `measurement(name, type)`,
`table(id, entries)`, `source(id, trigger, claims, name_key, bundle, options = {})` with options
`exp`, `objectives`, `objective_bonus`, `period_s`, `mail_on_claim`, static
`objective(name_key, kind, measure = "", value = null) -> Dictionary`, `mail(id, sender_key,
title_key, body_key, attachments, expires_days = null)`, `build() -> Dictionary`.

## design/tables.gd

| Call | Answers |
| --- | --- |
| `roll(table: Array, draw) -> {item, count}` | one weighted pick |
| `resolve(bundle, catalog, draw) -> {bundle, errors}` | the concrete merged bundle; a table with no valid draw is an error |

## ledger/ledger.gd

| Call | Answers |
| --- | --- |
| `create(now) -> Dictionary` | a fresh document |
| `validate(doc) -> Array[String]` | schema and shape problems |
| `balance(doc, id) -> int` | |
| `grant(doc, catalog, bundle, source, now) -> {granted, lost, errors}` | concrete bundle only; `lost` is what stack limits refused |
| `spend(doc, catalog, bundle, source, now) -> {spent, shortfall, errors}` | all or nothing; `shortfall` names what was missing |
| `entries(doc, kind = "") -> Array` | the log newest first, optionally one kind |

Constants: `SCHEMA_VERSION`, `ENTRIES_CAP`, `MAIL_CAP`.

## ledger/levels.gd

| Call | Answers |
| --- | --- |
| `state(doc, catalog, track) -> {level, exp, to_next}` | creates the track at level 1 on first sight |
| `add_exp(doc, catalog, track, amount) -> {track, level_before, exp_before, level, exp, level_ups, errors}` | |

## ledger/conditions.gd

| Call | Answers |
| --- | --- |
| `evaluate(condition, measurements, catalog) -> {met, errors}` | a missing or mistyped measurement is an error |
| `objectives_met(objectives, measurements, catalog) -> {met: Array[bool], count, errors}` | |
| `label_values(condition) -> Dictionary` | `{value}` for a condition's text, whole floats without `.0` |

## ledger/sources.gd

| Call | Answers |
| --- | --- |
| `record(doc, id) -> Dictionary` | the source's record, created on first sight |
| `can_claim(doc, catalog, id, now) -> {ok, reason, next_at}` | reason `""`, `unknown_source`, `already_claimed` or `period_not_elapsed` |
| `preview(doc, catalog, trigger, measurements, now) -> {rows, errors}` | one row per listening source: `id, name_key, claims, claimable, reason, next_at, bundle, objectives [{name_key, condition, met}], objectives_met, bonus, exp, mail_on_claim, record` |
| `claim(doc, catalog, trigger, measurements, now, draw = Callable()) -> {claimed, granted, lost, exp, mails, rows, errors}` | every claimable row granted; `exp` one entry per curve; `mails` the ids delivered; nothing written on any error |

## ledger/mailbox.gd

`deliver(doc, catalog, template_id, now)`, `deliver_custom(doc, mail, now, expires_days = null)`,
`deliver_once(doc, catalog, template_id, now)`, `inbox(doc, now)`, `find(doc, id)`,
`unread_count(doc, now)`, `claimable(doc, now)`, `mark_read(doc, id)`, `claim(doc, catalog, id, now)`,
`claim_all(doc, catalog, now)`, `is_expired(mail, now)`, `days_left(mail, now)`,
`prune_expired(doc, now)`, `evict(doc, cap = MAIL_CAP)`.

## store.gd

| Call | Answers |
| --- | --- |
| `load_document(path, validate: Callable, create: Callable, now) -> {document, fresh, refused, errors}` | a refused or unreadable file is moved aside and a fresh document created |
| `save_document(path, doc) -> Array[String]` | atomic: temp file then rename |

## presenters (nodes; add as children, they are CanvasLayers)

| Script | Calls and signals |
| --- | --- |
| `result_screen.gd` | `open(view, catalog, text, labels = {})`, `set_claiming(on)`, `show_result(level_result)`, `close()`, `is_open()`; signals `claim_pressed`, `continue_pressed`, `exit_pressed`. `view`: `title, subtitle, objectives [{name, met}], record_line, rows [{name, bundle}], track {level, exp}, exp_to_leave: Callable(level)`. Labels: `claim, continue, exit, level "Lv. {level}", exp, level_up, random` |
| `reward_popup.gd` | `open(entries, catalog, text, labels = {}, lost = [])`, `close()`, `is_open()`; signal `closed`. Labels: `title, tap_to_close, stack_full "{items}"` |
| `mailbox.gd` | `open(catalog, text, now, mails, labels = {})`, `refresh(mails, keep_id = -1)`, `close()`, `is_open()`; signals `closed`, `selected(id)`, `claim_requested(id)`, `claim_all_requested`. Labels: `title, close, claim, claimed, claim_all, empty, attachments, days_left "{days}", keeps` |
| `mail_button.gd` | `place(viewport_size)`, `unread`; signal `pressed` |

`text` is `Callable(key: String, values: Dictionary = {}) -> String`. The presenters take the mouse only
on their buttons and veils; every other Control ignores it. They run on real time and keep running under
a paused tree; the consumer decides whether to pause.
