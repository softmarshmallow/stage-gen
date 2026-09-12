# Command Link presentation

This directory belongs to Command Link. It composes the selected Godot packages
with this game's art, framing, story and laboratory controls.

- [stage.gd](stage.gd) owns frame timing, actor/camera composition, input behavior
  and the existing subclass surface used by the mission and lab routes.
- [stage_assets.gd](stage_assets.gd) binds the local profile's images, mark and
  location catalogs, and contact coordinates. Each stage has independent asset
  dictionaries and diagnostics. The adapter keeps Command Link's required IDs,
  square-mark and opaque-background checks; local byte loading delegates through
  the selected content loader.
- [stage_controls.gd](stage_controls.gd) constructs and positions the existing
  controls. Callbacks still invoke the owning stage's methods, including subclass
  overrides. Control construction and layout do not advance presentation clocks.
- [stage_profile.gd](stage_profile.gd) is the in-process binding supplied by the
  game or lab root, rather than a persisted gameplay format.

The stage keeps its existing methods and field accessors so mission and study
implementations retain their behavior. Catalog binding and control construction
are local composition helpers; neither is a common visual-novel framework.

[Stage seam checks](../tests/stage_seams_checks.gd) use synthetic images to prove
catalog refusal, contact binding, instance isolation, child order, fixed layout
and subclass callbacks. Existing composition, route, camera, actor and rendered
checks cover the complete presenter with prepared content.

Command Link owns its [one-shot renderer checks](../tests/one_shot_manpu_integration_checks.gd)
[walk-away/bounce checks](../tests/walk_away_integration_checks.gd), and
[native looping-mark checks](../tests/looping_manpu_integration_checks.gd). They use its
actual lab routes and prepared actors. Their optional `--capture-one-shot` and
`--capture-walk-away` flags require a native renderer and write local evidence.
