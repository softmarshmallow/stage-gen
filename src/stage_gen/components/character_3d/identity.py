"""Product identities persisted into provenance, node records and journals."""

from __future__ import annotations

from gnode import SoftwareIdentity

NODE_TYPE_NAMESPACE = "3d/character/"
IDENTITY = SoftwareIdentity(name="stage-gen-character-3d", version="0.2.0")
COLLECT_RECOVERY_IDENTITY = SoftwareIdentity(
    name="stage-gen-character-3d-collect-recovery", version="2"
)
