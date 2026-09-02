"use client";

// The case, played at one URL: scenario, room, scenario, and never a second
// address for the player to type.
//
// This is the shell. It owns the three things that outlive one leaf — where the
// player is, what they are carrying, and what they have already read — and it
// owns nothing about how a scenario or a room draws itself. Each leaf is still
// the whole game inside its own canvas; this component decides which one is on
// screen, hands it the facts an earlier beat exported, listens for the outcome it
// reports, and writes an autosave at every statement so the player can stop.
//
// The chrome is deliberately DOM rather than canvas. A backlog and a Continue are
// not part of either genre's game — they belong to the person holding the device,
// they have to work identically over a scene and over a room, and they are the
// two places in a pilot where a keyboard and a screen reader should just work.

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import RoomPlayer from "./RoomPlayer";
import ScenePlayer from "./ScenePlayer";
import {
  advanceCase,
  caseBeat,
  caseBeatNumber,
  initialCaseProgress,
  mergeFacts,
  ROOM_WIN_OUTCOME,
  type CaseBeat,
  type CaseDocument,
  type CaseProgress,
} from "@/lib/shell/case";
import {
  appendBacklog,
  beatSave,
  clearCaseSave,
  readCaseSave,
  roomSave,
  scenarioSave,
  writeCaseSave,
  type BacklogLine,
  type CaseSave,
} from "@/lib/shell/case-save";
import type { DialogueSceneMoment } from "@/lib/dialogue-scene/scene-game";
import type { DialogueSceneFixture } from "@/lib/dialogue-scene/schema";
import type { RoomManifest } from "@/lib/pointclick/contract";
import type { RoomPlayState } from "@/lib/pointclick/state";

/** One beat with the leaf it plays, or the reason that leaf could not be read. */
export interface CasePlayerLeaf {
  readonly beat: CaseBeat;
  readonly scene: DialogueSceneFixture | null;
  readonly room: RoomManifest | null;
  readonly error: string | null;
}

export interface CasePlayerProps {
  /** The tag the autosave is keyed by; one save per case, and no slots. */
  readonly tag: string;
  readonly caseDocument: CaseDocument;
  readonly leaves: readonly CasePlayerLeaf[];
  /** Where "back" goes; the case itself never navigates. */
  readonly backHref?: string;
}

type Phase = "reading_save" | "offering_continue" | "playing" | "finished";

/**
 * What "the same line, again" means, per leaf kind.
 *
 * A scenario has statement identity and needs nothing else. A room has no such
 * thing — it narrates in response to a click — so its line is identified by the
 * beat, the interactions that have fired, and the words themselves, which is
 * exactly enough to tell a redraw from a new click.
 */
function scenarioLineKey(beatId: string, statementId: string | null): string {
  return `${beatId}:${statementId ?? "end"}`;
}

function roomLineKey(
  beatId: string,
  fired: readonly number[],
  narration: string,
): string {
  return `${beatId}:${fired.join(",")}:${narration}`;
}

interface PendingOutcome {
  readonly beatId: string;
  readonly outcome: string;
  readonly flags: readonly string[];
}

export default function CasePlayer({
  tag,
  caseDocument,
  leaves,
  backHref = "/",
}: CasePlayerProps) {
  const [phase, setPhase] = useState<Phase>("reading_save");
  const [progress, setProgress] = useState<CaseProgress>(() =>
    initialCaseProgress(caseDocument),
  );
  const [resume, setResume] = useState<CaseSave | null>(null);
  const [backlog, setBacklog] = useState<readonly BacklogLine[]>([]);
  const [backlogOpen, setBacklogOpen] = useState(false);
  const [pending, setPending] = useState<PendingOutcome | null>(null);
  const [ending, setEnding] = useState<string | null>(null);
  // Which beat has produced its first moment. The loading layer is shown until it
  // has, because a leaf's canvas is TRANSPARENT and therefore never covers
  // anything — an earlier version of this assumed it would, and the label sat in
  // the middle of every painted stage for the whole beat.
  const [drawn, setDrawn] = useState<string | null>(null);

  // Mirrors, because the leaf's callbacks fire from inside a Phaser render and
  // must read the current beat rather than the one captured when they were made.
  const progressRef = useRef(progress);
  progressRef.current = progress;
  const backlogRef = useRef(backlog);
  backlogRef.current = backlog;
  const lastLine = useRef<string | null>(null);

  const leafByBeat = useMemo(
    () => new Map(leaves.map((leaf) => [leaf.beat.beatId, leaf])),
    [leaves],
  );
  const beat = caseBeat(caseDocument, progress.beatId);
  const leaf = beat === null ? undefined : leafByBeat.get(beat.beatId);

  useEffect(() => {
    const saved = readCaseSave(window.localStorage, tag);
    if (saved !== null && caseBeat(caseDocument, saved.beatId) !== null) {
      setResume(saved);
      setBacklog(saved.backlog);
      setPhase("offering_continue");
      return;
    }
    setPhase("playing");
  }, [tag, caseDocument]);

  const startOver = useCallback(() => {
    clearCaseSave(window.localStorage, tag);
    lastLine.current = null;
    setResume(null);
    setBacklog([]);
    setPending(null);
    setEnding(null);
    setProgress(initialCaseProgress(caseDocument));
    setPhase("playing");
  }, [caseDocument, tag]);

  const continueSaved = useCallback(() => {
    if (resume === null) return;
    // The resumed leaf redraws the moment it was saved at, and reports it like any
    // other. Without seeding the key it just reported, Continue would append the
    // line the player is looking at to a backlog that already ends with it.
    lastLine.current =
      resume.room === null
        ? scenarioLineKey(resume.beatId, resume.statementId)
        : roomLineKey(resume.beatId, resume.room.fired, resume.room.narration);
    setProgress({ beatId: resume.beatId, facts: resume.facts });
    setPending(null);
    setPhase("playing");
  }, [resume]);

  /** Remember one line, and answer with the backlog the save should carry. */
  const remember = useCallback(
    (key: string, line: BacklogLine | null): readonly BacklogLine[] => {
      if (line === null || lastLine.current === key) return backlogRef.current;
      lastLine.current = key;
      const next = appendBacklog(backlogRef.current, line);
      backlogRef.current = next;
      setBacklog(next);
      return next;
    },
    [],
  );

  const onMoment = useCallback(
    (moment: DialogueSceneMoment) => {
      const at = progressRef.current;
      setDrawn(at.beatId);
      const carried = remember(
        scenarioLineKey(at.beatId, moment.statementId),
        moment.line === null ? null : { speaker: moment.line.speaker, text: moment.line.text },
      );
      writeCaseSave(
        window.localStorage,
        scenarioSave(tag, at.beatId, at.facts, moment.state, carried),
      );
      if (moment.outcome !== null) {
        setPending({ beatId: at.beatId, outcome: moment.outcome, flags: moment.state.flags });
      }
    },
    [remember, tag],
  );

  const onRoomChange = useCallback(
    (state: RoomPlayState) => {
      const at = progressRef.current;
      setDrawn(at.beatId);
      const carried = remember(roomLineKey(at.beatId, state.fired, state.narration), {
        speaker: null,
        text: state.narration,
      });
      writeCaseSave(window.localStorage, roomSave(tag, at.beatId, at.facts, state, carried));
      if (state.solved) {
        setPending({ beatId: at.beatId, outcome: ROOM_WIN_OUTCOME, flags: state.flags });
      }
    },
    [remember, tag],
  );

  const finish = useCallback(
    (beatId: string, outcome: string, flags: readonly string[]) => {
      const at = progressRef.current;
      if (at.beatId !== beatId) return;
      const next = advanceCase(caseDocument, at, outcome, flags);
      if (next === null) {
        // Terminal, or an outcome the case declares no edge for. Either way the
        // episode is over here; the facts are merged so the closing card can say
        // what the player finished holding.
        mergeFacts(caseDocument, at.facts, flags);
        clearCaseSave(window.localStorage, tag);
        setEnding(outcome);
        setPending(null);
        setPhase("finished");
        return;
      }
      lastLine.current = null;
      setResume(null);
      setPending(null);
      progressRef.current = next;
      setProgress(next);
      writeCaseSave(
        window.localStorage,
        beatSave(tag, next.beatId, next.facts, backlogRef.current),
      );
    },
    [caseDocument, tag],
  );

  // Keys belong to whatever is on top. Each leaf's canvas listens on the window,
  // so an overlay that covered only the pixels would still let a space bar
  // advance a scene nobody can see - a misclick that loses a line, which is the
  // exact failure a backlog exists to undo. Swallowed in the capture phase,
  // except where the shell's own controls are focused and need the key.
  useEffect(() => {
    if (!backlogOpen && phase === "playing") return;
    const swallow = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest("[data-shell-chrome]") !== null) {
        return;
      }
      event.stopPropagation();
    };
    window.addEventListener("keydown", swallow, true);
    window.addEventListener("keyup", swallow, true);
    return () => {
      window.removeEventListener("keydown", swallow, true);
      window.removeEventListener("keyup", swallow, true);
    };
  }, [backlogOpen, phase]);

  const resumeFor = (beatId: string): CaseSave | null =>
    resume !== null && resume.beatId === beatId ? resume : null;

  const total = caseDocument.beats.length;
  const number = beat === null ? 0 : caseBeatNumber(caseDocument, beat.beatId);

  return (
    <main className="fixed inset-0 flex flex-col bg-black">
      <div data-shell-chrome className="flex items-center gap-3 px-3 py-1.5 text-[11px] text-dim">
        <Link href={backHref} className="shrink-0 whitespace-nowrap text-fg no-underline">
          [ ◂ back ]
        </Link>
        <span className="truncate">
          {caseDocument.displayName}
          {beat === null ? null : (
            <>
              {" · "}
              <span className="text-fg">{beat.displayName}</span>
              {` · beat ${number} of ${total}`}
            </>
          )}
        </span>
        <span className="grow" />
        <button
          type="button"
          onClick={() => setBacklogOpen((open) => !open)}
          className="shrink-0 cursor-pointer border border-dim/50 bg-transparent px-2 py-0.5 text-[11px] text-fg"
        >
          {backlogOpen ? "close backlog" : `backlog (${backlog.length})`}
        </button>
      </div>

      <div className="relative min-h-0 flex-1">
        {/*
          A beat's art is decoded before its canvas draws anything, and on the supper —
          a stage plus five full-height plates — that is several seconds of black with
          nothing to say it is working. This layer names the beat while that happens,
          so the wait reads as the story arriving rather than as a hang.

          It is hidden on the beat's first moment rather than by being drawn over: the
          leaf's canvas is transparent, so it covers nothing, and a label left under a
          painted stage sits in the middle of the picture for the whole beat.
        */}
        {phase === "playing" && beat !== null && drawn !== beat.beatId ? (
          <div
            data-shell-loading
            aria-hidden
            className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center"
          >
            <p className="text-[11px] tracking-wide text-dim">{beat.displayName}</p>
          </div>
        ) : null}

        {phase === "playing" && beat !== null && leaf !== undefined ? (
          <CaseLeaf
            beat={beat}
            leaf={leaf}
            facts={progress.facts}
            saved={resumeFor(beat.beatId)}
            onMoment={onMoment}
            onRoomChange={onRoomChange}
            onFinish={finish}
          />
        ) : null}

        {phase === "offering_continue" && resume !== null ? (
          <Curtain>
            <h2 className="text-lg text-fg">{caseDocument.displayName}</h2>
            <p className="max-w-md text-center text-sm text-dim">
              A save is waiting at{" "}
              <span className="text-fg">
                {caseBeat(caseDocument, resume.beatId)?.displayName ?? resume.beatId}
              </span>
              {resume.statementId === null ? null : (
                <>
                  {", line "}
                  <span className="text-fg">{resume.statementId}</span>
                </>
              )}
              .
            </p>
            <div className="flex gap-3">
              <CurtainButton onClick={continueSaved}>Continue</CurtainButton>
              <CurtainButton onClick={startOver}>Start over</CurtainButton>
            </div>
          </Curtain>
        ) : null}

        {phase === "finished" ? (
          <Curtain>
            <h2 className="text-lg text-fg">The case is closed.</h2>
            <p className="text-sm text-dim">
              It ended through <span className="text-fg">{ending}</span>.
            </p>
            <CurtainButton onClick={startOver}>Play it again</CurtainButton>
          </Curtain>
        ) : null}

        {phase === "playing" && leaf?.error != null ? (
          <Curtain>
            <h2 className="text-lg text-fg">This beat cannot be read.</h2>
            <p className="max-w-lg text-center text-sm text-dim">{leaf.error}</p>
          </Curtain>
        ) : null}

        {phase === "playing" && pending !== null && pending.beatId === progress.beatId ? (
          <div
            data-shell-chrome
            className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center"
          >
            <button
              type="button"
              onClick={() => finish(pending.beatId, pending.outcome, pending.flags)}
              className="pointer-events-auto cursor-pointer border border-fg/70 bg-black/80 px-5 py-2 text-sm text-fg"
            >
              Continue →
            </button>
          </div>
        ) : null}

        {backlogOpen ? (
          <Backlog lines={backlog} onClose={() => setBacklogOpen(false)} />
        ) : null}
      </div>
    </main>
  );
}

function CaseLeaf({
  beat,
  leaf,
  facts,
  saved,
  onMoment,
  onRoomChange,
  onFinish,
}: {
  beat: CaseBeat;
  leaf: CasePlayerLeaf;
  facts: readonly string[];
  saved: CaseSave | null;
  onMoment: (moment: DialogueSceneMoment) => void;
  onRoomChange: (state: RoomPlayState) => void;
  onFinish: (beatId: string, outcome: string, flags: readonly string[]) => void;
}) {
  if (leaf.scene !== null) {
    return (
      <ScenePlayer
        key={beat.beatId}
        fixture={leaf.scene}
        resume={saved?.scenario ?? null}
        carriedFlags={facts}
        onMoment={onMoment}
        onFinish={(outcome, flags) => onFinish(beat.beatId, outcome, flags)}
      />
    );
  }
  if (leaf.room !== null) {
    return (
      <RoomPlayer
        key={beat.beatId}
        tag={beat.runTag}
        manifest={leaf.room}
        resume={saved?.room ?? null}
        carriedFlags={facts}
        onChange={onRoomChange}
      />
    );
  }
  return null;
}

function Curtain({ children }: { children: React.ReactNode }) {
  return (
    <div
      data-shell-chrome
      className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 bg-black/85 px-6"
    >
      {children}
    </div>
  );
}

function CurtainButton({
  onClick,
  children,
}: {
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="cursor-pointer border border-fg/70 bg-transparent px-5 py-2 text-sm text-fg"
    >
      {children}
    </button>
  );
}

/**
 * The last fifty lines, newest at the bottom, speaker and text and nothing else.
 *
 * Fifty because that is the pilot's stated minimum and because an unbounded
 * backlog is a memory leak with a scroll bar. There is no jump-back-to-a-line:
 * rewinding is a save-state feature and this pilot has one save.
 */
function Backlog({
  lines,
  onClose,
}: {
  lines: readonly BacklogLine[];
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-label="Backlog"
      data-shell-chrome
      className="absolute inset-0 z-30 flex flex-col bg-black/95"
    >
      <div className="flex items-center justify-between border-b border-dim/30 px-4 py-2">
        <span className="text-xs text-dim">
          Backlog · the last {lines.length} {lines.length === 1 ? "line" : "lines"}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="cursor-pointer border border-dim/50 bg-transparent px-2 py-0.5 text-[11px] text-fg"
        >
          close
        </button>
      </div>
      <ol className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {lines.length === 0 ? (
          <li className="text-sm text-dim">Nothing has been said yet.</li>
        ) : (
          lines.map((line, index) => (
            <li key={`${index}-${line.text.slice(0, 24)}`} className="mb-3">
              <span className="block text-[11px] uppercase tracking-wide text-dim">
                {line.speaker ?? "—"}
              </span>
              <span className="block text-sm leading-relaxed text-fg">{line.text}</span>
            </li>
          ))
        )}
      </ol>
    </div>
  );
}
