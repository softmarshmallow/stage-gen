// The `interaction` family, second half: the conversation in flight.
//
// The scenario *reducer* was already shared — `lib/scenario/runtime.ts` is
// walked by the platformer and by the visual novel alike. What was not shared
// is the session around it: which authored interaction this playback belongs
// to, what an advance does when the program has ended, and who is told the
// outcome. The platformer kept that as a mutable `activeScenario` field whose
// `applyScenarioAction` inlined all three questions; the dialogue scene keeps
// its own version of the same three.
//
// The session below is a value, and it is generic over the program and the
// state because the family has no business knowing what a scenario is. What it
// knows is the lifecycle: opened, stepped, and either still running or finished
// with an outcome the consumer is handed exactly once.

export interface InteractionSession<Program, State> {
  /** The authored interaction this playback belongs to; the outcome is reported against it. */
  readonly interactionId: string;
  readonly program: Program;
  readonly state: State;
}

export interface SessionStepArgs<Program, State, Action> {
  readonly session: InteractionSession<Program, State>;
  readonly action: Action;
  /** The genre's reducer. Returning the same state means the action did nothing. */
  readonly reduce: (program: Program, state: State, action: Action) => State;
  /** Whether the program has run to its end. */
  readonly finished: (state: State) => boolean;
  /** The ending the program reached, or null when it reached none. */
  readonly outcome: (state: State) => string | null;
}

export type SessionStep<Program, State> =
  /** Nothing happened; the caller redraws nothing. */
  | Readonly<{ kind: "unchanged"; session: InteractionSession<Program, State> }>
  /** The playback moved and is still running. */
  | Readonly<{ kind: "running"; session: InteractionSession<Program, State> }>
  /** The playback ended. The outcome is reported once, against the interaction it belongs to. */
  | Readonly<{
      kind: "finished";
      session: InteractionSession<Program, State>;
      interactionId: string;
      outcome: string | null;
    }>;

export function openSession<Program, State>(
  interactionId: string,
  program: Program,
  state: State,
): InteractionSession<Program, State> {
  return Object.freeze({ interactionId, program, state });
}

/**
 * Step one interaction, and say which of the three things happened.
 *
 * Three, not two: "the action did nothing" is separate from "it advanced",
 * because a redraw on a no-op is what makes a panel flicker on every key a
 * player presses that the conversation does not answer.
 */
export function stepSession<Program, State, Action>(
  args: SessionStepArgs<Program, State, Action>,
): SessionStep<Program, State> {
  const next = args.reduce(args.session.program, args.session.state, args.action);
  if (next === args.session.state) {
    return { kind: "unchanged", session: args.session };
  }
  const session = openSession(args.session.interactionId, args.session.program, next);
  if (args.finished(next)) {
    return {
      kind: "finished",
      session,
      interactionId: session.interactionId,
      outcome: args.outcome(next),
    };
  }
  return { kind: "running", session };
}
