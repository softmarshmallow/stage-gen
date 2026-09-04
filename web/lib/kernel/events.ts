// The frame event queue: what one system tells the others happened.
//
// `reads` and `writes` carry *state* — the value of a world key at the moment
// a reader looks at it. They cannot carry an *occurrence*. A system that needs
// to know "a hazard was struck this frame", not "a hazard is overlapping now",
// has had exactly two options here until now: widen a state key into a
// per-frame flag that every consumer must remember to clear, or keep a private
// shadow copy of last frame's state and rediscover the edge by comparing.
//
// Both are already in the tree. The runner's audio system keeps five `prev*`
// locals to rebuild edges the producing systems knew for certain and threw
// away, and it has to special-case a restart because a shadow copy cannot tell
// a rewind from an event. That is the cost of having no channel for
// occurrences, paid once per consumer.
//
// So: one queue per frame, cleared at the top of the tick, appended to in
// sealed order, and readable by anything ordered after the emitter. An event
// is a plain frozen record with a `type` discriminant. The queue holds no
// subscriptions and dispatches nothing — a consumer asks for the events it
// cares about when its own update runs, which keeps the whole thing inside the
// deterministic tick rather than beside it.

/** The one thing every event must carry, so consumers can discriminate. */
export interface GameEvent {
  readonly type: string;
}

/**
 * The clearing half of the queue, which only the sealed tick may call.
 *
 * Split out from `EventQueue` so a system holding a queue cannot silently
 * discard the frame another system is still reading.
 */
export interface EventQueueControl {
  beginFrame(): void;
}

export interface EventQueue<E extends GameEvent> extends EventQueueControl {
  /** Append one occurrence to this frame. */
  emit(event: E): void;
  /** Every event of `type` emitted so far this frame, in emission order. */
  ofType<T extends E["type"]>(type: T): readonly Extract<E, { readonly type: T }>[];
  /** Every event emitted so far this frame, in emission order. */
  readonly frame: readonly E[];
}

/**
 * A queue for one world.
 *
 * Mutable by construction, like the world it belongs to: the sealed tick is a
 * sequence of in-place updates, and an immutable queue would mean rebuilding
 * and rebinding it inside every emitter. What is frozen is each event, so a
 * consumer cannot rewrite the record a later consumer will read.
 */
export function createEventQueue<E extends GameEvent>(): EventQueue<E> {
  let frame: E[] = [];
  return {
    emit(event: E): void {
      frame.push(Object.freeze(event));
    },
    ofType<T extends E["type"]>(type: T): readonly Extract<E, { readonly type: T }>[] {
      return frame.filter(
        (event): event is Extract<E, { readonly type: T }> => event.type === type,
      );
    },
    get frame(): readonly E[] {
      return frame;
    },
    beginFrame(): void {
      // A fresh array rather than `length = 0`: a consumer that kept the
      // previous frame's slice keeps looking at the events it was given.
      frame = [];
    },
  };
}
