"""The runner genre's avatar catalog (`runner-avatar-v3`)."""

from .models import (
    RUNNER_AVATAR_BASE_MOTION_STATES,
    RUNNER_AVATAR_MOTION_STATES,
    RUNNER_AVATAR_SCHEMA_VERSION,
    RUNNER_MOTION_ORDER,
    RunnerAvatar,
    RunnerAvatarCatalog,
    declared_motion_states,
    load_runner_avatar_bytes,
    runner_avatar_sha256,
)

__all__ = [
    "RUNNER_AVATAR_BASE_MOTION_STATES",
    "RUNNER_AVATAR_MOTION_STATES",
    "RUNNER_AVATAR_SCHEMA_VERSION",
    "RUNNER_MOTION_ORDER",
    "RunnerAvatar",
    "RunnerAvatarCatalog",
    "declared_motion_states",
    "load_runner_avatar_bytes",
    "runner_avatar_sha256",
]
