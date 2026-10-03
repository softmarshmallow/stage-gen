"""Descriptor-confined filesystem reads for authored character profiles.

The rules themselves moved to `components/_secure_fs` when the game contract began reading
authored TOML from an operator-named root under exactly the same conditions. This module keeps
the profile-specific name so the error type callers already catch is unchanged.
"""

from __future__ import annotations

from stage_gen.components._secure_fs import (
    SecurePathError,
    open_absolute_directory,
    read_absolute_regular_file,
    read_relative_regular_file,
)

#: Retained alias. The rules are shared with every other authored contract, so this is the same
#: class rather than a subclass: an `except SecureCharacterProfilePathError` written against the
#: profile loader still catches a failure raised through the shared reader.
SecureCharacterProfilePathError = SecurePathError

__all__ = [
    "SecureCharacterProfilePathError",
    "open_absolute_directory",
    "read_absolute_regular_file",
    "read_relative_regular_file",
]
