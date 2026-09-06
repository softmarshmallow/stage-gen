extends RefCounted

## Mulberry32 against the JavaScript it is ported from. The reference values
## were produced with node from the viewer's own function body:
##
##   node -e "function mulberry32(seed){let state=seed>>>0;return function(){
##     state=(state+0x6d2b79f5)>>>0;let t=state;t=Math.imul(t^(t>>>15),t|1);
##     t^=t+Math.imul(t^(t>>>7),t|61);return ((t^(t>>>14))>>>0)/4294967296;};}"

const SEED_1 := [
	0.6270739405881613,
	0.002735721180215478,
	0.5274470399599522,
	0.9810509674716741,
	0.9683778982143849,
]
## full-v66's layout seed.
const SEED_7 := [
	0.011704753153026104,
	0.06195825757458806,
	0.97690763277933,
	0.6990287057124078,
	0.5214452685322613,
]
const SEED_0 := [
	0.26642920868471265,
	0.0003297457005828619,
	0.2232720274478197,
]

func run(h: TestHarness) -> void:
	_check_stream(h, 1, SEED_1)
	_check_stream(h, 7, SEED_7)
	_check_stream(h, 0, SEED_0)

	# The same seed is the same stream, every time.
	var a := Mulberry32.new(7)
	var b := Mulberry32.new(7)
	for i in 64:
		if not h.assert_eq(a.next(), b.next(), "seed 7 draw %d diverged" % i):
			break

	# Every draw is in [0, 1).
	var generator := Mulberry32.new(12345)
	var low := 1.0
	var high := 0.0
	for _i in 4096:
		var value := generator.next()
		low = minf(low, value)
		high = maxf(high, value)
	h.assert_true(low >= 0.0, "a draw fell below 0 (%f)" % low)
	h.assert_true(high < 1.0, "a draw reached 1 (%f)" % high)

	# The draw counter and the peek, which only the parity harness reads: the
	# count is one per draw, and a peek returns the next value without moving
	# the state or the count.
	var counted := Mulberry32.new(7)
	h.assert_eq(counted.draws, 0, "a fresh generator has drawn nothing")
	for i in 3:
		counted.next()
	h.assert_eq(counted.draws, 3, "three draws counted three")
	var peeked := counted.peek()
	h.assert_eq(counted.draws, 3, "a peek counted as a draw")
	h.assert_near(counted.peek(), peeked, 1e-15, "two peeks in a row disagreed")
	h.assert_near(counted.next(), peeked, 1e-15, "the peek was not the next draw")
	h.assert_eq(counted.draws, 4, "the draw after a peek did not count")
	h.assert_near(counted.next(), SEED_7[4], 1e-15, "peeking moved the stream")

	# The world hands the same stream out as a Callable.
	var pkg := h.package()
	if pkg == null:
		h.fail("run package did not open")
		return
	var world := World.create(pkg, 7, {"masks": Masks.new()})
	for i in SEED_7.size():
		h.assert_near(world.rand.call(), SEED_7[i], 1e-12, "world.rand draw %d" % i)

func _check_stream(h: TestHarness, seed_value: int, expected: Array) -> void:
	var generator := Mulberry32.new(seed_value)
	for i in expected.size():
		h.assert_near(generator.next(), float(expected[i]), 1e-15, "mulberry32(%d) draw %d" % [seed_value, i])
