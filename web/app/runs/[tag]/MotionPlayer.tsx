"use client";

// Frame-steps a uniform N x 1 motion strip with background-position — no
// pixel reads, no keyframes (forbidden by the design rule); a JS interval
// drives playback.

import { useEffect, useState } from "react";
import { button, cx } from "@/app/ui";

const DEFAULT_FRAMES_PER_SECOND = 6;

export default function MotionPlayer({
  url,
  frameCount,
  framesPerSecond,
  label,
}: {
  url: string;
  frameCount: number;
  framesPerSecond: number | null;
  label: string;
}) {
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null);

  useEffect(() => {
    if (!playing) return;
    const fps = framesPerSecond ?? DEFAULT_FRAMES_PER_SECOND;
    const timer = setInterval(() => {
      setFrame((current) => (current + 1) % frameCount);
    }, 1000 / fps);
    return () => clearInterval(timer);
  }, [playing, frameCount, framesPerSecond]);

  const step = (delta: number) =>
    setFrame((current) => (current + delta + frameCount) % frameCount);

  return (
    <div>
      <div
        className="alpha-checker w-full"
        role="img"
        aria-label={`${label} frame ${frame + 1} of ${frameCount}`}
        style={{
          aspectRatio: natural ? `${natural.width / frameCount} / ${natural.height}` : "1 / 1",
          backgroundImage: `url("${url}")`,
          backgroundRepeat: "no-repeat",
          backgroundSize: `${frameCount * 100}% 100%`,
          backgroundPosition:
            frameCount > 1 ? `${(frame / (frameCount - 1)) * 100}% 0%` : "0% 0%",
          imageRendering: "pixelated",
        }}
      />
      {/* Hidden probe: the strip's natural size fixes the frame aspect. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className="hidden"
        src={url}
        alt=""
        aria-hidden="true"
        onLoad={(event) => {
          const image = event.currentTarget;
          setNatural({ width: image.naturalWidth, height: image.naturalHeight });
        }}
      />
      <div className="mt-1.5 flex items-center gap-1.5 text-xs">
        <button type="button" className={cx(button, "px-2 py-0.5")} onClick={() => step(-1)}>
          ◀
        </button>
        <button
          type="button"
          className={cx(button, "px-2 py-0.5")}
          aria-pressed={playing}
          onClick={() => setPlaying((value) => !value)}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <button type="button" className={cx(button, "px-2 py-0.5")} onClick={() => step(1)}>
          ▶|
        </button>
        <span className="text-dim">
          {frame + 1}/{frameCount}
        </span>
      </div>
    </div>
  );
}
