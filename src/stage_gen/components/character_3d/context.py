"""Deterministic image-history projection over the public tool-loop request."""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import replace

from gnode import ToolLoopStepRequest


def _image_digest(value: str) -> str:
    if not value.startswith("data:image/") or ";base64," not in value:
        raise ValueError("Archived tool images must be local base64 image data")
    try:
        data = base64.b64decode(value.split(";base64,", 1)[1], validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Archived tool image has invalid base64 data") from None
    return hashlib.sha256(data).hexdigest()


def project_image_history(
    request: ToolLoopStepRequest, recent_image_limit: int
) -> ToolLoopStepRequest:
    """Pin initial evidence and keep a suffix of complete subsequent image batches.

    The service retains its original conversation. Only the request handed to the
    provider is projected; this is not a second agent loop or a text summarizer.
    The first user message, including every reference image, is never modified.
    Tool replies, tool calls and all other text remain intact. The caller meters
    the resulting request and applies its ordinary total image and token limits.
    """
    if type(recent_image_limit) is not int or recent_image_limit < 1:
        raise ValueError("Recent image limit must be a positive integer")
    first_user = next(
        (index for index, message in enumerate(request.messages) if message.role == "user"), None
    )
    batches = [
        index
        for index, message in enumerate(request.messages)
        if message.images and index != first_user
    ]
    if not batches:
        return request
    if len(request.messages[batches[-1]].images) > recent_image_limit:
        raise ValueError("Newest tool image batch exceeds the recent image allowance")
    remaining = recent_image_limit
    keep = set()
    for index in reversed(batches):
        count = len(request.messages[index].images)
        if count > remaining:
            break
        keep.add(index)
        remaining -= count
    dropped = set(batches) - keep
    if not dropped:
        return request
    messages = list(request.messages)
    for index in sorted(dropped):
        message = request.messages[index]
        hashes = [_image_digest(value) for value in message.images]
        notice = (
            "[Archived tool image batch: "
            + str(len(hashes))
            + " image(s); decoded-image SHA-256 in original order: "
            + ", ".join(hashes)
            + (
                ". These images are omitted from this request's visual context."
                " Original tool replies and render artifacts remain available; "
                "request the relevant views again if needed.]"
            )
        )
        messages[index] = replace(message, text=message.text + "\n\n" + notice, images=())
    return replace(request, messages=tuple(messages))
