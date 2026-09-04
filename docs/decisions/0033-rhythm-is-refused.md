# 0033 — Rhythm is refused: the seam rule and beat sync are mutually exclusive

*Ruled with the adoption survey, and written into the genre specification so it is not
re-litigated.*

## Fact

Both references that actually sync music to play map a *through-composed* song onto a *fixed*
level. The runner's defining property is that any chunk may follow any chunk, drawn uniformly
at runtime.

## Challenge

"Feels musical" is a real want, and beat sync is the obvious way to get it. Refusing on cost
would leave the door open for a bigger budget.

## Ruling

Refused, and not on cost — it would still be no with unlimited budget. You cannot
through-compose against a random permutation: **the exact property that makes the runner
infinite is the property that forbids the rhythm model.** It is independently disqualified by
the speed ramp, which is continuous in distance, so the column-crossing period slides from
167ms to 111ms across one run and a column has no fixed beat phase at any point; the only
compatible model is a loop grid with constant tempo and integer columns per bar, which
forfeits the difficulty ramp entirely — a different genre, not a feature.

## Evidence

The producer does not exist either: the music request carries no tempo in or out, the audio
probe returns only duration, format and bit rate, and the dependency set has no onset or
tempo-estimation stack. A beat grid needs a new artifact kind, a new node type with a retry
owner and a new analysis dependency before one unit of design value lands, against a provider
whose tempo adherence nothing here tests, where a missed tempo is a semantic regeneration
rather than a retry: unbounded cost against unmeasured capability. A tempo field must not enter
the shared soundtrack contract — it is the one member already shared across genres, and neither
a jumper nor a cinematic platformer has a tempo. The cheap 80% is the per-event audio one-shot.

## Falsifier

A level model in this family that is fixed rather than permuted at runtime, or a ramp-free
member — either would remove one of the two independent disqualifications.
