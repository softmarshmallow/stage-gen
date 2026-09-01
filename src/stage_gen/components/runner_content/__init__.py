"""The runner genre's avatar catalog (`runner-avatar-v1`)."""

from .models import (
    RUNNER_AVATAR_MOTION_STATES,
    RUNNER_AVATAR_SCHEMA_VERSION,
    RunnerAvatar,
    RunnerAvatarCatalog,
    load_runner_avatar_bytes,
    runner_avatar_sha256,
)

__all__ = [
    "RUNNER_AVATAR_MOTION_STATES",
    "RUNNER_AVATAR_SCHEMA_VERSION",
    "RunnerAvatar",
    "RunnerAvatarCatalog",
    "load_runner_avatar_bytes",
    "runner_avatar_sha256",
]
