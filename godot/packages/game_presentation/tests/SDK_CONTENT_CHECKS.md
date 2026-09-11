# SDK and Command Link content boundary checks

The SDK installs as the complete `addons/game_presentation/` directory. Run
`python3 tools/check_sdk_package.py` from the development project, or pass
`--sdk-root` for an assembled copy. The check verifies literal resource paths,
relative loads and shader includes remain inside the payload, verifies their
targets exist, and checks script/shader UID sidecars for missing, duplicate and
orphaned identities. Dynamic references and export behavior are covered by the
independent starter import/run/export checks rather than inferred by this scan.

Command Link's root selects the content backend. Without an override it uses
Godot project resources. `--content-root /absolute/prepared/content` selects a
raw local directory whose contents mirror the example's existing bindings:

```text
assets/
  character_full_open.png
  character_full_closed.png
  character_touch.png
  character_second_standing.png
  character_third_standing.png
  layout.json
  locations/catalog.json
  locations/...
  manpu/catalog.json
  manpu/...
  opening/title.ogv
  opening/title_b.ogv
```

Catalog image paths are relative to the selected content root, not relative to
the catalog file. The concrete host also interprets the original `res://`
catalog entries relative to that root, preserving existing metadata. The SDK
loader itself accepts only explicit relative bindings. File roots must be
normalized absolute directories without symbolic links; use `/private/tmp`
rather than its `/tmp` alias on macOS.

The selected backend loads the contact layout, actor textures, Manpu textures,
backgrounds and opening video. Decodable PNG, JPEG and WebP textures retain the
example's geometry checks: Manpu have square canvases and backgrounds are
opaque. The example owns actor/contact/attachment geometry and story choices.
Its SDK behavior catalogs and shaders remain inside the addon.

`qa/command_link_content_checks.gd` builds temporary, code-authored test images
and catalogs outside the project and checks:

- the five actor images and contact coordinates come from that directory;
- relative and historical `res://` catalog entries both load external WebP;
- parent traversal is refused instead of falling back to repository content;
- the opening selects its independent external backend and retains looping;
- keyboard input and completion do not advance; missing video still waits for
  an explicit pointer action.

When the local placeholder OGV exists, the check copies it into its temporary
fixture and verifies the player is bound to that external file. This check
does not assess decoded video quality or an entire playback cycle. Existing
native opening checks provide those separate observations. Temporary content
is removed after the test. No active art is modified.

```sh
Godot --headless --path . --script res://tests/command_link_content_checks.gd
Godot --headless --path . -- --game command_link --route game --validate-routes
```
