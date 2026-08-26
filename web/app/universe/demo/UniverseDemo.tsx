"use client";

import { useMemo, useState } from "react";
import type {
  IllustratedMapFeatureV1,
  IllustratedMapManifestV1,
} from "@/lib/illustrated-map/contract";
import AtlasViewport from "./AtlasViewport";
import styles from "./UniverseDemo.module.css";

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
    <main className={styles.shell}>
      <header className={styles.header}>
        <div>
          <a className={styles.exitLink} href="/">
            ← stage-gen
          </a>
          <p className={styles.eyebrow}>Universe / demo</p>
          <h1>Universe planner and explorer</h1>
          <p className={styles.lede}>
            Technical workspace for planning and exploring generated worlds. Current
            module: illustrated map.
          </p>
        </div>
        <dl className={styles.headerFacts}>
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

      <div className={styles.workspace}>
        <section className={styles.mapPanel} aria-labelledby="atlas-heading">
          <div className={styles.mapToolbar}>
            <div>
              <h2 id="atlas-heading">{manifest.display_name}</h2>
              <p id="map-instructions">
                {manifest.coordinate_space.width} × {manifest.coordinate_space.height}
                {" · "}
                {manifest.features.length} point features · two-finger scroll: pan ·
                pinch: zoom · drag: pan
              </p>
            </div>
            <button
              className={styles.fitButton}
              type="button"
              onClick={() => setFitRequest((value) => value + 1)}
            >
              Fit extent
            </button>
          </div>

          <div className={styles.mapFrame}>
            <AtlasViewport
              manifest={manifest}
              raster_url={raster_url}
              selected_feature_id={selectedFeatureId}
              fit_request={fitRequest}
              on_select={setSelectedFeatureId}
            />
            <div className={styles.mapCorner} aria-hidden="true">
              image-pixel-v1 · top_left
            </div>
          </div>

          <div className={styles.mapFooter}>
            <span>
              raster: {manifest.raster.path} · {manifest.raster.delivery_kind}
            </span>
            <a href={manifest_url}>manifest.json ↗</a>
          </div>
        </section>

        <aside className={styles.inspector} aria-labelledby="inspector-heading">
          <div className={styles.inspectorHeading}>
            <p className={styles.eyebrow}>Selection</p>
            <h2 id="inspector-heading">Feature inspector</h2>
          </div>

          <div className={styles.featurePanel} aria-live="polite">
            {selectedFeature ? (
              <>
                <h3>{selectedFeature.label.fallback_text}</h3>
                <dl className={styles.featureFacts}>
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
                <p className={styles.featureSummary}>{selectedFeature.summary}</p>
                <div className={styles.tags} aria-label="Feature tags">
                  {selectedFeature.tags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
              </>
            ) : (
              <div className={styles.emptySelection}>
                <h3>No feature selected</h3>
                <p>Click a map point or select a row from the feature index.</p>
              </div>
            )}
          </div>

          <nav className={styles.featureIndex} aria-label="Map features">
            <div className={styles.indexHeading}>
              <h3>Feature index</h3>
              <span>{manifest.features.length}</span>
            </div>
            <ol>
              {manifest.features.map((feature) => (
                <li key={feature.feature_id}>
                  <button
                    type="button"
                    aria-pressed={feature.feature_id === selectedFeatureId}
                    onClick={() => setSelectedFeatureId(feature.feature_id)}
                  >
                    <span className={styles.featureName}>
                      {feature.label.fallback_text}
                    </span>
                    <span className={styles.featureId}>{feature.feature_id}</span>
                    <span className={styles.featureCoordinates}>
                      [{coordinates(feature)}]
                    </span>
                    <span className={styles.featureKind}>
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
