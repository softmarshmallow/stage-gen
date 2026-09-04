# 0003 — Script-declared music reuses the soundtrack component's generation intent

*Ruled with M1 increment 4.*

## Fact

A scenario already declared its tracks and admission already proved that every `play` and
`stop` named one. What was missing was generation and playback, not vocabulary.

## Challenge

The scenario owns the declaration, so the scenario could carry its own music request shape
and compile its own prompt — one contract, self-contained.

## Ruling

One track per declared track, carrying the soundtrack component's own `TrackGenerationIntent`
rather than a second shape, compiled by the one prompt compiler both recipes share. A second
request shape for the same artifact kind is a parallel contract, which this repository
retires rather than adds.

## Evidence

Both recipes reach music through the same compiler; the scenario contributes a declaration and
no new request type.

## Falsifier

A narrative-specific music parameter that cannot be expressed as a generation intent without
distorting the soundtrack contract for the genre that does not need it.
