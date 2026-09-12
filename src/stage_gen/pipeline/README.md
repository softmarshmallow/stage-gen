# Asset pipeline authoring

`stage_gen.pipeline` runs caller-defined GNode graphs. A definition is ordinary
Python: a graph-building function plus node types and their async implementations.
It requires no game TOML, genre, recipe subclass, repository fixture, or provider.

```python
from pathlib import Path
from stage_gen.pipeline import load_definition, plan, run, inspect

definition = load_definition("./my_assets.py:pipeline")
planned = plan(definition, input_root=Path("./inputs"), targets=["swatch"])
result = await run(
    planned,
    output_root=Path("./runs/first"),
    cache_root=Path("./cache"),
    services={},
)
assert result.summary.ok
view = inspect(result.run_dir)
```

`define(pipeline_id, title=..., build=..., bindings=...)` returns a
`PipelineDefinition`. `build(InputFiles)` returns any sealed `gnode.Graph`.
`NodeBinding(NodeType(...), handler, admit=None)` binds a node declaration to an
async `handler(node, context) -> NodeExecutionResult`. Existing GNode subgraph
builders can be composed directly. The harness normalizes the graph header into
`pipeline-execution-graph-v1`; it preserves every node, route, and node cache key.

The loader accepts `module:attribute` or `file.py:attribute`; the default attribute
is `pipeline`. The export can also be a zero-argument factory returning a definition.
Loading a definition executes caller-owned Python code. The harness is not a sandbox.

For a file reference, its parent directory is temporarily importable while the file
and exported factory execute. Adjacent helpers such as `from asset_nodes import build`
therefore work when the command runs from another directory. The loader restores
`sys.path` afterward and never changes the working directory. Imported helpers retain
normal Python module caching; file loading does not create an isolated module namespace.
Import helpers during definition loading and retain those references in handlers.
A new import delayed until node execution must resolve through the application's
normal import path. Prefer an installed package and `my_app.assets:pipeline` for larger
applications, package-relative imports, or modules shared across several pipelines.

The CLI's `--live` flag admits provider-capable nodes; it constructs no provider
services and supplies an empty `services` mapping. An exported definition or
zero-argument factory can bind handlers that close over the author's configuration
and service objects. Those handlers must own their service lifecycle, for example
with an async context manager. For centralized injection and cleanup, call the Python
`run(..., services=...)` API from an application-owned async service context.

## Inputs and cache identity

Read authored input through `InputFiles.read`, `.text`, or `.digest` while building
the graph. Include each file's `.digest(ref)` in the consuming node's
`input_digests`. A read that is not bound to any node is refused. At execution,
`context.read_input(ref)` permits only inputs bound directly to that node and
verifies their captured hashes. If inputs changed after planning, plan again.

The graph builder owns cache keys. Bind every output-affecting parameter, prompt,
source file, and implementation version into node identity. Parameters and card
text alone do not change a GNode cache key. `NodeType.contract_version` is the
implementation contract version. Changing it invalidates that type's output.

`context.read_artifact(ref)` reads and verifies a material direct dependency's published
output. A dependency excluded by `cache_depends_on` is an ordering barrier: its outputs
cannot be read through this helper and do not enter local content provenance.
Cache admission checks every artifact's hash, declared output set, and
upstream content lineage; `NodeBinding.admit` applies the same content validator
before fresh publication and cache restoration. A corrupt or rejected cache is a
miss. Independently keyed branches remain reusable when another input changes.

## Publication and services

`await context.publish(node, {port_id: bytes}, ...)` publishes exactly the declared
ports. `artifact_port` declares an artifact with canonical provenance;
`record_port` declares a record without a sidecar. Supply `media_types` when an
extension does not describe the bytes. `validate` can raise before publication;
the binding's `admit` also runs before publication. Each directory's artifacts and
sidecars use GNode's existing rollback-safe atomic bundle writer. A node is successful
only after its full declared output set has been admitted and cached.

Local outputs get portable provenance recording node identity and source digests.
Provider outputs must pass service-produced `ProvenanceInput` records through
`provenance={port_id: record}`. Provider operations retain the service's retry owner;
the harness does not add a retry loop. Pass the service's attempts, operation count,
and known cost through `publish` when reporting its result.
If subsequent cache persistence fails, the node fails while retaining those reported
attempts, operations, and costs in its trace and summary.

Services are injected through `run(..., services={...})`. The caller owns service
construction, credentials, and lifecycle. The harness imports no application
orchestration or provider factories. Selected nonlocal nodes require explicit
`allow_provider_calls=True` before any output or cache write. This declaration gate
cannot prevent trusted custom Python from making its own network calls.

Input, output, and cache roots are caller-owned. `output_root` must be a new run
directory and must not overlap `cache_root`. Existing roots and their parents must
be directories; this is checked before publishing the run or executing nodes.
Relative artifact references reject
traversal, symlinks, duplicate addresses, and collisions with execution records.
Only portable input references and digests are persisted; root paths remain in memory.
Keep credentials and private paths out of graph parameters and custom annotations.

## Planning and inspection

`targets` selects the requested nodes and their ancestors. Projection spans, cost,
and operation counts describe that closure; unselected branches are not executed.
`write_plan(planned, output_root)` can publish a plan without execution. Running
requires a separate new output directory.

Runs retain `execution-plan.json`, projection, summary, JSONL trace, portable input
and node-type metadata, and `execution-view.json`. A node failure returns
`summary.ok=False`; independent branches finish and blocked dependents are skipped.
Caller cancellation waits for every active handler's cleanup, then propagates after
an inspectable view is written. Injected services can be closed once `run` returns.

`inspect(run_dir)` rebuilds `PipelineRunView` from persisted metadata without
importing the user definition. The view has `kind="pipeline-execution-view-v1"`,
`schema_version=3`, `pipeline_id`, and `title`. Unknown node types display using
their declared title and GNode archetype. MIME types can be recovered from provenance.

For an application-owned preview contract, either pass
`define(..., annotate=ArtifactAnnotator)` or publish
`previews={port_id: {"kind": "my-preview-v1", ...}}` on an artifact port. Annotation
values are persisted as data for later inspection; preview objects do not become
engine contracts. Viewers can fall back to ordinary media for unknown preview kinds.
