# Verification

The autonomous loop only works if "did the task" is a function the
loop can trust. This doc defines the verification ladder, recipes for
the typical stage-gen task shapes, and the evidence pattern subagents
must follow when reporting back. See `LOOP_PROMPT.md` for the loop
discipline that consumes these signals.

## The verification ladder

Three rungs, climbed only as far as the task requires.

| Rung | When | Cost | Examples |
|---|---|---|---|
| **1. Per-task verify** | Every task; the `::` command on the TODO line. | Cheap (sub-second to a few seconds). | `bun --version`, `tsc --noEmit`, `test -s file.png`, `jq -e '.mobs[0].name' spec.json` |
| **2. Per-stage smoke** | After a related cluster of tasks (e.g. all parallax-layer code is done). | Medium (10-60 s, may run one image-gen). | Run one parallax-layer generator end-to-end; assert PNG exists, has expected dimensions, alpha channel is non-empty |
| **3. Full pipeline** | At project milestones. | Expensive ($1-5, several minutes). | Run the orchestrator with `--no-play "snowy mountain platformer"`; assert all expected files in `out/<tag>/` |

The TODO author should pick the cheapest rung that actually proves the task
is done. Don't promote a task to rung 3 unless rung 1 cannot tell whether
it succeeded.

## Verification recipes

A catalog of one-liners for the kinds of tasks a stage-gen-style pipeline
generates.

### Generated image exists and is non-blank

The pipeline writes PNGs; "exists" is necessary but not sufficient — a
zero-byte file or a fully-transparent canvas means the call failed
gracefully.

```bash
# exists + non-empty
test -s out/$TAG/concept_$TAG.png

# minimum byte size (image-gen rarely produces <50 KB output)
test "$(stat -f%z out/$TAG/concept_$TAG.png)" -ge 50000

# correct dimensions (uses sharp via bun, no external dep)
bun -e "const s=require('sharp');s('$F').metadata().then(m=>{if(m.width!==1536||m.height!==1024)process.exit(1)})"

# non-blank: at least one pixel deviates from the corner pixel
bun -e "
import sharp from 'sharp';
const {data,info}=await sharp(process.argv[1]).raw().toBuffer({resolveWithObject:true});
const c=data[0]^data[1]^data[2];
let varied=0;
for(let i=0;i<data.length;i+=info.channels){if((data[i]^data[i+1]^data[i+2])!==c){varied++;if(varied>1000)process.exit(0)}}
process.exit(1);
" "$F"
```

### JSON conforms to schema

`world_spec_<tag>.json` is the contract every downstream image script reads.
Verify shape, not values (the agent invents the names).

```bash
# required top-level keys
jq -e '.world.name and (.mobs|length>0) and (.items|length==8) and (.layers|length>=1)' \
  out/$TAG/world_spec_$TAG.json

# mob ladder structural commitment
jq -e 'all(.mobs[]; .tier_label and .body_plan and .name and .brief)' \
  out/$TAG/world_spec_$TAG.json

# exactly one opaque layer
jq -e '([.layers[] | select(.opaque)] | length) == 1' \
  out/$TAG/world_spec_$TAG.json
```

For deeper structural checks, define a Zod schema module and parse:

```bash
bun -e "import {WorldSpec} from '<path to your schema module>'; \
  WorldSpec.parse(JSON.parse(require('fs').readFileSync(process.argv[1],'utf8')))" \
  out/$TAG/world_spec_$TAG.json
```

### TypeScript script builds clean

```bash
# single file
bun build --target=bun --no-bundle <your gen script> > /dev/null

# whole project type-check (slower but catches cross-file regressions)
bun x tsc --noEmit
```

`bun build --no-bundle` is the cheap rung-1 check; `tsc --noEmit` is rung 2.

### Web runtime loads without console errors

Phaser scenes can compile cleanly but throw at load time. Use a headless
puppet:

```bash
# starts the dev server, opens the route, fails on any console.error
bun x playwright test <your loads spec> --reporter=line
```

A starter spec for the web runtime's load test:

```ts
import {test, expect} from '@playwright/test';
test('scene loads without console errors', async ({page}) => {
  const errors: string[] = [];
  page.on('console', (m) => m.type()==='error' && errors.push(m.text()));
  await page.goto('http://localhost:3000/play?tag=' + process.env.TAG);
  await page.waitForSelector('canvas');
  await page.waitForTimeout(2000);
  expect(errors).toEqual([]);
});
```

### Pipeline cost stays under budget

Wrap the agent's bun calls in a token/cost tally. A cheap tripwire:

```bash
# total bytes returned by image-gen this run (proxy for cost)
du -sk out/$TAG | awk '{if($1>50000) exit 1}'
```

For accurate accounting, capture the OpenAI usage headers from each
per-asset generator and write them to `out/$TAG/_cost.jsonl`, then:

```bash
jq -s 'map(.usd) | add' out/$TAG/_cost.jsonl | \
  awk '{if($1>5.00) exit 1}'
```

### File hash sanity (caching contract)

Re-running the pipeline with the same prompt should be a no-op. Verify the
caching contract:

```bash
H1=$(find out/$TAG -name '*.png' -exec md5 -q {} \; | sort | md5)
bun <orchestrator script> --no-play "$PROMPT"
H2=$(find out/$TAG -name '*.png' -exec md5 -q {} \; | sort | md5)
[ "$H1" = "$H2" ]
```

### Bash script syntactic correctness

```bash
bash -n scripts/foo.sh
```

Always cheap, always worth running.

### Process exits cleanly under SIGINT

For any long-running subprocess (orchestrator, dev server):

```bash
timeout --preserve-status 5 <command>
test $? -eq 0
```

## The evidence pattern

The agent must produce a verifiable artifact for every `[x]`. "I read the
file and it looks fine" is not evidence. Acceptable evidence pointers:

| Kind | Format | Example |
|---|---|---|
| Commit SHA | `sha=<7-char>` | `sha=a3f9c01` |
| Generated file | `path=<repo-relative>` | `path=out/swamp1/concept_swamp1.png (210KB, 1536x1024)` |
| Test/log line | `log=<one-line excerpt>` | `log=tests passed (12/12) in 2.4s` |
| Screenshot | `png=<path>` | `png=tmp/screens/scene-loaded.png` |

Format on the line directly below the task:

```
[x] generate world concept for tag swamp1 :: test -s out/swamp1/concept_swamp1.png
  -> path=out/swamp1/concept_swamp1.png (212KB, 1536x1024) sha=a3f9c01
```

The runner does not parse the evidence pointer — it's there for the human
auditing the run after the fact and for follow-up tasks that need to refer
back to a previous artifact (e.g. "verify mob_concept matches concept's
palette").

## Non-deterministic outputs

Image-gen produces a different image every call. Verify **shape**, never
**content**:

| Verify | Don't verify |
|---|---|
| File exists | Pixel-exact match against a golden |
| File size > N bytes | Pixel-exact match against a previous run |
| Dimensions are exactly W×H | "Looks like a mountain" via vision LLM (expensive, flaky) |
| Alpha channel has both transparent and opaque pixels | Specific creature in specific pose |
| Magenta chroma key occupies expected region | "Colour palette matches" (use perceptual hash with wide tolerance only if you must) |

If you genuinely need semantic verification (rare), use a vision LLM with a
yes/no prompt and treat its answer as a soft signal — never as the gate
for marking `[x]`. Soft signals belong in evidence, not in the verify
command.

## Verify-script template

For TCs whose `check` is more than one line, factor it into a script
under `verify/` at the repo root and have the subagent invoke it. The
script returns exit code 0 on pass, non-zero on fail, and emits a
one-line evidence summary on stdout.

Template (`verify/_template.sh`):

```bash
#!/usr/bin/env bash
# verify: <one-line description of what this proves>
# usage:  bash verify/<name>.sh <args>
set -euo pipefail

TAG="${1:?usage: $0 <tag>}"
OUT="out/$TAG"

# 1. existence
test -s "$OUT/world_spec_$TAG.json" || { echo "missing spec"; exit 1; }

# 2. structural
jq -e '.mobs and .items and .layers' "$OUT/world_spec_$TAG.json" >/dev/null \
  || { echo "spec missing required keys"; exit 1; }

# 3. emit evidence to stdout (the agent can paste into the TODO)
SIZE=$(stat -f%z "$OUT/world_spec_$TAG.json")
MOBS=$(jq '.mobs|length' "$OUT/world_spec_$TAG.json")
echo "ok: world_spec ${SIZE}B, ${MOBS} mobs"
```

Three properties make a verify script good:

1. **Exit code only.** The runner checks `$?`. `set -euo pipefail` makes
   silent failures impossible.
2. **One concern per script.** Don't bundle "schema + cost + dimensions"
   into one verify; that's three tasks.
3. **Emit a one-line evidence summary on stdout.** The subagent copies
   that line into its return payload as the evidence pointer. No
   structured logging, no JSON.

## Task decomposition

If a TC's `check` cannot be expressed as a rung-1 signal, the TC is
too big. Split it into smaller TCs whose checks are each rung-1, and
let a higher-level TC encode the integration check at rung 2 or 3.

Bad — single TC trying to swallow a whole subsystem:

```
[ ] TC-XXX: parallax layer pipeline works
  check: ???
```

Good — a chain of small, individually-verifiable TCs that compose:

```
[ ] TC-AAA: world_spec.layers conforms to schema
  check: schema-parse exits 0 against the JSON
[ ] TC-BBB: parallax-layer generator produces a PNG at the contracted size
  check: file exists; dimensions read as 2400×800
[ ] TC-CCC: parallax-layer generator is wired into the orchestrator
  check: a full pipeline run produces every declared layer file
```

Each TC is something one fresh subagent can dispatch, verify, and
report back on inside a single iteration.
