"use client";

import { useEffect, useState } from "react";

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
      className="sg-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={asset.label}
      onClick={(event) => {
        if ((event.target as HTMLElement).closest(".sg-lightbox-meta")) return;
        onClose();
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className={`sg-lightbox-img${
          asset.transparent && showAlpha ? " alpha-checker" : ""
        }`}
        src={asset.url}
        alt={asset.label}
        onLoad={(event) => {
          const image = event.currentTarget;
          setDimensions({ width: image.naturalWidth, height: image.naturalHeight });
        }}
      />
      <div className="sg-lightbox-meta">
        <span>{asset.path}</span>
        {dimensions.width && dimensions.height ? (
          <span>
            {dimensions.width}×{dimensions.height}
          </span>
        ) : null}
        {asset.transparent ? (
          <button
            type="button"
            className="sg-btn"
            onClick={(event) => {
              event.stopPropagation();
              setShowAlpha((visible) => !visible);
            }}
          >
            [ {showAlpha ? "hide" : "show"} alpha ]
          </button>
        ) : null}
        <span style={{ color: "var(--dim)" }}>(esc to close)</span>
      </div>
    </div>
  );
}
