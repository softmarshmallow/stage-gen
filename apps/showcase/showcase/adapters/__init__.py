"""Run-family adapters. Each turns run folders into a showcase record (see record.py).

Signature: build_record(repo_root, media, run_options_from_front_matter) -> record.
"""

from . import (
    execution_view,
    gnode_records,
    parallax_layers,
    portrait_face,
    sprite_set,
    terrain_atlas,
    ui_kit,
)

ADAPTERS = {
    "gnode_records": gnode_records.build_record,
    "execution_view": execution_view.build_record,
    "portrait_face": portrait_face.build_record,
    "terrain_atlas": terrain_atlas.build_record,
    "ui_kit": ui_kit.build_record,
    "sprite_set": sprite_set.build_record,
    "parallax_layers": parallax_layers.build_record,
}
