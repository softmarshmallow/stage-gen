"use client";

import Link from "next/link";
import { useState } from "react";
import { preparedAssetUrl } from "@/lib/runtime/prepared-manifest";
import type {
  PreparedAssetCard,
  PreparedAssetGroup,
} from "@/lib/shell/prepared-assets";
import ImageLightbox, { type LightboxImage } from "./ImageLightbox";

export type PreparedAssetExplorerModel = Readonly<{
  tag: string;
  game_id: string;
  display_name: string;
  revision: number;
  package_sha256: string;
  artifact_count: number;
  groups: readonly PreparedAssetGroup[];
}>;

const UNGROUPED_GROUP_ID = "ungrouped";

function countAssets(groups: readonly PreparedAssetGroup[]): number {
  return groups.reduce((total, group) => total + group.assets.length, 0);
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function noteFor(group: PreparedAssetGroup): string | null {
  if (group.group_id === UNGROUPED_GROUP_ID) {
    return "published as content by this package, but this view has no place for it yet";
  }
  if (group.role === "provenance") {
    return "records and judged plates the run ships so it can be re-derived; nothing loads them to play";
  }
  return null;
}

export default function PreparedAssetExplorer({
  model,
}: {
  model: PreparedAssetExplorerModel;
}) {
  const [lightbox, setLightbox] = useState<LightboxImage | null>(null);

  const assetGroups = model.groups.filter((group) => group.role === "asset");
  const assetCount = countAssets(assetGroups);
  const provenanceCount = countAssets(
    model.groups.filter((group) => group.role === "provenance"),
  );
  const ungroupedCount = countAssets(
    model.groups.filter((group) => group.group_id === UNGROUPED_GROUP_ID),
  );

  return (
    <main className="sg-page">
      <div className="sg-meta-line">
        <Link href="/">stage-gen</Link> / prepared asset explorer
      </div>

      <div className="sg-header-strip">
        <div>
          <h1 className="sg-h1">{model.display_name}</h1>
          <div className="sg-meta-line">
            game: <span style={{ color: "var(--fg)" }}>{model.game_id}</span> · revision{" "}
            <span style={{ color: "var(--fg)" }}>{model.revision}</span>
          </div>
          <div className="sg-meta-line">
            tag: <span style={{ color: "var(--fg)" }}>{model.tag}</span>
          </div>
          <div className="sg-meta-line">
            status: <span style={{ color: "var(--accent)" }}>prepared</span> ·{" "}
            {model.artifact_count} closure artifacts · {assetCount} assets ·{" "}
            {provenanceCount} provenance
            {ungroupedCount > 0 ? (
              <>
                {" "}
                · <span style={{ color: "var(--error)" }}>{ungroupedCount} ungrouped</span>
              </>
            ) : null}
          </div>
          <div className="sg-meta-line" title={model.package_sha256}>
            package: <span style={{ color: "var(--fg)" }}>{model.package_sha256.slice(0, 16)}…</span>
          </div>
        </div>
        <Link className="sg-play is-active" href={`/preview/${model.tag}`}>
          [ preview ▸ ]
        </Link>
      </div>

      {model.groups.map((group) => {
        const audioOnly = group.assets.every((asset) =>
          asset.media_type.startsWith("audio/"),
        );
        const note = noteFor(group);
        return (
          <section key={group.group_id} aria-labelledby={`group-${group.group_id}`}>
            <div className="sg-section-h" id={`group-${group.group_id}`}>
              {group.label} · {group.assets.length}
            </div>
            {note ? <div className="sg-asset-path">{note}</div> : null}
            <div className={audioOnly ? "sg-audio-grid" : "sg-grid"}>
              {group.assets.map((asset: PreparedAssetCard) => {
                const url = preparedAssetUrl(model.tag, asset.path);
                if (asset.media_type.startsWith("audio/")) {
                  return (
                    <article className="sg-audio-card" key={asset.path}>
                      <div className="sg-asset-label">{asset.label}</div>
                      <audio controls preload="metadata" src={url}>
                        <a href={url}>download {asset.label}</a>
                      </audio>
                      <div className="sg-asset-path" title={asset.path}>
                        {asset.path}
                      </div>
                    </article>
                  );
                }
                if (!asset.media_type.startsWith("image/")) {
                  return (
                    <a
                      className="sg-slot"
                      key={asset.path}
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`open ${asset.path}`}
                    >
                      <div className="sg-slot-inner">
                        <span className="sg-slot-record">{"{ }"}</span>
                      </div>
                      <div className="sg-slot-label" title={asset.path}>
                        {asset.path.split("/").at(-1)} · {formatBytes(asset.bytes)}
                      </div>
                    </a>
                  );
                }
                return (
                  <button
                    type="button"
                    className="sg-slot is-active"
                    key={asset.path}
                    aria-label={`open ${asset.label}: ${asset.path}`}
                    onClick={() =>
                      setLightbox({
                        path: asset.path,
                        label: asset.label,
                        url,
                        transparent: asset.transparent,
                        width: asset.width,
                        height: asset.height,
                      })
                    }
                  >
                    <div className={`sg-slot-inner${asset.transparent ? " alpha-checker" : ""}`}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        className="sg-slot-img"
                        src={url}
                        alt={asset.label}
                        loading="lazy"
                      />
                    </div>
                    <div className="sg-slot-label" title={asset.path}>
                      {asset.label}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}

      {lightbox ? (
        <ImageLightbox asset={lightbox} onClose={() => setLightbox(null)} />
      ) : null}
    </main>
  );
}
