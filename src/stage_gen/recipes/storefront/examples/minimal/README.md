# Minimal storefront assets

This example supplies one original geometric reference, a positioning note, and
one requested app icon. It needs no game contract, gameplay file, scene, or demo
package. The script draws its input locally using Pillow; it calls no provider.

From the repository root:

```sh
python src/stage_gen/recipes/storefront/examples/minimal/make_inputs.py /tmp/quiet-orbit-input
stage-gen storefront generate --input /tmp/quiet-orbit-input \
  --output /tmp/quiet-orbit-plan --cache-dir /tmp/quiet-orbit-cache --dry-run
```

The dry run validates the input and writes the asset graph. Executing the graph
requires configured services and explicit live authorization. The reference is
procedural fixture art; generated outputs remain unreviewed until inspected.
