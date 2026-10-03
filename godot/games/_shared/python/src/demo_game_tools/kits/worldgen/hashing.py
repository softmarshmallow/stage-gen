"""Salted, addressable draws: one number per (seed, salt, index), never a stream.

A world generator that consumes one random stream in order has a tuning
problem: raise the density of one object and every object placed after it
lands somewhere else, because they now read later numbers. Here every draw is
addressed instead. A stream is the seed folded with a salt (which object, which
purpose), and a draw is that base folded with an integer index (which cell,
which candidate, which axis). Two draws agree if and only if their addresses
agree, so an edit to one object's block can only move that object's draws.

The mixing is splitmix64's finalizer, which passes the usual statistical
batteries and is a dozen integer operations in pure Python. The uniform is 53
bits, not 32: a Poisson count taken by inverse CDF from a 32-bit uniform
truncates its tail at 2^-32, silently, and the extra bits are free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

M64: Final = 0xFFFF_FFFF_FFFF_FFFF
#: Joins salt segments. Never legal inside an identifier, so two different
#: segment lists can never fold to one salt string.
SALT_SEP: Final = "\x1f"

_FNV_OFFSET: Final = 0xCBF2_9CE4_8422_2325
_FNV_PRIME: Final = 0x0000_0100_0000_01B3
_UNIT: Final = 2.0**-53


def fnv1a64(text: str) -> int:
    """FNV-1a over the UTF-8 bytes. Only ever used to fold a salt into a base."""

    value = _FNV_OFFSET
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * _FNV_PRIME) & M64
    return value


def splitmix64(z: int) -> int:
    """The splitmix64 output function: one round of avalanche over 64 bits."""

    z = (z + 0x9E37_79B9_7F4A_7C15) & M64
    z = ((z ^ (z >> 30)) * 0xBF58_476D_1CE4_E5B9) & M64
    z = ((z ^ (z >> 27)) * 0x94D0_49BB_1331_11EB) & M64
    return z ^ (z >> 31)


@dataclass(frozen=True, slots=True)
class Stream:
    """One addressable source of draws: the seed and the salt folded once.

    ``Stream.of(seed, "oak", "poisson", "site").unit(i, j, k, 0)`` is the
    same number every time, on every machine, and no other address gives it.
    ``cell(i, j)`` folds the first two indices so a loop over a cell does not
    re-fold them for every draw; ``stream.cell(i, j).unit(k)`` equals
    ``stream.unit(i, j, k)`` exactly.
    """

    base: int

    @classmethod
    def of(cls, seed: int, *salt: str) -> Stream:
        return cls((splitmix64(seed & M64) ^ fnv1a64(SALT_SEP.join(salt))) & M64)

    def fold(self, *index: int) -> int:
        value = self.base
        for entry in index:
            if entry < 0:
                raise ValueError(f"draw index must be non-negative, got {entry}")
            value = splitmix64(value ^ entry)
        return value

    def cell(self, *index: int) -> Stream:
        return Stream(self.fold(*index))

    def unit(self, *index: int) -> float:
        """A uniform in [0, 1) with 53 significant bits."""

        return (splitmix64(self.fold(*index)) >> 11) * _UNIT

    def below(self, n: int, *index: int) -> int:
        """An integer in [0, n). The bias of flooring a 53-bit unit is below 2^-33 for n < 2^20."""

        if n <= 0:
            raise ValueError(f"below() needs a positive bound, got {n}")
        return min(n - 1, int(self.unit(*index) * n))

    def span(self, low: float, high: float, *index: int) -> float:
        return low + (high - low) * self.unit(*index)
