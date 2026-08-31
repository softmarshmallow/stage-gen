import { describe, expect, test } from "bun:test";

import { ferryProgramDocument } from "@/lib/scenario/program.fixture";
import { parseScenarioProgram, serializeScenarioProgram } from "@/lib/scenario/program";
import {
  dialogueSceneExpression,
  dialogueSceneStage,
  validateDialogueSceneFixture,
} from "./schema";

const program = parseScenarioProgram(ferryProgramDocument());

function runSrc(name: string): string {
  return `/api/assets/harborlight/assets/${name}.png`;
}

/** A fixture that exactly covers what the authored ferry scenario asks for. */
function fixture(): Record<string, unknown> {
  return {
    schemaVersion: 1,
    fixtureId: "harborlight-scene",
    title: "The Ferry Bell",
    sceneLabel: "Two travellers wait for the last ferry",
    presentation: { framingZoom: 70, sourceFramingZoom: 70 },
    styleSrc: runSrc("style-plate"),
    stages: program.stages.map((stage) => ({
      stageId: stage.stageId,
      id: stage.stageId.replace(/_/g, "-"),
      src: runSrc(`stage-${stage.stageId.replace(/_/g, "-")}`),
      alt: stage.brief.slice(0, 160),
    })),
    tracks: program.tracks.map((track) => ({
      trackId: track.trackId,
      id: `track-${track.trackId.replace(/_/g, "-")}`,
      src: `/api/assets/harborlight/assets/track-${track.trackId.replace(/_/g, "-")}.mp3`,
    })),
    actors: program.cast
      .filter((member) => member.expressions.length > 0)
      .map((member) => ({
        actorId: member.actorId,
        appearance: {
          id: member.actorId.replace(/_/g, "-"),
          label: member.displayName ?? member.actorId,
          age: 18,
          role: "An original harbor local",
          description: "An original harbor local",
          visualIdentity: "Dark hair and dark eyes",
          artDirection: "cel shaded anime",
        },
        expressions: member.expressions.map((state) => ({
          id: `${member.actorId.replace(/_/g, "-")}-${state}`,
          src: runSrc(`${member.actorId.replace(/_/g, "-")}-${state}`),
          alt: `${member.displayName ?? member.actorId} looking ${state}`,
          state,
          label: state,
          description: `A ${state} expression`,
        })),
      })),
    scenario: serializeScenarioProgram(program),
  };
}

describe("dialogue-scene runtime fixture", () => {
  test("it accepts a scene whose art covers its whole cast and every stage", () => {
    const parsed = validateDialogueSceneFixture(fixture());
    expect(parsed.actors.map((actor) => actor.actorId)).toEqual(["mara", "teo"]);
    expect(parsed.stages.map((stage) => stage.stageId)).toEqual(["pier_dusk", "boathouse"]);
    expect(Object.isFrozen(parsed)).toBeTrue();
  });

  test("it refuses a scenario that plays a track the fixture has no audio for", () => {
    const value = fixture();
    value.tracks = [];
    expect(() => validateDialogueSceneFixture(value)).toThrow(
      "has no audio for track harbor_wind",
    );
  });

  test("it refuses a track whose src is not confined audio", () => {
    const value = fixture();
    (value.tracks as { src: string }[])[0]!.src = "/api/assets/harborlight/assets/track.png";
    expect(() => validateDialogueSceneFixture(value)).toThrow("must be a confined run");
  });

  test("it refuses a scenario that stages a backdrop the fixture has no plate for", () => {
    const value = fixture();
    value.stages = (value.stages as unknown[]).slice(0, 1);
    expect(() => validateDialogueSceneFixture(value)).toThrow(
      "has no backdrop for stage boathouse",
    );
  });

  test("it refuses a scenario that shows an actor the fixture cannot draw", () => {
    const value = fixture();
    value.actors = (value.actors as unknown[]).slice(0, 1);
    expect(() => validateDialogueSceneFixture(value)).toThrow(
      "has no plates for actor teo",
    );
  });

  test("it refuses an actor missing one of the expressions the script uses", () => {
    const value = fixture();
    const actors = value.actors as { expressions: unknown[] }[];
    actors[0]!.expressions = actors[0]!.expressions.slice(0, 2);
    expect(() => validateDialogueSceneFixture(value)).toThrow("has no concerned plate");
  });

  test("it refuses assets assembled from two different runs", () => {
    const value = fixture();
    value.styleSrc = "/api/assets/other-run/assets/style-plate.png";
    expect(() => validateDialogueSceneFixture(value)).toThrow(
      "must all share one run or installed bundle",
    );
  });

  test("it refuses an asset path outside the confined roots", () => {
    const value = fixture();
    value.styleSrc = "/public/style-plate.png";
    expect(() => validateDialogueSceneFixture(value)).toThrow("must be a confined run");
  });

  test("it refuses unknown and missing keys alike", () => {
    expect(() => validateDialogueSceneFixture({ ...fixture(), extra: 1 })).toThrow(
      "unexpected extra",
    );
    const missing = fixture();
    delete missing.title;
    expect(() => validateDialogueSceneFixture(missing)).toThrow("missing title");
  });
});

describe("looking things up by the names the scenario uses", () => {
  const parsed = validateDialogueSceneFixture(fixture());

  test("a stage id resolves to its backdrop, and an unknown one to null", () => {
    expect(dialogueSceneStage(parsed, "boathouse")?.src).toBe(runSrc("stage-boathouse"));
    expect(dialogueSceneStage(parsed, "nowhere")).toBeNull();
  });

  test("an actor resolves to the named expression, falling back to its first plate", () => {
    expect(dialogueSceneExpression(parsed, "teo", "delighted")?.state).toBe("delighted");
    expect(dialogueSceneExpression(parsed, "teo", null)?.state).toBe("neutral");
    expect(dialogueSceneExpression(parsed, "nobody", "neutral")).toBeNull();
  });
});
