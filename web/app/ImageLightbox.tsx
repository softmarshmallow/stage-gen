"use client";

import { useEffect, useState } from "react";
import { button, cx } from "@/app/ui";

export type LightboxImage = Readonly<{
  path: string;
  label: string;
  url: string;
  transparent: boolean;
  width?: number;
  height?: number;
}>;

export default function ImageLightbox({
  asset,
  onClose,
}: {
  asset: LightboxImage;
  onClose: () => void;
}) {
  const [showAlpha, setShowAlpha] = useState(false);
  const [dimensions, setDimensions] = useState<{
    width?: number;
    height?: number;
  }>({ width: asset.width, height: asset.height });

  useEffect(() => {
    setShowAlpha(false);
    setDimensions({ width: asset.width, height: asset.height });
  }, [asset.height, asset.path, asset.width]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-black p-6"
      role="dialog"
      aria-modal="true"
      aria-label={asset.label}
      onClick={(event) => {
        // The caption strip is the one part of the overlay that is not a
        // dismiss target: it carries the alpha toggle.
        if ((event.target as HTMLElement).closest("[data-lightbox-meta]")) return;
        onClose();
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className={cx(
          "max-h-[calc(95vh-80px)] max-w-[95vw] object-contain",
          asset.transparent && showAlpha && "alpha-checker",
        )}
        src={asset.url}
        alt={asset.label}
        onLoad={(event) => {
          const image = event.currentTarget;
          setDimensions({ width: image.naturalWidth, height: image.naturalHeight });
        }}
      />
      <div
        className="mt-3 flex items-center gap-4 text-xs text-dim"
        data-lightbox-meta
      >
        <span>{asset.path}</span>
        {dimensions.width && dimensions.height ? (
          <span>
            {dimensions.width}×{dimensions.height}
          </span>
        ) : null}
        {asset.transparent ? (
          <button
            type="button"
            className={button}
            onClick={(event) => {
              event.stopPropagation();
              setShowAlpha((visible) => !visible);
            }}
          >
            [ {showAlpha ? "hide" : "show"} alpha ]
          </button>
        ) : null}
        <span>(esc to close)</span>
      </div>
    </div>
  );
}
