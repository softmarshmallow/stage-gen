// A gauge: a bounded resource that drains, refills, and refuses input for a
// while after it was drained.
//
// Deliberately domain-free. There is no `hp`, no `damage` and no `hurt` in
// this file, because the shape is not health's: hit points, mana, stamina, a
// shield, fuel, oxygen and a boss's phase meter are one model wearing six
// names, and the moment the model is called HP the second one has to be
// written again from scratch. The runner needs one gauge; an RPG needs two
// side by side; naming the primitive after either would be naming it after
// today's game.
//
// The refractory window is part of the primitive rather than a caller's job
// for the same reason it exists in combat: contact is continuous. A hazard the
// avatar is standing inside, or a mob standing inside the player, would
// otherwise empty the whole gauge in one cooldown cycle, because nothing
// separates one drain from the next. A drain that arrives during the window is
// not an error and not a hit — it is absorbed, and being absorbed is what
// makes the contact survivable.
//
// Everything here is pure, total, and frozen. Nothing reads a clock: `nowMs`
// is always passed in, and the blink phase is arithmetic on it rather than a
// tween, so a deterministic fixed-step replay produces identical frames.

export type Gauge = Readonly<{
  value: number;
  max: number;
  /** Drains before this timestamp are absorbed. */
  refractoryUntilMs: number;
  depleted: boolean;
}>;

/**
 * The authoritative outcome of one attempt to change a gauge.
 *
 * `attempted` is what the caller asked for; `applied` is the delta after the
 * bound, so a consumer never has to reconstruct overspill from mutable state.
 * A refused attempt is still a complete answer: same value before and after,
 * zero applied, `connected = false`, and the gauge handed back unchanged so
 * the caller can assign unconditionally.
 */
export type GaugeChange = Readonly<{
  connected: boolean;
  attempted: number;
  applied: number;
  before: number;
  after: number;
  depleted: boolean;
  gauge: Gauge;
}>;

export function createGauge(max: number): Gauge {
  if (!Number.isSafeInteger(max) || max <= 0) {
    throw new RangeError("a gauge maximum must be a positive integer");
  }
  return Object.freeze({ value: max, max, refractoryUntilMs: 0, depleted: false });
}

export function isRefractory(gauge: Gauge, nowMs: number): boolean {
  return nowMs < gauge.refractoryUntilMs;
}

function refused(gauge: Gauge, attempted: number): GaugeChange {
  const value = Number.isFinite(gauge.value) ? Math.max(0, gauge.value) : 0;
  return Object.freeze({
    connected: false,
    attempted: Number.isFinite(attempted) ? attempted : 0,
    applied: 0,
    before: value,
    after: value,
    depleted: gauge.depleted || value <= 0,
    gauge,
  });
}

/**
 * Drain the gauge, honouring the refractory window.
 *
 * Refuses rather than clamping in every case where the arithmetic would be
 * meaningless: an already-depleted gauge, an invalid or non-positive amount,
 * an empty pool, and a drain inside the window. `refractoryMs` of zero opens
 * no window, which is what a caller wants for a pool that has no immunity —
 * the drain still lands, it simply grants nothing afterwards.
 */
export function drain(
  gauge: Gauge,
  amount: number,
  nowMs: number,
  refractoryMs: number,
): GaugeChange {
  if (
    gauge.depleted ||
    !Number.isFinite(gauge.value) ||
    gauge.value <= 0 ||
    !Number.isFinite(amount) ||
    amount <= 0 ||
    isRefractory(gauge, nowMs)
  ) {
    return refused(gauge, amount);
  }
  const after = Math.max(0, gauge.value - amount);
  const window = Number.isFinite(refractoryMs) && refractoryMs > 0 ? nowMs + refractoryMs : 0;
  return Object.freeze({
    connected: true,
    attempted: amount,
    applied: gauge.value - after,
    before: gauge.value,
    after,
    depleted: after <= 0,
    gauge: Object.freeze({
      value: after,
      max: gauge.max,
      // A window that already passed is not worth remembering.
      refractoryUntilMs: Math.max(window, gauge.refractoryUntilMs),
      depleted: after <= 0,
    }),
  });
}

/**
 * Refill toward the ceiling.
 *
 * Refuses a depleted gauge (bringing one back is a separate decision, not a
 * top-up), an invalid amount, and a gauge already full — that last refusal is
 * the one that matters, because it is what stops a held key or an automated
 * policy from spending a bagful into a pool that was never drained.
 *
 * The refractory window is deliberately untouched: refilling is not being hit,
 * and granting immunity here would make it the strongest defensive move.
 */
export function restore(gauge: Gauge, amount: number): GaugeChange {
  if (
    gauge.depleted ||
    !Number.isFinite(amount) ||
    amount <= 0 ||
    gauge.value >= gauge.max
  ) {
    return refused(gauge, amount);
  }
  const after = Math.min(gauge.max, gauge.value + amount);
  if (after <= gauge.value) return refused(gauge, amount);
  return Object.freeze({
    connected: true,
    attempted: amount,
    applied: after - gauge.value,
    before: gauge.value,
    after,
    depleted: false,
    gauge: Object.freeze({
      value: after,
      max: gauge.max,
      refractoryUntilMs: gauge.refractoryUntilMs,
      depleted: false,
    }),
  });
}

/**
 * Raise the ceiling and fill to it.
 *
 * The fill is the point rather than a side effect: a ceiling that only widened
 * would arrive as an empty promise in the middle of whatever earned it. A
 * ceiling that does not grow is returned untouched, and this never lowers one —
 * shrinking a pool is not what growth does, and doing it quietly here would
 * hide the caller's mistake.
 */
export function grow(gauge: Gauge, max: number): Gauge {
  if (!Number.isSafeInteger(max) || max <= 0) {
    throw new RangeError("a grown gauge requires a positive integer maximum");
  }
  if (max <= gauge.max) return gauge;
  return Object.freeze({
    value: max,
    max,
    refractoryUntilMs: gauge.refractoryUntilMs,
    depleted: gauge.depleted,
  });
}

/**
 * Deterministic opacity for the refractory window.
 *
 * The phase counts down from the remaining window rather than up from the
 * drain, so the frame that connected is already dim even when the caller
 * resolves the drain after the sprite's own update for that frame. A depleted
 * gauge never blinks: whatever terminal presentation it triggered stays fully
 * visible.
 */
export function refractoryBlinkAlpha(
  gauge: Gauge,
  nowMs: number,
  intervalMs: number,
  dimAlpha: number,
): number {
  if (gauge.depleted || !isRefractory(gauge, nowMs)) return 1;
  if (!Number.isFinite(intervalMs) || intervalMs <= 0) return dimAlpha;
  const phase = Math.floor((gauge.refractoryUntilMs - nowMs) / intervalMs);
  return phase % 2 === 0 ? dimAlpha : 1;
}

/** How full the gauge is, in [0, 1]. The one number a bar needs. */
export function gaugeFraction(gauge: Gauge): number {
  if (!Number.isFinite(gauge.value) || !Number.isFinite(gauge.max) || gauge.max <= 0) return 0;
  return Math.min(1, Math.max(0, gauge.value / gauge.max));
}
