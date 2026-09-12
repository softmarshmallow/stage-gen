# Shared game format references

These documents describe input and runtime formats used by the named games in
this repository. They are maintained with those readers and do not define the
public asset SDK or a required way to make a game.

- [Prepared input format](game-package.md): directory/ZIP capture, explicit selection and validation.
- [Game contract design](game-contract.md): the domain model behind those existing formats, with future-facing design sections kept in context.
- [Authored root schema](formats/authored-contract-schema.md): the supported `game.toml` membership format.
- [Soundtracks](soundtrack.md): shared authored track and playback binding format.
- [UI](formats/ui.md): the supported game interface binding format.
- [Runtime boundary](formats/host-contract.md): deterministic run consumption for the four prepared-run games.
- [Dialogue sequence design](formats/dialogue-and-cutscene-sequences.md), [UI taxonomy design](formats/ui-atlas.md) and [view/style vocabulary](formats/view-and-style-taxonomy.md): scoped design records whose maturity is stated individually.

Bellweather owns its [map and build graph](../../bellweather/docs/generation-pipeline.md).
Iron Petal Unit owns its [runner](../../iron_petal_unit/docs/runner.md).
Ember Hollow owns its [survival preparation](../../ember_hollow/docs/generation-v1.md).
The Grain owns its [case](../../the_grain/docs/case.md) and narrative leaves.
