"""Derived pictures for the showcase, each bound to the run file it came from.

Every derived file lands in one ledger entry: output path, digest, size, source paths with their
digests, and the transform in words. The ledger is the basis for a later publication review.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageChops

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corner_colour(im: Image.Image) -> tuple[int, int, int] | None:
    """Mean corner colour when the four corners agree (a plain ground), else None."""
    rgb = im.convert("RGB")
    w, h = rgb.size
    corners = [rgb.getpixel(c) for c in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    mean = tuple(round(sum(c[i] for c in corners) / 4) for i in range(3))
    if any(abs(c[i] - mean[i]) > 10 for c in corners for i in range(3)):
        return None
    return mean  # type: ignore[return-value]


def hex_colour(rgb: tuple[int, int, int] | None) -> str | None:
    return None if rgb is None else f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def has_alpha(im: Image.Image) -> bool:
    return im.mode == "RGBA" and im.getextrema()[3][0] < 255


def video_frames(
    path: Path, times: list[float] | None = None, alpha: bool = False
) -> list[Image.Image]:
    """Decode frames with FFmpeg: every frame, or one frame at each given time in seconds."""
    fmt, mode = ("rgba", "RGBA") if alpha else ("rgb24", "RGB")

    def decode(before: list[str], after: list[str]) -> list[Image.Image]:
        raw = subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                *before,
                "-i",
                str(path),
                *after,
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "-pix_fmt",
                fmt,
                "-",
            ],
            capture_output=True,
            check=True,
        ).stdout
        starts, at = [], raw.find(PNG_SIGNATURE)
        while at >= 0:
            starts.append(at)
            at = raw.find(PNG_SIGNATURE, at + 1)
        # With no frame at all, ends still holds one entry; zip must then yield nothing.
        ends = [*starts[1:], len(raw)]
        return [
            Image.open(io.BytesIO(raw[s:e])).convert(mode)
            for s, e in zip(starts, ends, strict=False)
        ]

    if times is None:
        return decode([], [])
    return [decode(["-ss", f"{t:.3f}"], ["-frames:v", "1"])[0] for t in times]


class Media:
    def __init__(self, out: Path, run_root: Path, prefix: str = "media"):
        self.out = out
        self.run_root = run_root
        self.prefix = prefix
        self.ledger: list[dict] = []
        out.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def open_flat(path: Path, ground: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
        with Image.open(path) as im:
            im.load()
            if im.mode in ("RGBA", "LA", "P"):
                rgba = im.convert("RGBA")
                flat = Image.new("RGBA", rgba.size, (*ground, 255))
                flat.alpha_composite(rgba)
                return flat.convert("RGB")
            return im.convert("RGB")

    @staticmethod
    def subject_box(im: Image.Image, pad: float = 0.06) -> tuple[int, int, int, int] | None:
        """Box around pixels unlike a plain ground, with a margin; None without a plain ground."""
        ground = corner_colour(im)
        if ground is None:
            return None
        diff = ImageChops.difference(im.convert("RGB"), Image.new("RGB", im.size, ground))
        box = diff.convert("L").point(lambda v: 255 if v > 24 else 0).getbbox()
        if box is None:
            return None
        m = round(max(box[2] - box[0], box[3] - box[1]) * pad)
        w, h = im.size
        return (max(0, box[0] - m), max(0, box[1] - m), min(w, box[2] + m), min(h, box[3] + m))

    @staticmethod
    def pad_to(im: Image.Image, aspect: float) -> Image.Image:
        """Extend the canvas with its own ground to a width/height ratio; subject untouched."""
        fill = corner_colour(im) or (255, 255, 255)
        w, h = im.size
        size = (round(h * aspect), h) if w / h < aspect else (w, round(w / aspect))
        canvas = Image.new("RGB", size, fill)
        canvas.paste(im, ((size[0] - w) // 2, (size[1] - h) // 2))
        return canvas

    @staticmethod
    def fit(
        frames: list[Image.Image], box: tuple[int, int, int, int] | None, max_height: int
    ) -> list[Image.Image]:
        if box:
            frames = [f.crop(box) for f in frames]
        if frames[0].height > max_height:
            size = (round(frames[0].width * max_height / frames[0].height), max_height)
            frames = [f.resize(size, Image.LANCZOS) for f in frames]
        return frames

    def _record(self, name: str, sources: list[Path], transform: str, alpha: bool = False) -> dict:
        target = self.out / name
        with Image.open(target) as im:
            width, height = im.size
            ground = None if alpha else corner_colour(im.convert("RGB"))
        self.ledger.append(
            {
                "file": f"{self.prefix}/{name}",
                "sha256": sha256(target),
                "bytes": target.stat().st_size,
                "size": [width, height],
                "sources": [{"path": self._source_ref(p), "sha256": sha256(p)} for p in sources],
                "transform": transform,
            }
        )
        return {
            "src": f"{self.prefix}/{name}",
            "width": width,
            "height": height,
            "bg": "transparent" if alpha else (hex_colour(ground) or "#ffffff"),
            "alpha": alpha,
        }

    def _source_ref(self, path: Path) -> str:
        path = path.resolve()
        return (
            str(path.relative_to(self.run_root))
            if path.is_relative_to(self.run_root)
            else path.name
        )

    def _save(
        self, frames: list[Image.Image], name: str, durations: list[int] | int, quality: int
    ) -> None:
        if len(frames) == 1:
            frames[0].save(self.out / name, "WEBP", quality=quality, method=6)
        else:
            frames[0].save(
                self.out / name,
                "WEBP",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=0,
                quality=quality,
                method=4,
            )

    # ---------------------------------------------------------------- products

    def still(self, name: str, source: Path, max_height: int, crop: bool = False) -> dict:
        im = self.open_flat(source)
        if crop and (box := self.subject_box(im)):
            im = im.crop(box)
        self._save(self.fit([im], None, max_height), name, 0, 84)
        steps = ["cropped to subject" if crop else "", f"at most {max_height} px high", "WebP q84"]
        return self._record(name, [source], ", ".join(s for s in steps if s))

    def still_alpha(self, name: str, source: Path, max_height: int = 480) -> dict:
        """Like still(), but keeps transparency instead of flattening it."""
        with Image.open(source) as im:
            return self.image(name, im.convert("RGBA"), [source], "transparency kept", max_height)

    def image(
        self,
        name: str,
        im: Image.Image,
        sources: list[Path],
        transform: str,
        max_height: int = 480,
        box: tuple[int, int, int, int] | None = None,
    ) -> dict:
        """A picture derived in memory, such as a decoded video frame or an annotated source."""
        alpha = has_alpha(im)
        self._save(self.fit([im if alpha else im.convert("RGB")], box, max_height), name, 0, 84)
        return self._record(
            name, sources, f"{transform}, at most {max_height} px high, WebP q84", alpha
        )

    def png(self, name: str, im: Image.Image, sources: list[Path], transform: str) -> dict:
        """An exact, lossless picture, for pixels a page lays out by measurement.

        Nine-slice cells and sprite cells are laid out this way.
        """
        im.save(self.out / name, "PNG", optimize=True)
        return self._record(name, sources, f"{transform}, lossless PNG", has_alpha(im))

    def sequence(
        self,
        name: str,
        frames: list[Image.Image],
        durations: list[int] | int,
        sources: list[Path],
        transform: str,
        max_height: int = 480,
        box: tuple[int, int, int, int] | None = None,
        quality: int = 78,
    ) -> dict:
        """An animated WebP from frames in memory; transparency is kept when the frames carry it."""
        alpha = has_alpha(frames[0])
        frames = self.fit([f if alpha else f.convert("RGB") for f in frames], box, max_height)
        self._save(frames, name, durations, quality)
        return self._record(
            name,
            sources,
            f"{transform}, {len(frames)} frames, at most {max_height} px high, "
            f"animated WebP q{quality}",
            alpha,
        )

    def cycle(
        self, name: str, sources: list[Path], height: int, ms: int, aspect: float | None = None
    ) -> dict:
        frames = [self.open_flat(p) for p in sources]
        boxes = [self.subject_box(f) for f in frames]
        if boxes and all(boxes):
            union = (
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            )
            frames = [f.crop(union) for f in frames]
        if aspect:
            frames = [self.pad_to(f, aspect) for f in frames]
        width = round(frames[0].width * height / frames[0].height)
        self._save([f.resize((width, height), Image.LANCZOS) for f in frames], name, ms, 84)
        return self._record(
            name,
            sources,
            f"{len(frames)} frames at {ms} ms, cropped to the subject of all frames, "
            f"{'padded, ' if aspect else ''}{height} px, animated WebP q84",
        )

    def copy(self, name: str, source: Path, note: str) -> dict:
        shutil.copyfile(source, self.out / name)
        self.ledger.append(
            {
                "file": f"{self.prefix}/{name}",
                "sha256": sha256(source),
                "bytes": source.stat().st_size,
                "sources": [{"path": self._source_ref(source), "sha256": sha256(source)}],
                "transform": f"byte copy; {note}",
            }
        )
        return {"src": f"{self.prefix}/{name}", "bytes": source.stat().st_size}
