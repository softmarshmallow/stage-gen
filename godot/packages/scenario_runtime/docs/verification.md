# Scenario verification

Scenario owns its compiler, execution, host, presenter, compatibility and assembly
checks. Named games own whole-game behavior and artistic integration. The
[Godot coordinator](../../../docs/verification.md) discovers the maintained suites
and reports deferred prerequisites explicitly. It is the current coverage roster.

From the repository root, using the development environment:

```sh
uv run --group games python godot/tools/check.py --owner scenario_runtime
uv run --group games python godot/tools/check.py --owner vn
```

Use `--list` to inspect registered owner/suite names and prerequisites. Direct
package checks also work without named games or generated media:

```sh
godot --headless --path godot/packages/scenario_runtime --script res://tests/run_session_checks.gd
godot --headless --path godot/packages/scenario_runtime --script res://tests/run_checks.gd
godot --headless --path godot/packages/scenario_runtime --script res://tests/run_embedding_checks.gd
godot --headless --path godot/packages/scenario_runtime --script res://tests/run_host_checks.gd
godot --headless --path godot/packages/scenario_runtime --script res://tests/run_example_checks.gd
```

The [Python distribution](../authoring/README.md#verification) can be tested and
built independently. Its tests include a real wheel consumer that cannot import
Stage Gen, GNode or the game collection. Shared conformance source/program/catalog
fixtures are compiled by Python and executed by Godot. The production adapter's
tests live under `games/_shared/python/tests/scenario_production_tests`.

| Owner/check family | Evidence |
| --- | --- |
| Compiler and catalog | Source diagnostics, stable IDs/maps, typed parameters, closed fields, bounded macro expansion, references and flow refusals |
| Session | Ordered choices/facts/gates/cues, independent clocks, scoped operations, stale completion refusal, suspension and snapshot admission |
| V2 facade | Supported prepared program/state/action/event behavior and strict snapshot boundary |
| Host | Channel conflicts, grants, capability validation, owned cleanup and adapter feedback |
| Dialogue/anchors | Optional portraits and reflow; world/canvas projection, moving anchors and loss policy |
| Procedural examples | Host simulation continues during dialogue; world bubbles; preset/inline effects use one mechanism |
| Content package bridge | Python-written file hashes and capability closure accepted/refused by native activation; immutable revisions and active-session isolation |
| Starter assembly | Real source/dependency copying, licenses/UIDs, confined fresh destination, source hashes |
| Starter gameplay | Both replies, reveal/input gates, mandatory contact, feedback timing, pause/restart and supplied voice precedence |
| Game consumers | Their own routes, cases, text, voice, timing, camera/effects and prepared input compatibility |

The promotion's focused native evidence includes v3 core checks, the unchanged
v2 suite, embedding/host checks, all three procedural examples and two independently
assembled content revisions consumed by the same player. Fresh aggregate results
and any media/rendering prerequisites belong to the coordinator report rather
than a permanently copied test count in this document.

Structural/headless tests prove inspected behavior, not visible composition or
listening quality. Native capture/play-through and audio listening are separate
verdicts. Media is neither generated nor refreshed by these checks. Source package
assembly, a running PCK and a published platform release are also separate claims.

## Measured execution cost

The promotion was measured on an Apple M4 Pro with Godot 4.7.2, using the same
frozen Afterlight content and 600 fixed 60 Hz game ticks at the opening and final
live line. Drawing was disabled for both implementations. The complete episode
had 57 visited presentations and 348 historical operations at its final line.

| Final-line CPU time before drawing | Mean | p95 |
| --- | --- | --- |
| Former game-local director | 0.152 ms | 0.174 ms |
| Scenario after active-operation indexing and per-visit gate reporting | 1.523 ms | 2.047 ms |

Admission happens before execution; steady ticks do not parse source, resolve the
catalog or load media. Scheduling follows active operations. Transactional state
copies and returned state reports still include saved history, so the richer
runtime has a measured cost and long-running invocations can grow. This result
does not claim faster execution than the former director, rendered FPS, audio
latency or a bound for every future game. Keep invocations scoped to their owned
sequences and measure larger content before extending this workload.
