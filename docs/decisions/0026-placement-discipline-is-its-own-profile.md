# 0026 — Placement discipline is its own profile, not fields on the jump profile

*Ruled with admission hardening I.*

## Fact

Two proven holes shipped unwinnable moments. A chunk ending a three-column pit at its last
authorable columns passes every per-chunk check, and any chunk with a hazard at column 0 may
follow it: the avatar lands on the seam and meets the hazard 0.167s later, against 0.767s of
airtime and a ~200ms human reaction. And a pit followed by a bank higher than the rise limit
resolved clean, because the interior-rise guard only compares adjacent columns and the
supported list omits pit columns.

## Challenge

The jump profile already carries the arithmetic admission reads. Hanging headroom, spacing and
clearance on it is one frozen record instead of two.

## Ruling

A frozen placement profile sits *beside* the jump profile, selected by a module constant.
Conflating traversal capability with placement discipline forces every future jump name to
re-declare the whole discipline, and it is the half that will not transpose to a jumper. The
name is not persisted as an authored field: a one-member vocabulary nobody can choose between
is a constant, and the field lands in one bump the moment a second discipline exists.

## Evidence

Per-chunk admission structurally cannot see the seam case, because the validator never touches
a neighbour — which is the seam rule's whole purpose, so the apron is the price of keeping it
rather than an argument against it. The spacing is *derived* rather than asserted: a single
jump spans 4.6 columns at base speed, so the minimum hazard separation is at least six with a
reaction margin, not the four first proposed, and clearance is stated over hazard *sets*
within one arc span. The apron alone closes only the cross-chunk case, so landing clearance is
measured forward from every pit's and every interior rise's landing column, or the same
counterexample survives one column inside a chunk boundary. The refusals are proven in
`tests/unit/orchestration/test_runner_member.py`.

## Falsifier

A second placement discipline that cannot be expressed without re-declaring the jump
arithmetic, which would mean the two records were one after all.
