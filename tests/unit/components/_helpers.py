from __future__ import annotations

from io import BytesIO

from PIL import Image


def png_bytes(
    *,
    size: tuple[int, int] = (2, 2),
    color: tuple[int, int, int, int] = (10, 20, 30, 255),
) -> bytes:
    output = BytesIO()
    Image.new("RGBA", size, color).save(output, format="PNG")
    return output.getvalue()


def wav_bytes(payload_size: int = 8) -> bytes:
    payload = b"\x00" * payload_size
    size = 36 + len(payload)
    return (
        b"RIFF"
        + size.to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (8000).to_bytes(4, "little")
        + (16000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + len(payload).to_bytes(4, "little")
        + payload
    )
