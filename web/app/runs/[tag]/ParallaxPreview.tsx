"use client";

import { useState } from "react";
import { parallaxOffset, type ParallaxPreview as ParallaxDocument } from "@/lib/run-viewer/artifact-preview";
import { preparedAssetUrl } from "@/lib/shell/asset-url";

/** Inspection of supplied layers, with camera offsets as a preview control. */
export default function ParallaxPreview({ tag, preview }: { tag: string; preview: ParallaxDocument }) {
  const [scrollX, setScrollX] = useState(0);
  const [scrollY, setScrollY] = useState(0);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  return (
    <div className="mt-1 space-y-2">
      <div className="alpha-checker relative w-full overflow-hidden border border-border" style={{ aspectRatio: `${preview.width}/${preview.height}`, containerType: "inline-size" }} role="img" aria-label="Supplied parallax layers">
        {preview.layers.filter((layer) => !hidden.has(layer.layerId)).map((layer) => {
          const [x, y] = parallaxOffset(layer, scrollX, scrollY);
          // Container width units preserve source-pixel geometry as the panel resizes.
          const unit = 100 / preview.width;
          return <div key={layer.layerId} className="absolute inset-0" style={{
            backgroundImage: `url("${preparedAssetUrl(tag, layer.assetRef)}")`,
            backgroundSize: `${layer.width * unit}cqw ${layer.height * unit}cqw`,
            backgroundPosition: `${x * unit}cqw ${y * unit}cqw`,
            backgroundRepeat: layer.repeatX ? (layer.repeatY ? "repeat" : "repeat-x") : (layer.repeatY ? "repeat-y" : "no-repeat"),
          }} />;
        })}
      </div>
      <label className="flex items-center gap-2 text-xs">Horizontal offset
        <input className="min-w-0 flex-1" type="range" min={-preview.width} max={preview.width} value={scrollX} onChange={(event) => setScrollX(Number(event.target.value))} />
        <output>{scrollX}</output>
      </label>
      <label className="flex items-center gap-2 text-xs">Vertical offset
        <input className="min-w-0 flex-1" type="range" min={-preview.height} max={preview.height} value={scrollY} onChange={(event) => setScrollY(Number(event.target.value))} />
        <output>{scrollY}</output>
      </label>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {preview.layers.map((layer) => <label key={layer.layerId} className="flex items-center gap-1">
          <input type="checkbox" checked={!hidden.has(layer.layerId)} onChange={() => setHidden((current) => {
            const next = new Set(current);
            if (next.has(layer.layerId)) next.delete(layer.layerId); else next.add(layer.layerId);
            return next;
          })} />
          {layer.layerId} · {layer.parallax}×
        </label>)}
      </div>
    </div>
  );
}
