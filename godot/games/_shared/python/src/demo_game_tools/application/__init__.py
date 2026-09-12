"""Application decisions owned by the optional game input tools."""

from collections.abc import Sequence

from stage_gen.application import UsageError


def resolve_genre(declared: Sequence[str], requested: str | None) -> str:
    """Pick the genre member one run addresses.

    One run serves one genre member. With a single declared member the flag is noise,
    so it defaults; with several, defaulting would silently choose a genre, which is
    exactly the kind of decision a spend-adjacent command must not make on its own.
    """

    if requested is not None:
        if requested not in declared:
            raise UsageError(
                f"--genre {requested!r} is not declared by the package; declared: "
                + ", ".join(declared)
            )
        return requested
    if len(declared) == 1:
        return declared[0]
    raise UsageError("--genre is required for a package declaring several: " + ", ".join(declared))


__all__ = ["resolve_genre"]
