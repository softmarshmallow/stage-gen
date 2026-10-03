import { describe, expect, test } from "bun:test";
import { parseViewContexts, viewPolicy, withUrls } from "./view-context";

const TEMPLATE = `views/${"a".repeat(64)}.html`;

function contexts(overrides: Record<string, unknown> = {}) {
  return {
    kind: "gnode-view-contexts-v1",
    view_origins: [],
    views: [
      {
        kind: "gnode-view-context-v1",
        scope: "node",
        node_id: "compose#1",
        template: TEMPLATE,
        step: { path: "compose", title: "Compose the scrolling background", status: "succeeded", with: {} },
        run: { id: "2026-10-03-1", workflow: "looping-parallax", status: "succeeded", cost_usd: 0 },
        inputs: {
          canvas: { width: 640, height: 360 },
          layers: { sky: { kind: "image/png", digest: "b".repeat(64), size: 3, key: "sky", ref: `views/files/${"b".repeat(64)}.png` } },
        },
        outputs: { manifest: { kind: "json", digest: "c".repeat(64), size: 2, key: null, ref: `views/files/${"c".repeat(64)}.json`, value: {} } },
        facts: {},
        ...overrides,
      },
    ],
  };
}

describe("view contexts", () => {
  test("every file gains the URL it is served at, and nothing else changes", () => {
    const [view] = parseViewContexts(contexts()).views;
    const sent = withUrls(view, (ref) => `/api/assets/r/t/${ref}`) as Record<string, any>;
    expect(sent.inputs.layers.sky.url).toBe(`/api/assets/r/t/views/files/${"b".repeat(64)}.png`);
    expect(sent.inputs.canvas).toEqual({ width: 640, height: 360 });
    expect(sent.outputs.manifest.value).toEqual({});
  });

  test("a workflow's own view reads every step by name, and the run's outputs", () => {
    const image = { kind: "image/png", digest: "d".repeat(64), size: 3, key: null, ref: `views/files/${"d".repeat(64)}.png` };
    const whole = {
      kind: "gnode-view-context-v1",
      scope: "workflow",
      node_id: null,
      template: TEMPLATE,
      run: { id: "2026-10-03-1", workflow: "universe", status: "succeeded", cost_usd: 0 },
      outputs: {},
      steps: { entity: { instances: [{ key: "ferry", status: "succeeded", steps: { draw: { outputs: { image } } } }] } },
    };
    const [view] = parseViewContexts({ kind: "gnode-view-contexts-v1", views: [whole] }).views;
    expect([view.scope, view.nodeId, view.title]).toEqual(["workflow", null, "universe"]);
    const sent = withUrls(view, (ref) => `/a/${ref}`) as Record<string, any>;
    expect(sent.steps.entity.instances[0].steps.draw.outputs.image.url).toBe(`/a/${image.ref}`);
    const escaping = { ...whole, steps: { draw: { outputs: { image: { ...image, ref: "../x.png" } } } } };
    expect(() => parseViewContexts({ kind: "gnode-view-contexts-v1", views: [escaping] })).toThrow();
  });

  test("a template outside the run's kept views, or a file escaping the run, is refused", () => {
    expect(() => parseViewContexts(contexts({ template: "../x.html" }))).toThrow();
    expect(() => parseViewContexts(contexts({ template: "files/compose/x.html" }))).toThrow();
    const escaping = contexts();
    (escaping.views[0].inputs.layers.sky as any).ref = "../../secret.png";
    expect(() => parseViewContexts(escaping)).toThrow();
  });

  test("view origins must be https origins", () => {
    expect(() => parseViewContexts({ ...contexts(), view_origins: ["http://example.com"] })).toThrow();
    expect(parseViewContexts({ ...contexts(), view_origins: ["https://cdn.example.com"] }).viewOrigins).toEqual([
      "https://cdn.example.com",
    ]);
  });

  test("a view is served sandboxed, reaching only the viewer and its declared origins", () => {
    const policy = viewPolicy("http://localhost:3000", ["https://cdn.example.com"]);
    expect(policy).toContain("sandbox allow-scripts");
    expect(policy).toContain("default-src 'none'");
    expect(policy).toContain("img-src http://localhost:3000 data: blob: https://cdn.example.com");
    expect(policy).not.toContain("allow-same-origin");
    expect(policy).toContain("script-src 'unsafe-inline' http://localhost:3000/_gnode/view.js https://cdn.example.com");
  });
});
