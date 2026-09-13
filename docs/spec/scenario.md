# Scenario

> **Checked by:** none.

Scenario is owned by the [Godot example project](../../godot/CHARTER.md), as an
embeddable VN-oriented presentation framework. Its compiler is independently
installable from `godot/packages/scenario_runtime/authoring`; it is no longer a
Stage Gen asset component. The game owns and invokes a scenario, supplies its
bindings/capabilities and keeps control of the world.

- [Current package](../../godot/packages/scenario_runtime/README.md)
- [Authoritative invocation contract](../../godot/packages/scenario_runtime/docs/contract.md)
- [Directory preview](../../godot/packages/scenario_runtime/docs/layout.md)
- [Compiler and source syntax](../../godot/packages/scenario_runtime/authoring/README.md)
- [Embedding, portraits and 2D/3D actors](../../godot/packages/scenario_runtime/docs/embedding.md)
- [Supported v2 inputs and compatibility](../../godot/packages/scenario_runtime/docs/compatibility.md)
- [Verification](../../godot/packages/scenario_runtime/docs/verification.md)
- [Ownership decision and supersession](../decisions/0070-the-game-invokes-scenario.md)

The [earlier v2 design](../../godot/packages/scenario_runtime/docs/history/v2-design.md)
is historical evidence. The proposed universal game-sequence document does not
control the current contract. Existing game inputs retain their supported readers;
new narrative authoring uses v3 without requiring a universal gameplay schema.
