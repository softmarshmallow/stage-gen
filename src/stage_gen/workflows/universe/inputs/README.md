# Universe source examples

`lantern_ferry/` is a source-checkout fixture with original procedural reference
art, synopsis, and expansion direction. Its input directory is excluded from
Python distributions as one unit, so installed packages never carry a partial
runnable example with missing image references.

To author another universe, supply your own local directory containing
`universe.toml`, its referenced image, and the two named text documents. Follow
the universe source contract in `src/stage_gen/workflows/universe/contract.md`. The
repository fixture's image can be regenerated with
`scripts/author_universe_fixture_poster.py`; that script writes the checkout
fixture, not an installed-package resource.
