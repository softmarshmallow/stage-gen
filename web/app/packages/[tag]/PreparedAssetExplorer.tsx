"use client";

import Link from "next/link";
import { useState } from "react";
import { preparedAssetUrl } from "@/lib/runtime/prepared-manifest";
import type {
  PreparedAssetCard,
  PreparedAssetGroup,
} from "@/lib/shell/prepared-assets";
import ImageLightbox, { type LightboxImage } from "@/app/ImageLightbox";
import {
  assetGrid,
  assetPath,
  audioGrid,
  cx,
  h1,
  headerStrip,
  metaLine,
  page,
  playActive,
  playSize,
  sectionHeading,
  slot,
  slotIdle,
  slotImage,
  slotInner,
  slotLabel,
  slotPresent,
} from "@/app/ui";

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
    <main className={page}>
      <div className={metaLine}>
        <Link href="/">stage-gen</Link> / prepared asset explorer
      </div>

      <div className={headerStrip}>
        <div>
          <h1 className={h1}>{model.display_name}</h1>
          <div className={metaLine}>
            game: <span className="text-fg">{model.game_id}</span> · revision{" "}
            <span className="text-fg">{model.revision}</span>
          </div>
          <div className={metaLine}>
            tag: <span className="text-fg">{model.tag}</span>
          </div>
          <div className={metaLine}>
            status: <span className="text-accent">prepared</span> ·{" "}
            {model.artifact_count} closure artifacts · {assetCount} assets ·{" "}
            {provenanceCount} provenance
            {ungroupedCount > 0 ? (
              <>
                {" "}
                · <span className="text-error">{ungroupedCount} ungrouped</span>
              </>
            ) : null}
          </div>
          <div className={metaLine} title={model.package_sha256}>
            package:{" "}
            <span className="text-fg">
              {model.package_sha256.slice(0, 16)}…
            </span>
          </div>
        </div>
        <Link
          className={cx(playActive, playSize)}
          href={`/preview/${model.tag}`}
        >
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
            <div className={sectionHeading} id={`group-${group.group_id}`}>
              {group.label} · {group.assets.length}
            </div>
            {note ? <div className={assetPath}>{note}</div> : null}
            <div className={audioOnly ? audioGrid : assetGrid}>
              {group.assets.map((asset: PreparedAssetCard) => {
                const url = preparedAssetUrl(model.tag, asset.path);
                if (asset.media_type.startsWith("audio/")) {
                  return (
                    <article
                      className="min-w-0 border border-accent bg-bg p-2.5"
                      key={asset.path}
                    >
                      <div className="text-fg">{asset.label}</div>
                      <audio
                        className="my-2 block w-full"
                        controls
                        preload="metadata"
                        src={url}
                      >
                        <a href={url}>download {asset.label}</a>
                      </audio>
                      <div className={assetPath} title={asset.path}>
                        {asset.path}
                      </div>
                    </article>
                  );
                }
                if (!asset.media_type.startsWith("image/")) {
                  return (
                    <a
                      className={cx(slot, slotIdle)}
                      key={asset.path}
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`open ${asset.path}`}
                    >
                      <div className={cx(slotInner, "bg-well")}>
                        {/* A published record with nothing to render is shown
                            as a file, never as a broken image. */}
                        <span className="select-none text-lg text-dim">
                          {"{ }"}
                        </span>
                      </div>
                      <div className={slotLabel} title={asset.path}>
                        {asset.path.split("/").at(-1)} · {formatBytes(asset.bytes)}
                      </div>
                    </a>
                  );
                }
                return (
                  <button
                    type="button"
                    className={cx(slot, slotPresent)}
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
                    <div
                      className={cx(
                        slotInner,
                        asset.transparent ? "alpha-checker" : "bg-well",
                      )}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        className={slotImage}
                        src={url}
                        alt={asset.label}
                        loading="lazy"
                      />
                    </div>
                    <div className={slotLabel} title={asset.path}>
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
