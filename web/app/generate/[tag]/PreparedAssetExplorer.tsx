"use client";

import Link from "next/link";
import { useState } from "react";
import { preparedAssetUrl } from "@/lib/runtime/prepared-manifest";
import type { PreparedAssetGroup } from "@/lib/shell/prepared-assets";
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

export default function PreparedAssetExplorer({
  model,
}: {
  model: PreparedAssetExplorerModel;
}) {
  const [lightbox, setLightbox] = useState<LightboxImage | null>(null);

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
            {model.artifact_count} / {model.artifact_count} manifest-bound artifacts
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
        return (
          <section key={group.group_id} aria-labelledby={`group-${group.group_id}`}>
            <div className="sg-section-h" id={`group-${group.group_id}`}>
              {group.label} · {group.assets.length}
            </div>
            <div className={audioOnly ? "sg-audio-grid" : "sg-grid"}>
              {group.assets.map((asset) => {
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
