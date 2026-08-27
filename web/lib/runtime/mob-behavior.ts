import {
  attackFootLevelsOverlap,
  type MobIntent,
} from "./combat";

export function constrainMobStrikeToAttackLevel(input: Readonly<{
  requestedIntent: MobIntent;
  mobFootY: number;
  playerFootY: number | null;
  tilePixels: number;
}>): MobIntent {
  if (input.requestedIntent !== "strike") return input.requestedIntent;
  if (
    input.playerFootY !== null &&
    attackFootLevelsOverlap(
      input.mobFootY,
      input.playerFootY,
      input.tilePixels,
    )
  ) {
    return "strike";
  }
  return "chase";
}

/** Recover locomotion after a finite attack/hurt strip has stopped on its last frame. */
export function mobLocomotionAnimationNeedsRestart(input: Readonly<{
  state: "wander" | "chase" | "windup" | "hurt" | "dead";
  currentAnimationKey: string | null;
  idleAnimationKey: string;
  isPlaying: boolean;
}>): boolean {
  if (input.state !== "wander" && input.state !== "chase") return false;
  return (
    input.currentAnimationKey !== input.idleAnimationKey ||
    !input.isPlaying
  );
}
