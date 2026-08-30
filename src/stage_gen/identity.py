"""stage-gen's provenance identity strings, supplied to engine services.

The engine ships no brand: every service takes its component and tool
identities from the application. These are the exact strings this
application has always written, so provenance bytes do not move.
"""

from gnode import SoftwareIdentity

STAGE_GEN_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")
IMAGE_GENERATION_COMPONENT = SoftwareIdentity(name="@stage-gen/image-generation", version="0.0.0")
STRUCTURED_GENERATION_COMPONENT = SoftwareIdentity(
    name="@stage-gen/structured-generation", version="0.0.0"
)
MUSIC_GENERATION_COMPONENT = SoftwareIdentity(name="@stage-gen/music-generation", version="0.0.0")
BACKGROUND_REMOVAL_COMPONENT = SoftwareIdentity(
    name="@stage-gen/background-removal", version="0.0.0"
)
