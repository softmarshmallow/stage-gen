"""The application layer's one shared error.

A usage error is its own class so a command can exit 2 for it, the way argparse does for a
malformed command line, rather than flatten it with an internal failure.
"""


class UsageError(ValueError):
    """A command was asked for something its flags cannot mean."""


__all__ = ["UsageError"]
