"use client";

import { useMemo, useState } from "react";
import type {
  IllustratedMapFeatureV1,
  IllustratedMapManifestV1,
} from "@/lib/illustrated-map/contract";
import { cx } from "@/app/ui";
import AtlasViewport from "./AtlasViewport";

interface UniverseDemoProps {
  readonly manifest: IllustratedMapManifestV1;
  readonly manifest_url: string;
  readonly raster_url: string;
}

const FEATURE_LABELS: Record<IllustratedMapFeatureV1["feature_kind"], string> = {
  settlement: "Settlement",
  landmark: "Landmark",
  natural_feature: "Natural feature",
  crossing: "Crossing",
  ruin: "Ruin",
  sanctuary: "Sanctuary",
};

/** Uppercase accent kicker over a heading. */
const EYEBROW = "text-[0.68rem] tracking-[0.12em] text-accent uppercase";

/** Dim link that warms to the accent. */
const QUIET_LINK = "text-dim no-underline hover:text-accent";

/** Definition rows in a hairline box, hairline-separated from each other. */
const FACT_LIST =
  "m-0 border border-border [&>div+div]:border-t [&>div+div]:border-border " +
  "[&_dt]:text-dim [&_dd]:m-0 [&_dd]:wrap-anywhere";

/** Column panels are the same height and carry the same hairline heading. */
const PANEL_HEADING = "min-h-[74px] border-b border-border px-3.5 py-3";

function coordinates(feature: IllustratedMapFeatureV1): string {
  return feature.geometry.coordinates.join(", ");
}

export default function UniverseDemo({
  manifest,
  manifest_url,
  raster_url,
}: UniverseDemoProps) {
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null);
  const [fitRequest, setFitRequest] = useState(0);
  const featuresById = useMemo(
    () => new Map(manifest.features.map((feature) => [feature.feature_id, feature])),
    [manifest.features],
  );
  const selectedFeature = selectedFeatureId
    ? (featuresById.get(selectedFeatureId) ?? null)
    : null;

  return (
    <main className="min-h-screen bg-bg p-6 text-fg max-[720px]:p-3">
      <header className="mx-auto mb-5 flex w-[min(1480px,100%)] items-end justify-between gap-8 max-[720px]:flex-col max-[720px]:items-start max-[720px]:gap-3">
        <div>
          <a className={QUIET_LINK} href="/">
            ← stage-gen
          </a>
          <p className={cx(EYEBROW, "mt-4")}>Universe / demo</p>
          <h1 className="mt-1 text-[clamp(1.55rem,3vw,2.15rem)] font-semibold tracking-[-0.03em]">
            Universe planner and explorer
          </h1>
          <p className="mt-1.5 text-dim">
            Technical workspace for planning and exploring generated worlds. Current
            module: illustrated map.
          </p>
        </div>
        <dl
          className={cx(
            FACT_LIST,
            "min-w-[390px] bg-bg [&>div]:grid [&>div]:grid-cols-[86px_minmax(0,1fr)] [&>div]:gap-2.5 [&>div]:px-2.5 [&>div]:py-[7px] max-[720px]:w-full max-[720px]:min-w-0",
          )}
        >
          <div>
            <dt>schema</dt>
            <dd>{manifest.kind}</dd>
          </div>
          <div>
            <dt>media</dt>
            <dd>{manifest.raster.media_type}</dd>
          </div>
        </dl>
      </header>

      <div className="mx-auto grid h-[calc(min(72vh,850px)+115px)] w-[min(1480px,100%)] grid-cols-[minmax(0,1fr)_370px] overflow-hidden border border-border bg-bg max-[1050px]:h-auto max-[1050px]:grid-cols-1">
        <section
          className="h-full min-w-0 border-r border-border max-[1050px]:h-auto max-[1050px]:border-r-0 max-[1050px]:border-b"
          aria-labelledby="atlas-heading"
        >
          <div className="flex min-h-[74px] items-center justify-between gap-5 border-b border-border px-3.5 py-3 max-[720px]:flex-col max-[720px]:items-start">
            <div>
              <h2 id="atlas-heading" className="text-[0.95rem] font-semibold">
                {manifest.display_name}
              </h2>
              <p id="map-instructions" className="mt-[3px] text-[0.72rem] text-dim">
                {manifest.coordinate_space.width} × {manifest.coordinate_space.height}
                {" · "}
                {manifest.features.length} point features · two-finger scroll: pan ·
                pinch: zoom · drag: pan
              </p>
            </div>
            <button
              className="flex-none cursor-pointer border border-dim px-[11px] py-[7px] text-fg hover:border-accent hover:text-accent focus-visible:border-accent focus-visible:text-accent focus-visible:outline-none"
              type="button"
              onClick={() => setFitRequest((value) => value + 1)}
            >
              Fit extent
            </button>
          </div>

          <div className="relative min-h-[620px] bg-[#1a1a1a] max-[720px]:aspect-[4/3] max-[720px]:h-auto max-[720px]:min-h-0">
            <AtlasViewport
              manifest={manifest}
              raster_url={raster_url}
              selected_feature_id={selectedFeatureId}
              fit_request={fitRequest}
              on_select={setSelectedFeatureId}
            />
            <div
              className="pointer-events-none absolute right-2.5 bottom-2.5 border border-[#555] bg-bg/80 px-[7px] py-1 text-[0.64rem] text-[#eee]"
              aria-hidden="true"
            >
              image-pixel-v1 · top_left
            </div>
          </div>

          <div className="flex min-h-10 items-center justify-between gap-5 border-t border-border px-3.5 py-[7px] text-[0.66rem] text-dim max-[720px]:flex-col max-[720px]:items-start max-[720px]:gap-0.5">
            <span>
              raster: {manifest.raster.path} · {manifest.raster.delivery_kind}
            </span>
            <a className={QUIET_LINK} href={manifest_url}>
              manifest.json ↗
            </a>
          </div>
        </section>

        <aside
          className="flex h-full min-h-0 flex-col bg-bg max-[1050px]:h-auto"
          aria-labelledby="inspector-heading"
        >
          <div className={PANEL_HEADING}>
            <p className={cx(EYEBROW, "mb-[3px]")}>Selection</p>
            <h2 id="inspector-heading" className="text-[0.95rem] font-semibold">
              Feature inspector
            </h2>
          </div>

          <div
            className="min-h-[260px] border-b border-border bg-[#0d0d0d] px-3.5 py-4"
            aria-live="polite"
          >
            {selectedFeature ? (
              <>
                <h3 className="mb-3.5 text-base font-semibold text-fg">
                  {selectedFeature.label.fallback_text}
                </h3>
                <dl
                  className={cx(
                    FACT_LIST,
                    "[&>div]:grid [&>div]:grid-cols-[128px_minmax(0,1fr)] [&>div]:gap-2 [&>div]:px-[7px] [&>div]:py-[5px] [&>div]:text-[0.68rem]",
                  )}
                >
                  <div>
                    <dt>feature_id</dt>
                    <dd>{selectedFeature.feature_id}</dd>
                  </div>
                  <div>
                    <dt>kind</dt>
                    <dd>{selectedFeature.feature_kind}</dd>
                  </div>
                  <div>
                    <dt>coordinates</dt>
                    <dd>[{coordinates(selectedFeature)}]</dd>
                  </div>
                  <div>
                    <dt>label_min_scale</dt>
                    <dd>{selectedFeature.label.min_screen_pixels_per_image_pixel}</dd>
                  </div>
                  <div>
                    <dt>hit_radius</dt>
                    <dd>{selectedFeature.interaction.hit_radius_image_pixels}px</dd>
                  </div>
                </dl>
                <p className="mt-3 text-[0.74rem] text-dim">
                  {selectedFeature.summary}
                </p>
                <div className="mt-3 flex flex-wrap gap-[5px]" aria-label="Feature tags">
                  {selectedFeature.tags.map((tag) => (
                    <span
                      key={tag}
                      className="border border-border px-[5px] py-0.5 text-[0.62rem] text-dim"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <div className="grid min-h-[200px] content-center">
                <h3 className="mb-3.5 text-base font-semibold text-fg">
                  No feature selected
                </h3>
                <p className="mt-3 max-w-[290px] text-[0.74rem] text-dim">
                  Click a map point or select a row from the feature index.
                </p>
              </div>
            )}
          </div>

          <nav
            className="min-h-0 flex-1 overflow-auto max-[1050px]:max-h-[420px]"
            aria-label="Map features"
          >
            <div className="sticky top-0 z-[2] flex justify-between border-b border-border bg-bg/[0.96] px-3.5 py-[9px]">
              <h3 className="text-[0.68rem] font-medium tracking-[0.08em] uppercase">
                Feature index
              </h3>
              <span className="text-dim">{manifest.features.length}</span>
            </div>
            <ol className="list-none">
              {manifest.features.map((feature) => (
                <li key={feature.feature_id}>
                  <button
                    type="button"
                    className="grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_auto] gap-x-2.5 gap-y-0.5 border-b border-border px-3.5 py-[9px] text-left text-fg hover:bg-hover focus-visible:bg-hover focus-visible:outline-none aria-pressed:bg-hover aria-pressed:shadow-[inset_2px_0_var(--color-accent)]"
                    aria-pressed={feature.feature_id === selectedFeatureId}
                    onClick={() => setSelectedFeatureId(feature.feature_id)}
                  >
                    <span className="text-[0.76rem]">
                      {feature.label.fallback_text}
                    </span>
                    <span className="col-start-1 text-[0.61rem] text-dim">
                      {feature.feature_id}
                    </span>
                    <span className="col-start-2 row-start-1 text-[0.61rem] text-dim">
                      [{coordinates(feature)}]
                    </span>
                    <span className="col-start-2 row-start-2 text-right text-[0.61rem] text-dim">
                      {FEATURE_LABELS[feature.feature_kind]}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </nav>
        </aside>
      </div>
    </main>
  );
}
