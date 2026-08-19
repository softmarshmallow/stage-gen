export const DIALOGUE_SCENE_FRAMING_PUBLIC_MIN = 0 as const;
export const DIALOGUE_SCENE_FRAMING_PUBLIC_MAX = 100 as const;
export const DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN = 25 as const;
export const DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX = 85 as const;

export type DialogueSceneFramingSemanticTier =
  | "full-body"
  | "waist-up"
  | "head-and-shoulders";
export type DialogueSceneFramingCameraTerm = "full shot" | "medium shot" | "close-up";
export type DialogueSceneFramingBand = readonly [number, number];

interface FramingTier {
  readonly anchor: number;
  readonly semanticTier: DialogueSceneFramingSemanticTier;
  readonly cameraTerm: DialogueSceneFramingCameraTerm;
  readonly cropDirective: string;
  readonly visibleAnatomy: string;
  readonly inFramePose: string;
  readonly faceHeightPercent: DialogueSceneFramingBand;
  readonly headroomPercent: DialogueSceneFramingBand;
  readonly presentationXPercent: number;
}

export interface DialogueSceneFramingResult {
  readonly inputZoom: number;
  readonly clampedZoom: number;
  readonly effectiveZoom: number;
  readonly saturated: boolean;
  readonly semanticTier: DialogueSceneFramingSemanticTier;
  readonly cameraTerm: DialogueSceneFramingCameraTerm;
  readonly cropDirective: string;
  readonly bands: {
    readonly faceHeightPercent: DialogueSceneFramingBand;
    readonly headroomPercent: DialogueSceneFramingBand;
  };
  readonly prompt: {
    readonly method: "hybrid-crop-first-v2";
    readonly role: "coarse-generation-guidance";
    readonly requiresDeterministicFinalCrop: true;
    readonly text: string;
  };
  readonly presentation: {
    readonly scale: number;
    readonly position: {
      readonly xPercent: number;
      readonly yPercent: number;
    };
    readonly transformOrigin: "top center";
  };
}

export interface DialogueSceneFramingPromptContext {
  readonly identity: readonly string[];
  readonly style: readonly string[];
  readonly expression: string;
  readonly tierOverrides?: Partial<
    Record<
      DialogueSceneFramingSemanticTier,
      {
        readonly cropDirective?: string;
        readonly visibleAnatomy?: string;
      }
    >
  >;
}

const IDENTITY = [
  "one original adult observatory courier",
  "same facial structure and adult age",
  "dark-auburn bob haircut",
  "brass communications earpiece",
  "amber scarf",
  "long navy courier coat with brass fasteners",
  "same body proportions and costume construction",
  "no added, removed, or redesigned identity-defining features when those features are within frame",
] as const;

const STYLE = [
  "coherent polished 2D game character art",
  "same painterly edge treatment, material rendering, palette, and lighting direction as the reference",
  "no photorealism or 3D-render styling",
] as const;

const TIERS = Object.freeze([
  Object.freeze({
    anchor: 25,
    semanticTier: "full-body",
    cameraTerm: "full shot",
    cropDirective:
      "the bottom edge of the final canvas must sit below both boot soles while retaining a floor margin of 2%-6% of canvas height; the top of the hair, both hands, complete coat hem, both legs, and both boots must remain inside the canvas",
    visibleAnatomy:
      "entire hair and head, neck, shoulders, torso, both arms and hands, coat hem, both legs, and both boots",
    inFramePose:
      "full figure upright, shoulders level, body turned ten degrees to the viewer's left, head and gaze toward the viewer, arms relaxed naturally at the sides",
    faceHeightPercent: Object.freeze([7, 11]) as DialogueSceneFramingBand,
    headroomPercent: Object.freeze([4, 8]) as DialogueSceneFramingBand,
    presentationXPercent: 72,
  }),
  Object.freeze({
    anchor: 60,
    semanticTier: "waist-up",
    cameraTerm: "medium shot",
    cropDirective:
      "the bottom edge of the final canvas must cross at the natural waist directly below the coat's waist fastener; hips, thighs, knees, lower legs, and boots must remain outside the canvas",
    visibleAnatomy:
      "entire hair and head, neck, both shoulders, torso through the natural waist, and both upper arms",
    inFramePose:
      "visible upper torso upright, both shoulders level, upper torso turned ten degrees to the viewer's left, head and gaze toward the viewer",
    faceHeightPercent: Object.freeze([18, 26]) as DialogueSceneFramingBand,
    headroomPercent: Object.freeze([4, 8]) as DialogueSceneFramingBand,
    presentationXPercent: 62,
  }),
  Object.freeze({
    anchor: 85,
    semanticTier: "head-and-shoulders",
    cameraTerm: "close-up",
    cropDirective:
      "the bottom edge of the final canvas must cross the upper chest below the clavicles while retaining the complete shoulder line; waist, hips, hands, lower arms, legs, and boots must remain outside the canvas",
    visibleAnatomy:
      "entire hair and head, face, neck, both complete shoulders, and upper chest",
    inFramePose:
      "visible head, neck, and shoulders upright, both shoulders level, head and gaze toward the viewer",
    faceHeightPercent: Object.freeze([34, 46]) as DialogueSceneFramingBand,
    headroomPercent: Object.freeze([3, 7]) as DialogueSceneFramingBand,
    presentationXPercent: 52,
  }),
] satisfies readonly FramingTier[]);

const DEFAULT_PROMPT_CONTEXT = Object.freeze({
  identity: IDENTITY,
  style: STYLE,
  expression: "calm closed-mouth neutral expression",
} satisfies DialogueSceneFramingPromptContext);
const CANVAS = "portrait-oriented 2:3 canvas";
const BACKGROUND =
  "flat uniform neutral middle-gray backdrop with no gradient, texture, scenery, props, horizon, cast shadow, or floor line";
const OUTPUT =
  "one opaque RGB image generated directly, with no transparency, alpha, chroma key, mask, grid, or postprocessing";
const EXCLUSIONS = "no text, captions, logos, signatures, or watermarks";
const FULL_SHOT_FACE_MIDPOINT_PERCENT = 9;

export function mapDialogueSceneFraming(
  framingZoom: number,
  promptContext: DialogueSceneFramingPromptContext = DEFAULT_PROMPT_CONTEXT,
): DialogueSceneFramingResult {
  if (!Number.isFinite(framingZoom)) {
    throw new Error("dialogue-scene framingZoom must be a finite number");
  }
  assertPromptContext(promptContext);

  const clampedZoom = clamp(
    framingZoom,
    DIALOGUE_SCENE_FRAMING_PUBLIC_MIN,
    DIALOGUE_SCENE_FRAMING_PUBLIC_MAX,
  );
  const effectiveZoom = clamp(
    clampedZoom,
    DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN,
    DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX,
  );
  const tier = nearestTier(effectiveZoom);
  const tierOverride = promptContext.tierOverrides?.[tier.semanticTier];
  const cropDirective = tierOverride?.cropDirective ?? tier.cropDirective;
  const visibleAnatomy = tierOverride?.visibleAnatomy ?? tier.visibleAnatomy;
  const faceHeightPercent = interpolateBand(effectiveZoom, "faceHeightPercent");
  const headroomPercent = interpolateBand(effectiveZoom, "headroomPercent");
  const faceMidpoint = midpoint(faceHeightPercent);
  const presentationXPercent = interpolateScalar(
    effectiveZoom,
    "presentationXPercent",
  );

  const promptText = renderCropFirstPrompt({
    zoom: clampedZoom,
    tier,
    cropDirective,
    visibleAnatomy,
    faceHeightPercent,
    headroomPercent,
    promptContext,
  });

  return Object.freeze({
    inputZoom: framingZoom,
    clampedZoom,
    effectiveZoom,
    saturated: effectiveZoom !== clampedZoom,
    semanticTier: tier.semanticTier,
    cameraTerm: tier.cameraTerm,
    cropDirective,
    bands: Object.freeze({
      faceHeightPercent,
      headroomPercent,
    }),
    prompt: Object.freeze({
      method: "hybrid-crop-first-v2",
      role: "coarse-generation-guidance",
      requiresDeterministicFinalCrop: true,
      text: promptText,
    }),
    presentation: Object.freeze({
      scale: roundTo(faceMidpoint / FULL_SHOT_FACE_MIDPOINT_PERCENT, 3),
      position: Object.freeze({
        xPercent: roundTo(presentationXPercent, 1),
        yPercent: roundTo(midpoint(headroomPercent), 1),
      }),
      transformOrigin: "top center",
    }),
  });
}

export function normalizeDialogueSceneFramingScale(
  targetScale: number,
  sourceBaselineScale: number,
): number {
  if (
    !Number.isFinite(targetScale) ||
    !Number.isFinite(sourceBaselineScale) ||
    targetScale <= 0 ||
    sourceBaselineScale <= 0
  ) {
    throw new Error("dialogue-scene framing scales must be finite positive numbers");
  }
  return roundTo(targetScale / sourceBaselineScale, 3);
}

function renderCropFirstPrompt({
  zoom,
  tier,
  cropDirective,
  visibleAnatomy,
  faceHeightPercent,
  headroomPercent,
  promptContext,
}: {
  readonly zoom: number;
  readonly tier: FramingTier;
  readonly cropDirective: string;
  readonly visibleAnatomy: string;
  readonly faceHeightPercent: DialogueSceneFramingBand;
  readonly headroomPercent: DialogueSceneFramingBand;
  readonly promptContext: DialogueSceneFramingPromptContext;
}): string {
  return `FINAL CANVAS CROP IS MANDATORY: ${cropDirective}. Anatomy outside this crop is intentionally off-frame; do not reconstruct it, reveal it, or shrink the character to fit it into the canvas. Create one ${tier.cameraTerm} of the exact character in the supplied reference image with framingZoom=${formatZoom(zoom)}/100, where higher means tighter. The crop landmark overrides every percentage target and all other framing guidance. Required visible anatomy: ${visibleAnatomy}. Apply identity invariants only to features that are in frame: ${promptContext.identity.join("; ")}. Preserve style: ${promptContext.style.join("; ")}. In-frame pose only: ${tier.inFramePose}. Expression: ${promptContext.expression}. Secondary audit targets only, never reasons to loosen the crop: face height ${formatBand(faceHeightPercent)}; headroom ${formatBand(headroomPercent)}. Canvas: ${CANVAS}. Backdrop: ${BACKGROUND}. Output: ${OUTPUT}. Exclusions: ${EXCLUSIONS}.`;
}

function assertPromptContext(context: DialogueSceneFramingPromptContext): void {
  const tierOverrideFragments = Object.values(context.tierOverrides ?? {}).flatMap(
    (override) =>
      override === undefined
        ? []
        : [override.cropDirective, override.visibleAnatomy].filter(
            (value): value is string => value !== undefined,
          ),
  );
  if (
    context.identity.length < 1 ||
    context.style.length < 1 ||
    !context.identity.every(validPromptFragment) ||
    !context.style.every(validPromptFragment) ||
    !validPromptFragment(context.expression) ||
    !tierOverrideFragments.every(validPromptFragment)
  ) {
    throw new Error(
      "dialogue-scene framing prompt context requires non-empty trimmed identity, style, and expression text",
    );
  }
}

function validPromptFragment(value: string): boolean {
  return typeof value === "string" && value.trim() === value && value.length > 0;
}

function nearestTier(zoom: number): FramingTier {
  if (zoom < 42.5) return TIERS[0];
  if (zoom < 72.5) return TIERS[1];
  return TIERS[2];
}

function interpolateBand(
  zoom: number,
  key: "faceHeightPercent" | "headroomPercent",
): DialogueSceneFramingBand {
  const [lower, upper, ratio] = interpolationSegment(zoom);
  return Object.freeze([
    roundTo(lerp(lower[key][0], upper[key][0], ratio), 1),
    roundTo(lerp(lower[key][1], upper[key][1], ratio), 1),
  ]);
}

function interpolateScalar(zoom: number, key: "presentationXPercent"): number {
  const [lower, upper, ratio] = interpolationSegment(zoom);
  return lerp(lower[key], upper[key], ratio);
}

function interpolationSegment(zoom: number): readonly [FramingTier, FramingTier, number] {
  if (zoom <= TIERS[1].anchor) {
    return [
      TIERS[0],
      TIERS[1],
      (zoom - TIERS[0].anchor) / (TIERS[1].anchor - TIERS[0].anchor),
    ];
  }
  return [
    TIERS[1],
    TIERS[2],
    (zoom - TIERS[1].anchor) / (TIERS[2].anchor - TIERS[1].anchor),
  ];
}

function formatBand([low, high]: DialogueSceneFramingBand): string {
  return `${low.toFixed(1)}%-${high.toFixed(1)}% of canvas height, inclusive`;
}

function formatZoom(value: number): string {
  const rounded = roundTo(value, 1);
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function midpoint([low, high]: DialogueSceneFramingBand): number {
  return (low + high) / 2;
}

function lerp(start: number, end: number, ratio: number): number {
  return start + (end - start) * ratio;
}

function roundTo(value: number, decimalPlaces: number): number {
  const factor = 10 ** decimalPlaces;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}
