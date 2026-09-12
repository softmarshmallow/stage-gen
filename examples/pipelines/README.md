# Local media pipeline

`local_media.py` defines a custom graph with independent PNG and WAV generation
nodes and a JSON catalog joining their outputs. All media are deterministic,
synthetic examples. No credential, provider, game config, or runtime is required.

Create an input directory containing `palette.json`:

```json
{"color": [48, 132, 184]}
```

Load and execute the definition from any working directory:

```python
import asyncio
from pathlib import Path
from stage_gen.pipeline import load_definition, plan, run, inspect


async def main():
    pipeline = load_definition("/absolute/path/to/local_media.py:pipeline")
    planned = plan(pipeline, input_root=Path("./inputs"))
    first = await run(planned, output_root=Path("./run-1"), cache_root=Path("./cache"))
    second = await run(planned, output_root=Path("./run-2"), cache_root=Path("./cache"))
    assert first.summary.ok and second.summary.ok
    print(inspect(second.run_dir).model_dump_json(indent=2))


asyncio.run(main())
```

The second run restores all three nodes from validated cache. Set
`targets=["swatch"]` when planning to execute only the image branch. Change the
palette and plan again: the image and catalog regenerate while the WAV remains a
cache hit. An invalid color produces an inspectable failed image node, a successful
independent audio node, and a skipped catalog.

The file may be copied into an external application and renamed. It imports only
installed public `gnode`, `stage_gen.pipeline`, and Pillow APIs. Its `pipeline`
export is also loadable by the `stage-gen pipeline` CLI.

## Deterministic portrait processing

`portrait_processing.py` builds a four-stage graph around the public portrait
components: source import, uniform face crop, synthetic donor plus mask, and
source-preserving restoration with a two-frame WebP preview. Call
`write_example_inputs(Path("./portrait-inputs"))` from that module to create
original synthetic input pixels and an authored face box, then load its `pipeline`
export with the same API or CLI. `checks.json` reports exact exterior and alpha
preservation. This example performs no semantic or temporal review.
