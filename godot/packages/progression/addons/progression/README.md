# progression (addon payload)

Install this folder as `addons/progression/`. No other addon is required. Scripts are loaded with
`preload("res://addons/progression/<path>.gd")`; nothing is an autoload or a `class_name`.

| Folder | Role | Pure |
| --- | --- | --- |
| `design/` | `catalog.gd` validates a design and answers lookups; `builder.gd` builds the same design in code; `tables.gd` rolls weighted drops from a supplied draw | yes |
| `ledger/` | `ledger.gd` the document, balances, grant and spend, entry log; `levels.gd` tracks; `conditions.gd` objectives over measurements; `sources.gd` triggers into previews and claims; `mailbox.gd` mail | yes |
| `store.gd` | any document as one JSON file, atomic write, refusal that moves the file aside | no (filesystem) |
| `presenters/` | `result_screen.gd`, `reward_popup.gd`, `mailbox.gd`, `mail_button.gd`, `item_card.gd`, `style.gd`: code-built Controls, no media, chrome strings from the host with English defaults | no (Controls) |

## The design

One dictionary with `schema_version: 2`, from one JSON file, several merged, or the builder:

```json
{"schema_version": 2,
 "items": {"gold": {"type": "currency", "rarity": "common", "stack": 999999, "name_key": "item.gold"}},
 "curves": {"account": [100, 150, 220]},
 "measurements": {"fight_s": "number", "hits_taken": "integer", "died": "boolean"},
 "tables": {"drops": [{"item": "gem", "count": 5, "weight": 70}, {"item": "core", "count": 1, "weight": 30}]},
 "sources": {
   "arena.first": {"trigger": "stage:arena", "claims": "once", "name_key": "reward.first",
                   "bundle": [{"item": "gem", "count": 60}], "mail_on_claim": "first_clear"},
   "arena.clear": {"trigger": "stage:arena", "claims": "repeat", "name_key": "reward.clear",
                   "bundle": [{"item": "gold", "count": 150}, {"table": "drops", "rolls": 1}],
                   "exp": {"curve": "account", "amount": 120},
                   "objectives": [{"name_key": "obj.cleared", "condition": {"kind": "always"}},
                                  {"name_key": "obj.fast", "condition": {"kind": "below", "measure": "fight_s", "value": 120}}],
                   "objective_bonus": {"2": [{"item": "charm", "count": 1}]}},
   "daily": {"trigger": "login", "claims": "periodic", "period_s": 86400, "name_key": "reward.daily",
             "bundle": [{"item": "gold", "count": 50}]}},
 "mails": {"welcome": {"sender_key": "sender", "title_key": "mail.welcome.title", "body_key": "mail.welcome.body",
                       "attachments": [{"item": "gold", "count": 500}], "expires_days": null}}}
```

| Section | Rules |
| --- | --- |
| `items` | `type` currency or material; `rarity` common, rare, epic or legendary; `stack` above zero; `name_key` |
| `curves` | name to steps above zero: EXP to leave level 1, 2, ...; the last step repeats, so no cap |
| `measurements` | name to `number`, `integer` or `boolean`: what a report promises to carry |
| `tables` | id to entries `{item, count, weight}` with weights above zero |
| `sources` | `trigger` (any string the game reports); `claims` once (ever), repeat (every report) or periodic (`period_s` since the last claim); `name_key`; `bundle` of `{item, count}` or `{table, rolls}`; optional `exp {curve, amount}`, `objectives` (each `name_key` plus a condition), `objective_bonus` keyed by the count met, `mail_on_claim` |
| conditions | `always`; `is_true` on a boolean; `below`, `above`, `at_most`, `at_least` on a number; `equals` on either; every one names a declared measurement of a matching type |
| `mails` | `sender_key`, `title_key`, `body_key`, concrete `attachments`, `expires_days` null (keeps) or above zero |

Every `*_key` is resolved by the consumer's text callable; the package imposes no key scheme. Pass the
consumer's key list to `configure()` and a key the text set lacks is a configuration error. Unknown
sections (a game's own notes beside the design) are ignored. Any problem refuses the whole design and
keeps the previous one.

## The ledger document

```json
{"schema_version": 2, "created_at": 0,
 "balances": {"gold": 650}, "tracks": {"account": {"level": 2, "exp": 20}},
 "records": {"arena.clear": {"claims": 1, "first_claimed_at": 0, "last_claimed_at": 0, "best_met": 3}},
 "entries": [{"at": 0, "kind": "grant", "source": "arena.clear", "items": [{"item": "gold", "count": 150}]}],
 "mail": [{"id": 1, "template": "welcome", "sender_key": "...", "title_key": "...", "body_key": "...",
           "attachments": [{"item": "gold", "count": 500}], "sent_at": 0, "expires_at": null, "read": false, "claimed": false}],
 "mail_seq": 1, "delivered_once": ["welcome"]}
```

Balances are counts by item id and nothing more. The entry log keeps the newest 200 grants and spends;
the mailbox keeps at most 100 mails, evicting claimed ones first, oldest first. A mail is copied out of
its template at delivery. The store refuses a document of another schema by moving it aside and
starting fresh; there is no migration.

## A report, end to end

1. The game measures something and calls `sources.preview(ledger, design, "stage:arena", {fight_s: 84.0, hits_taken: 2}, now)` to show a result screen: which sources are claimable and why not, which objectives were met, the bundles and EXP.
2. On Claim it calls `sources.claim(...)` with the same arguments plus a `draw` callable when any bundle rolls a table. Every table is rolled and every refusal found before the first write; then grants, records, EXP per curve and the sources' mails are written.
3. It saves the ledger with `store.save_document(path, ledger)` and shows `granted` in the popup.

A mail claim, a shop purchase (`ledger.spend`, all or nothing) and a periodic login go through the
same ledger and the same popup.
