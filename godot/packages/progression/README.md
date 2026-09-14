# Progression

A reward design contract and a ledger for Godot games, with optional claim screens. A game declares
what exists (items and currencies, level curves, the measurements it will report, drop tables, reward
sources, mail templates), validated as a whole before play; the package keeps one player's ledger
(balances, level tracks, source records, an entry log, mail) and answers every report with what it
granted or why it refused. It knows no game noun: measurements, names, the clock and randomness all
come from the consumer, and what an item *does* is the game's business.

The shape follows what the mobile games surveyed for it share: a source pays a one-time bundle or a
repeat bundle or a periodic one; objectives are measured conditions with a bonus per count met; a
bundle is a list of `{item, count}` and currencies are items; every grant ends in one "Obtained" panel;
mail keeps sender, title, body, attachments, sent and expiry times, read and claimed flags, stays as
read after a claim and offers Claim all.

## Install and try

Copy [`addons/progression/`](addons/progression/README.md) into a Godot 4.7 project's `addons/`,
preserving the license and the source UIDs. It declares no other addon. The
[payload README](addons/progression/README.md) is the contract; [`API.md`](addons/progression/API.md)
lists every call.

```sh
godot --path godot/packages/progression res://examples/fake_game/main.tscn -- --fresh
```

The [fake game](examples/fake_game/main.gd) is a consumer with no real game: buttons stand in for a
battle (two ways to win the arena with different measurements), a login (the daily gift), a shop (spend)
and the mailbox. Every package call a game makes is there in the open.

## Ownership

| The package owns | The consumer owns |
| --- | --- |
| validating the design; the ledger document and every mutation of it; claim lifecycle once / repeat / periodic; objective scoring; drop-table rolls from a supplied draw; mail lifecycle; atomic JSON persistence of any document | the design (JSON files or `design/builder.gd`), its text keys and the text lookup; the measurements and when to report a trigger; the clock (`now` in unix seconds) and the random draw; the ledger's path; the tree pause around a screen; what Continue and Exit do; its real inventory, shops and everything an item means |

The design and ledger halves are pure (`RefCounted`, static over dictionaries, no clock, filesystem
or engine nodes); `store.gd` and `presenters/` are the engine-facing edge a game may replace.

## Checks

```sh
godot --headless --path godot/packages/progression --script res://tests/run_checks.gd
godot --headless --path godot/packages/progression --script res://tests/run_example_checks.gd
python3 godot/packages/progression/tools/check_package.py
```

The first covers the design refusals, builder parity with JSON, tables, grant and spend, levels,
conditions, the source lifecycle, mail and the store. The second drives the fake game end to end;
`-- --capture <dir>` on a native renderer also writes one PNG per screen. The third is the shared SDK
package check (real files, UID sidecars, no dependency outside declared addons). All three are
registered with the [Godot verification coordinator](../../docs/verification.md).
