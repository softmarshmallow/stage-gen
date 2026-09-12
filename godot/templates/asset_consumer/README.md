# Asset consumer template

This small Godot project displays one supplied PNG. Its own preparation script binds the source
to `content/preview.png`, and its scene owns how that image is displayed. It imports no legacy
builder, runtime family, or canonical game contract. Copy this directory into a project you own
and replace the scene behavior as needed.

From the repository root, using the Python environment that contains Stage Gen and Pillow:

```sh
python godot/templates/asset_consumer/prepare.py --asset out/my-run/parallax/preview.png
godot --path godot/templates/asset_consumer
```

The image can come from any pipeline or from an authorized existing input. The script validates
the PNG and, when an adjacent `.meta.json` provenance sidecar exists, checks its digest, size,
and media type before copying both unchanged across this consumer boundary. It replaces the
script-owned `content/` directory as one rollback-safe operation. That directory is ignored;
preparing a local image does not publish or approve it.

The output path and scene binding are local choices of this template. They are not a Stage Gen
input schema or a promise that the asset pipeline will construct a game. The template does not
perform semantic review or generation.

A provider-free smoke check after preparing an image is:

```sh
godot --headless --path godot/templates/asset_consumer --script res://tests/consume.gd
```

The repository contract test copies the template to a temporary project, prepares an image,
verifies provenance preservation and refused mismatches, and runs that native check when Godot
is installed. It never puts test media in the tracked template.
