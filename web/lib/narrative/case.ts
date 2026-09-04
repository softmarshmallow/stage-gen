// The `case-runtime-v1` projection, consumer side: the authored case-v1 graph of beats
// above the leaves, plus the run tag (and, for a scenario beat, the scenario id) that
// says which generated run actually holds each leaf. A beat that has grown a run tag is
// a different document from the one the author wrote, so it carries its own identity.
//
// A leaf — a scenario or a point-and-click room — is a complete little game with
// its own proof, and neither knows the other exists. An episode is several of
// them in a row, and something has to say which one is next, what a player
// carried out of the last one, and when the whole thing is over. That is all a
// case is. It adds no narrative vocabulary: it names beats, keys edges on the
// outcome a leaf already reports, and declares the boolean facts that cross
// between them.
//
// The shell owns this rather than either genre, because it is the only part of
// the consumer that outlives one leaf. Parsing is strict in the house style:
// unknown keys are drift, and a document that names a beat it does not carry is
// refused rather than played until it walks off the end.
//
// This module is pure. The reader that finds a case on disk is `case-io.ts`, and
// the persistence that lets a player leave in the middle is `case-save.ts`.

export const CASE_KIND = "case-runtime-v1";
export const CASE_SCHEMA_VERSION = 1;

/** The outcome a room reports; a room has exactly one win, so it needs no name. */
export const ROOM_WIN_OUTCOME = "win";

const SNAKE_ID = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;
const RUN_TAG = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export type CaseBeatKind = "scenario" | "room";

/** Whether a fact must be established before it is read, or may read false. */
export type FactEstablishment = "required" | "defaults_false";

export interface CaseFact {
  readonly factId: string;
  readonly establishment: FactEstablishment;
  readonly summary: string | null;
}

export interface CaseEdge {
  /** A scenario's `end <outcome>`, or `win` for a room. */
  readonly outcome: string;
  readonly to: string;
}

export interface CaseBeat {
  readonly beatId: string;
  readonly kind: CaseBeatKind;
  /**
   * The run that produced this leaf, played in place out of `out/<run_tag>/`.
   *
   * The authored document names the leaf by package member; this runtime one
   * names the run that member was generated into, because the consumer plays
   * runs and has never read a package. It is the one field the projection from
   * the authored contract has to add.
   */
  readonly runTag: string;
  /**
   * Which scenario inside that run this beat plays, for a scenario beat.
   *
   * One `dialogue-scene` run publishes several scenarios — an episode is split
   * so each one's admission proof stays under its ceiling — so the run tag alone
   * does not locate a leaf. A room run publishes one room, so a room beat carries
   * no id at all rather than a null one.
   */
  readonly scenarioId: string | null;
  readonly displayName: string;
  /** The authored package member, carried through for provenance; unused here. */
  readonly member: string | null;
  /** The facts this beat imports, as authored. The leaf declares them too. */
  readonly reads: readonly string[];
  /** The facts this beat can establish, as authored. */
  readonly writes: readonly string[];
  readonly edges: readonly CaseEdge[];
}

export interface CaseDocument {
  readonly caseId: string;
  readonly displayName: string;
  readonly entry: string;
  /** Every boolean fact that may cross a beat boundary, declared once. */
  readonly facts: readonly string[];
  readonly factDeclarations: readonly CaseFact[];
  readonly beats: readonly CaseBeat[];
}

/**
 * Validate one case document.
 *
 * Structural only, and deliberately so. Reachability, fact liveness, and "every
 * fact a beat reads is exported by some earlier beat on every path" are the
 * producer's admission proof, offline, before any art is paid for. A consumer
 * that re-decided them would be a second opinion about a settled question. What
 * is checked here is what this runtime would otherwise trip over: a duplicate
 * beat, an entry that names nothing, an edge into thin air, and a case with no
 * way to finish.
 */
export function parseCase(value: unknown): CaseDocument {
  const root = strictRecord(
    value,
    ["schema_version", "kind", "case_id", "display_name", "entry", "facts", "beats"],
    "case",
    ["game_id", "revision"],
  );
  exact(root.schema_version, CASE_SCHEMA_VERSION, "case schema_version");
  exact(root.kind, CASE_KIND, "case kind");

  const beats = list(root.beats, "case beats", 1).map(beat);
  const ids = new Set(beats.map((entry) => entry.beatId));
  if (ids.size !== beats.length) throw new Error("case beat ids must be unique");

  const factDeclarations = list(root.facts, "case facts", 0).map(fact);
  const document: CaseDocument = Object.freeze({
    caseId: snakeId(root.case_id, "case case_id"),
    displayName: text(root.display_name, "case display_name", 96),
    entry: snakeId(root.entry, "case entry"),
    facts: Object.freeze(factDeclarations.map((entry) => entry.factId)),
    factDeclarations: Object.freeze(factDeclarations),
    beats: Object.freeze(beats),
  });

  if (!ids.has(document.entry)) {
    throw new Error(`case entry ${document.entry} does not name a beat`);
  }
  if (new Set(document.facts).size !== document.facts.length) {
    throw new Error("case facts must be unique");
  }
  for (const entry of beats) {
    for (const edge of entry.edges) {
      if (!ids.has(edge.to)) {
        throw new Error(`case beat ${entry.beatId} has an edge to unknown beat ${edge.to}`);
      }
    }
    if (new Set(entry.edges.map((edge) => edge.outcome)).size !== entry.edges.length) {
      throw new Error(`case beat ${entry.beatId} repeats an outcome`);
    }
    if (entry.kind === "room" && entry.edges.some((edge) => edge.outcome !== ROOM_WIN_OUTCOME)) {
      throw new Error(
        `case beat ${entry.beatId} is a room, whose only outcome is ${ROOM_WIN_OUTCOME}`,
      );
    }
  }
  if (!beats.some((entry) => entry.edges.length === 0)) {
    throw new Error("case must carry a terminal beat");
  }
  return document;
}

/**
 * One leaf, wrapped as a case of a single terminal beat.
 *
 * `/scene/<tag>` and `/room/<tag>` are the same shell as `/case/<tag>` with one
 * beat in it. That is not a trick to reuse a component: autosave, Continue and
 * the backlog are the shell's job for every leaf, and a scene played on its own
 * that could not be resumed would be a second, worse consumer of the same
 * runtime.
 */
export const SINGLE_LEAF_CASE_ID = "single_leaf";

export function singleBeatCase(
  displayName: string,
  kind: CaseBeatKind,
  runTag: string,
): CaseDocument {
  return parseCase({
    schema_version: CASE_SCHEMA_VERSION,
    kind: CASE_KIND,
    case_id: SINGLE_LEAF_CASE_ID,
    display_name: displayName,
    entry: "only",
    facts: [],
    beats: [
      {
        beat_id: "only",
        kind,
        run_tag: runTag,
        display_name: displayName,
        terminal: true,
        edges: [],
      },
    ],
  });
}

// ------------------------------------------------------------------ runtime

/** Where a player is in a case, and what they are carrying. */
export interface CaseProgress {
  readonly beatId: string;
  readonly facts: readonly string[];
}

export function initialCaseProgress(document: CaseDocument): CaseProgress {
  return Object.freeze({ beatId: document.entry, facts: Object.freeze([]) });
}

export function caseBeat(document: CaseDocument, beatId: string): CaseBeat | null {
  return document.beats.find((beat) => beat.beatId === beatId) ?? null;
}

/** A beat with no outgoing edge ends the case. */
export function caseBeatIsTerminal(beat: CaseBeat): boolean {
  return beat.edges.length === 0;
}

/**
 * Finish the current beat and take the edge its outcome names.
 *
 * `exported` is the leaf's own flag set as it finished; only names the case
 * declared as facts survive the boundary. Nothing else crosses — no inventory,
 * no seen set, no staging — because a fact is the only thing both a scenario and
 * a room can say.
 *
 * Returns the progress at the next beat, or null when the case is over, either
 * because the beat is terminal or because no edge matches the outcome. The
 * second case is the producer's proof failing, not the player's problem: it ends
 * the case rather than stranding them on a screen with nothing to press.
 */
export function advanceCase(
  document: CaseDocument,
  progress: CaseProgress,
  outcome: string,
  exported: readonly string[],
): CaseProgress | null {
  const beat = caseBeat(document, progress.beatId);
  if (beat === null) return null;
  const carried = mergeFacts(document, progress.facts, exported);
  const edge = beat.edges.find((entry) => entry.outcome === outcome);
  if (edge === undefined) return null;
  return Object.freeze({ beatId: edge.to, facts: carried });
}

/** The facts a finished beat leaves behind, whether or not the case continues. */
export function mergeFacts(
  document: CaseDocument,
  carried: readonly string[],
  exported: readonly string[],
): readonly string[] {
  const declared = new Set(document.facts);
  const merged = new Set(carried.filter((fact) => declared.has(fact)));
  for (const fact of exported) {
    if (declared.has(fact)) merged.add(fact);
  }
  return Object.freeze([...merged].sort());
}

/** How far through the case a player is, for the shell's one line of chrome. */
export function caseBeatNumber(document: CaseDocument, beatId: string): number {
  return document.beats.findIndex((beat) => beat.beatId === beatId) + 1;
}

// ------------------------------------------------------------------ members

/**
 * Which scenario inside a run a beat plays.
 *
 * A room beat must not carry one — a room run publishes exactly one room, so an
 * id there is a projection that has confused itself, and it is refused rather
 * than ignored. A scenario beat may omit it, and absent means "this run
 * publishes exactly one scenario, play that": which is true of every
 * single-scenario run and is what `/scene/<tag>` relies on. `case bundle`
 * always writes the id, so the chained path never depends on the fallback.
 */
function scenarioIdFor(value: unknown, kind: CaseBeatKind, index: number): string | null {
  if (kind === "room") {
    if (value !== undefined) {
      throw new Error(
        `case beats[${index}].scenario_id is set on a room beat; a room run publishes one room`,
      );
    }
    return null;
  }
  if (value === undefined) return null;
  return snakeId(value, `case beats[${index}].scenario_id`);
}

function beat(value: unknown, index: number): CaseBeat {
  const record = strictRecord(
    value,
    ["beat_id", "kind", "run_tag", "display_name"],
    `case beats[${index}]`,
    ["member", "reads", "writes", "terminal", "edges", "scenario_id"],
  );
  const kind = record.kind;
  if (kind !== "scenario" && kind !== "room") {
    throw new Error(`case beats[${index}].kind must be scenario or room`);
  }
  const edges = list(record.edges ?? [], `case beats[${index}].edges`, 0);
  // `terminal` and "declares no edges" say the same thing, so a document in which
  // they disagree is refused rather than one of them being believed.
  if (record.terminal !== undefined) {
    if (typeof record.terminal !== "boolean") {
      throw new Error(`case beats[${index}].terminal must be a boolean`);
    }
    if (record.terminal !== (edges.length === 0)) {
      throw new Error(
        `case beats[${index}].terminal disagrees with the edges it declares`,
      );
    }
  }
  return Object.freeze({
    beatId: snakeId(record.beat_id, `case beats[${index}].beat_id`),
    kind,
    runTag: runTag(record.run_tag, `case beats[${index}].run_tag`),
    scenarioId: scenarioIdFor(record.scenario_id, kind, index),
    displayName: text(record.display_name, `case beats[${index}].display_name`, 96),
    member:
      record.member === undefined || record.member === null
        ? null
        : text(record.member, `case beats[${index}].member`, 256),
    reads: Object.freeze(
      list(record.reads ?? [], `case beats[${index}].reads`, 0).map((entry, at) =>
        snakeId(entry, `case beats[${index}].reads[${at}]`),
      ),
    ),
    writes: Object.freeze(
      list(record.writes ?? [], `case beats[${index}].writes`, 0).map((entry, at) =>
        snakeId(entry, `case beats[${index}].writes[${at}]`),
      ),
    ),
    edges: Object.freeze(
      edges.map((entry, at) => {
        const edge = strictRecord(entry, ["outcome", "to"], `case beats[${index}].edges[${at}]`);
        return Object.freeze({
          outcome: snakeId(edge.outcome, `case beats[${index}].edges[${at}].outcome`),
          to: snakeId(edge.to, `case beats[${index}].edges[${at}].to`),
        });
      }),
    ),
  });
}

function fact(value: unknown, index: number): CaseFact {
  const record = strictRecord(value, ["fact_id"], `case facts[${index}]`, [
    "establishment",
    "summary",
  ]);
  const establishment = record.establishment ?? "defaults_false";
  if (establishment !== "required" && establishment !== "defaults_false") {
    throw new Error(`case facts[${index}].establishment must be required or defaults_false`);
  }
  return Object.freeze({
    factId: snakeId(record.fact_id, `case facts[${index}].fact_id`),
    establishment,
    summary:
      record.summary === undefined || record.summary === null
        ? null
        : text(record.summary, `case facts[${index}].summary`, 300),
  });
}

// ------------------------------------------------------------------ scalars

function strictRecord(
  value: unknown,
  requiredKeys: readonly string[],
  label: string,
  optionalKeys: readonly string[] = [],
): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  const record = value as Record<string, unknown>;
  const known = new Set([...requiredKeys, ...optionalKeys]);
  const missing = requiredKeys.filter(
    (key) => !Object.prototype.hasOwnProperty.call(record, key),
  );
  const extra = Object.keys(record).filter((key) => !known.has(key));
  if (missing.length > 0 || extra.length > 0) {
    throw new Error(
      `${label} keys must match the schema` +
        `${missing.length > 0 ? `; missing ${missing.join(", ")}` : ""}` +
        `${extra.length > 0 ? `; unexpected ${extra.join(", ")}` : ""}`,
    );
  }
  return record;
}

function list(value: unknown, label: string, minimum: number): readonly unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  if (value.length < minimum) {
    throw new Error(`${label} must contain at least ${minimum} entries`);
  }
  return value;
}

function text(value: unknown, label: string, maxLength: number): string {
  if (typeof value !== "string" || value.length === 0 || value.trim() !== value) {
    throw new Error(`${label} must be a trimmed non-empty string`);
  }
  if (value.length > maxLength) throw new Error(`${label} must be at most ${maxLength} characters`);
  return value;
}

function snakeId(value: unknown, label: string): string {
  if (typeof value !== "string" || !SNAKE_ID.test(value)) {
    throw new Error(`${label} must be a lower_snake_case identifier`);
  }
  return value;
}

function runTag(value: unknown, label: string): string {
  if (typeof value !== "string" || !RUN_TAG.test(value)) {
    throw new Error(`${label} must be a run tag`);
  }
  return value;
}

function exact<ValueT>(value: unknown, expected: ValueT, label: string): void {
  if (value !== expected) throw new Error(`${label} must be ${JSON.stringify(expected)}`);
}
