// Centralised AI SDK client wiring.
//
// Single place where the Vercel AI Gateway URL + key get pulled from env.
// All stages import the SDK helpers from here so future drift (auth header,
// SDK upgrades, gateway swap) lives in one file. env validation already
// happens at CLI bootstrap (env.ts) — no re-validation here.
//
// The AI SDK auto-detects AI_GATEWAY_API_KEY from process.env, so the gateway
// auth wiring is implicit. If AI_GATEWAY_BASE_URL ever needs to be overridden,
// set it on process.env before any SDK call — that is what this module ensures.

import { generateImage as sdkGenerateImage, generateObject as sdkGenerateObject } from "ai";
import type { PipelineEnv } from "../env.ts";

let configured = false;

/**
 * Idempotently propagate validated env values into the AI SDK's expected
 * environment. The SDK reads these at call time, so setting them on the
 * Node process.env once at startup is sufficient.
 */
export function configureAi(env: PipelineEnv): void {
  if (configured) return;
  process.env.AI_GATEWAY_API_KEY = env.AI_GATEWAY_API_KEY;
  if (env.AI_GATEWAY_BASE_URL) {
    process.env.AI_GATEWAY_BASE_URL = env.AI_GATEWAY_BASE_URL;
  }
  configured = true;
}

/** Re-export the SDK calls every stage uses. Wrap with `withRetry` at call site. */
export const generateImage = sdkGenerateImage;
export const generateObject = sdkGenerateObject;
