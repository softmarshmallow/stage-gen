# Scenario authoring

`stagegen-scenario` is the independently installed Python authoring distribution
for the Godot-owned Scenario runtime. Its import namespace is
`scenario_authoring`. Python 3.12 and Pydantic are its runtime dependencies.
Compilation, admission, inspection and packaging import neither Stage Gen nor
GNode, Godot, a game, or a provider.

The game owns a Scenario invocation. Authored content describes its dialogue,
permitted presentation and progression; it does not create or own the game.
The package [invocation contract](../docs/contract.md) owns execution semantics.

## Author a sequence

Every instruction has a stable `@id`. File order supplies the next instruction
when it is unambiguous. Choices and branches name explicit targets. IDs survive
comment changes and insertion of other instructions; edits still produce a new
program identity and require the runtime's content/save compatibility policy.

```text
scenario arrival
speaker guide "Guide"
fact accepted = false

@opening
guide key greeting profile=bottom
    gate text_revealed finish_on_advance=true

@decision
menu text="Come with me?" speaker=guide:
    yes "Yes." -> accepted set={"accepted":true}
    no "Another time." -> declined

@accepted
guide "Then we go together." profile=bubble

@accepted_end
end accepted

@declined
guide "I will wait here."

@declined_end
end declined
```

Literal dialogue is `speaker [expression] "Text"`; narration is `"Text"` or
`narrate "Text"`. Localized text uses `speaker key text_id` or `narrate key text_id`.
A menu can omit its prompt. An optional expression names presentation data and
does not require a front-facing actor slot or a portrait.

`profile`, `channel`, `portrait` and `anchor` are concise presentation fields.
Richer presentation is authored as an object, which may span multiple lines:

```text
@contact
guide key contact_caption
    present {
        "profile": "front_view",
        "portrait": false,
        "camera": {"target": [0.2, 0.5], "duration": 1.5}
    }
    gate operation_completed:contact finish_on_advance=false
    advance_mode on_gates
```

The game-installed presentation profile decides which of its declared fields it
supports. The compiler treats the presentation object as data; it does not
invent a camera or execute an arbitrary function. The same line can instead use
a bottom panel or a host-bound world bubble.

Facts are booleans or finite string choices. `fact door_open external = false`
declares a game-supplied fact. Only ordered host updates can change external
facts; `set` and option assignments can change local facts. A string declaration names its full domain,
for example `fact reply = "unset" in ["unset", "yes", "no"]`. Assignments are
`set accepted=true`; option `if={"accepted":true}` tests declared facts. A branch
uses indented `if {"accepted":true} -> target` edges and one `else -> target`.
There are no arithmetic expressions, code evaluation or embedded host callbacks.

## Effects and reusable direction

An effect is either a named game catalog noun or an inline installed type. Both
resolve through the same parameter schema, validation and default handling.

```text
@embers
start ember_preset as hall_embers target=air scope=sequence

@reaction
guide "Look up."
    cue glint at 0.85 start particle({"sprite_id":"spark","rate":6}) as glint duration=0.2
    cue emphasis on text_revealed after 0.1 start ember_preset as glow scope=sequence duration=0.5

@settled
wait operation=glow

@cleanup
stop hall_embers

@done
end complete
```

The installed capability schema must actually declare these types and parameters.
A cue uses `at seconds` or `on event after seconds`, including
`operation_completed:<instance_id>`. Standalone effects default to `scope=sequence`;
line/menu cues default to `scope=node`. Effect clocks default to `presentation`.
A time wait is `wait duration=1 clock=sequence`; another suspension is
`wait event=contact`. The runtime owns the meaning of clocks, suspension,
completion, cancellation and input gates.

Catalogs have `kind="scenario-catalog"`, `schema_version=1`, `catalog_id`, a
nonempty immutable revision **string**, and `definitions`. Each definition names
an installed `type`, `parameters`, and an optional `overrides` list. A preset
cannot override an unexposed parameter. Installed types declare a positive
integer version and typed parameter schemas. Unknown types/versions and invalid
parameters fail before execution. A new data-defined noun needs no language
keyword or player update when its capabilities are already installed.

Reusable source sequences expand into the same compiled instruction model:

```text
sequence greeting:
    @hello
    say $speaker "$words"

@first_visit
use greeting with={"speaker":"guide","words":"Hello."}
```

Exact `$parameter` values are substituted as data; arbitrary expressions and
partial string evaluation are absent. Expansion prefixes local node and operation
IDs with the invocation ID. Local branch targets follow the same remapping, and
final fallthrough continues after the use. Calls may nest, but recursion is
refused; expansion is capped at 10,000 nodes and 32 levels. This authoring reuse
does not create a second execution model or a runtime code-binding mechanism.

## Python and CLI

```python
from scenario_authoring import compile_scenario

compiled = compile_scenario(
    'scenario hello\n@hello\n"Hello."\n@done\nend complete\n',
    source_name="hello.scenario",
)
program = compiled.program
source_map = compiled.source_map
```

Pass game-owned catalog and installed capability dictionaries as `catalog=` and
`capabilities=`. `admit_program` validates already compiled JSON using a catalog
returned by `read_catalog`. `Compilation` exposes canonical `program_bytes`,
`program_sha256` and the exact `source_sha256`. Source maps identify authored
lines and reusable-sequence definitions without embedding checkout paths.

After installing this distribution:

```sh
scenario-authoring check episode.scenario --catalog catalog.json --capabilities capabilities.json
scenario-authoring compile episode.scenario --catalog catalog.json --capabilities capabilities.json \
  --output episode.json --source-map episode.map.json
scenario-authoring check episode.json --compiled --catalog catalog.json --capabilities capabilities.json
scenario-authoring inspect episode.scenario --catalog catalog.json --capabilities capabilities.json
scenario-authoring preview-input episode.scenario --catalog catalog.json --capabilities capabilities.json \
  --output preview.json
```

`python -m scenario_authoring` exposes the same commands. `preview-input` assembles
program/catalog/source-map data for a game-owned preview; it does not claim to
render a game, choose assets or grant presentation capabilities. CLI failures
return exit code 2 with a JSON diagnostic. Source strings use JSON quoting and
named values; lines beginning with `#` are comments.

## Content packages

A game may obtain a content directory by any delivery mechanism. These tools
assemble and verify a local data closure; they never download or generate files.

```sh
scenario-authoring pack --source-root content --output new-episode \
  --package-id episode --revision 1 --catalog catalog.json \
  --program arrival=programs/arrival.json --asset text/en.json \
  --capabilities capabilities.json
scenario-authoring check-package new-episode --capabilities capabilities.json
```

`scenario-package.json` contains the package ID and positive integer revision,
Scenario version, catalog member path, scenario-to-program map, required
capability versions and explicit `{path, sha256, bytes}` file records. It is
excluded from its own file inventory. Catalog revision and content-package
revision are separate identities.

Paths are confined to the source root; traversal, aliases, symlinks, executable
Godot files and unlisted members are refused. Output must be a fresh directory.
The writer validates the complete candidate before installing it atomically.
The reader refuses mismatched digests, identities, capabilities and unknown
files. Limits match the runtime loader: a 2 MiB manifest, 4,096 member files and
512 MiB of member bytes. Resource binding,
localization selection, activation and persistence remain game-owned.

## Supported v2 input

`scenario_authoring.compatibility.v2` preserves the earlier narrative parser,
compiler and bounded admission. Its compiler values contain no game IDs, input
member paths, background briefs or music-generation intentions.

The game-owned `demo_game_tools.scenario` adapter reads existing `scenarios/*.toml`
packages, verifies their script digests and retains production metadata. During
migration it continues emitting the existing `scenario-program-v2` envelope.
Imported flags remain writable within an invocation, matching the supported v2
implementation. V2 admission records reachable states and ending witnesses; it
does not prove every possible path terminates or that presentation succeeds.

## Verification

From this directory:

```sh
uv sync --group dev
uv run --group dev python -m pytest
uv build --wheel
```

Owned tests cover current source/catalog/program conformance, invalid references,
typed parameters, data-only sequence expansion, stable source maps, CLI behavior,
package closure/refusals, retained v2 parsing and flag liveness. An actual wheel
consumer compiles v2 and v3 with site initialization disabled and no repository
source paths. The shared [conformance fixtures](../conformance/authoring/bridge.scenario)
are also admitted by the Godot reader's owned checks.
