// The component set every page source composes: the port of the retired showcase's
// @component registry, with the same names, prop names, prop types and required props.
// lib/mdx.ts binds each entry to one page and checks its props before it renders, as
// render_element did; the block files themselves only render.

import type { ComponentType } from "react";
import Hero from "./Hero";
import Stats from "./Stats";
import Stat from "./Stat";
import Filmstrip from "./Filmstrip";
import Frame from "./Frame";
import Guards from "./Guards";
import Guard from "./Guard";
import Models from "./Models";
import Columns from "./Columns";
import Files from "./Files";
import File from "./File";
import Scope from "./Scope";
import Works from "./Works";
import Limit from "./Limit";
import Tip from "./Tip";
import Compare from "./Compare";
import Painter from "./Painter";
import Atlas from "./Atlas";
import FaceRig from "./FaceRig";
import PartStage from "./PartStage";
import SpriteStage from "./SpriteStage";
import ParallaxLoop from "./ParallaxLoop";
import ParallaxStage from "./ParallaxStage";
import UiKit from "./UiKit";
import Ref from "./Ref";
import Try from "./Try";
import Agent from "./Agent";
import Shell from "./Shell";

/** A prop's type as the showcase declared it: str, list or int. */
export type PropKind = "string" | "list" | "int";

export interface BlockSpec {
  // Blocks take their MDX props plus the bound page; lib/mdx.ts supplies both.
  readonly render: ComponentType<any>;
  readonly props: Readonly<Record<string, PropKind>>;
  readonly required: readonly string[];
}

export const BLOCKS: Readonly<Record<string, BlockSpec>> = {
  Hero: { render: Hero, props: { input: "string", output: "string", also: "string", clip: "string" }, required: ["input", "output"] },
  Stats: { render: Stats, props: {}, required: [] },
  Stat: { render: Stat, props: { metric: "string" }, required: ["metric"] },
  Filmstrip: { render: Filmstrip, props: {}, required: [] },
  Frame: { render: Frame, props: { node: "string", media: "list" }, required: ["node"] },
  Guards: { render: Guards, props: {}, required: [] },
  Guard: { render: Guard, props: { node: "string", how: "string" }, required: ["node", "how"] },
  Models: { render: Models, props: {}, required: [] },
  Columns: { render: Columns, props: {}, required: [] },
  Files: { render: Files, props: {}, required: [] },
  File: { render: File, props: { path: "string" }, required: ["path"] },
  Scope: { render: Scope, props: {}, required: [] },
  Works: { render: Works, props: {}, required: [] },
  Limit: { render: Limit, props: {}, required: [] },
  Tip: { render: Tip, props: {}, required: [] },
  Compare: { render: Compare, props: { node: "string", media: "list", left: "string", right: "string", at: "int" }, required: ["node", "left", "right"] },
  Painter: { render: Painter, props: { start: "list" }, required: ["start"] },
  Atlas: { render: Atlas, props: { output: "string" }, required: ["output"] },
  FaceRig: { render: FaceRig, props: { output: "string" }, required: ["output"] },
  PartStage: { render: PartStage, props: { output: "string", clip: "string" }, required: ["output"] },
  SpriteStage: { render: SpriteStage, props: { output: "string" }, required: ["output"] },
  ParallaxLoop: { render: ParallaxLoop, props: { output: "string" }, required: ["output"] },
  ParallaxStage: { render: ParallaxStage, props: { output: "string" }, required: ["output"] },
  UiKit: { render: UiKit, props: { backdrop: "string", buttons: "list" }, required: ["buttons"] },
  Ref: { render: Ref, props: { input: "string" }, required: ["input"] },
  Try: { render: Try, props: {}, required: [] },
  Agent: { render: Agent, props: {}, required: [] },
  Shell: { render: Shell, props: {}, required: [] },
};

/**
 * Props that name something of the bound example, by what they name. lib/mdx.ts resolves
 * each against the page before a block renders, so a page naming a metric, output, input
 * or node its example lacks fails the build even while the block is a stub.
 */
export const NAMED_PROPS: Readonly<Record<string, "node" | "metric" | "output" | "input">> = {
  node: "node",
  metric: "metric",
  output: "output",
  input: "input",
  also: "input",
  backdrop: "input",
};
