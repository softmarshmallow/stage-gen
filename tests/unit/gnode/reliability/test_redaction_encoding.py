from __future__ import annotations

import base64

import pytest

from gnode import (
    assert_media_type,
    decode_base64_strict,
    hash_input_reference,
    is_portable_artifact_reference,
    redact_secrets,
    sanitize_for_persistence,
    sanitize_reference,
    sha256_hex,
)


def test_redacts_explicit_credentials_headers_and_embedded_media() -> None:
    secret = "fal-key-private-value"
    payload = "A" * 80
    redacted = redact_secrets(
        f"authorization=Key {secret} api_key='{secret}' "
        f"data:image/png;base64,{payload} b64_json='{payload}'",
        (secret,),
    )
    assert secret not in redacted
    assert payload not in redacted
    assert "[REDACTED]" in redacted


def test_persistence_sanitizer_redacts_by_key_and_rejects_binary_values() -> None:
    value = sanitize_for_persistence(
        {"quality": "high", "apiKey": "secret", "nested": {"token": "secret"}}
    )
    assert value == {
        "quality": "high",
        "apiKey": "[REDACTED]",
        "nested": {"token": "[REDACTED]"},
    }
    with pytest.raises(TypeError, match="unsupported"):
        sanitize_for_persistence({"bytes": b"not-json"})


def test_strict_base64_and_media_type_validation() -> None:
    encoded = base64.b64encode(b"abc").decode()
    assert decode_base64_strict(encoded) == b"abc"
    for invalid in ("", "AAAAA", "not-base64", "____"):
        with pytest.raises(ValueError, match="base64"):
            decode_base64_strict(invalid)
    assert assert_media_type(" IMAGE/PNG ", "image") == "image/png"
    with pytest.raises(ValueError):
        assert_media_type("image/png; charset=binary", "image")


def test_reference_sanitization_and_content_hashing() -> None:
    encoded = base64.b64encode(b"abc").decode()
    reference = f"data:image/png;base64,{encoded}"
    hashed = hash_input_reference(reference, "inputs/reference.png")
    assert hashed.ref == "inputs/reference.png"
    assert hashed.sha256 == sha256_hex(b"abc")
    assert hashed.source == "content"
    assert hashed.bytes == 3
    assert sanitize_reference("https://user:pass@example.com/a.png?signature=x#fragment") == (
        "https://example.com/a.png"
    )
    assert sanitize_reference(reference) == "data:image/png;base64,[REDACTED]"


@pytest.mark.parametrize(
    ("reference", "portable"),
    [
        (f"sha256:{'a' * 64}", True),
        ("assets/music/source.mp3", True),
        ("https://example.com/source.mp3", True),
        ("/tmp/private/source.mp3", False),
        ("file:///private/source.mp3", False),
        ("data:audio/mpeg;base64,AAAA", False),
        ("https://user:password@example.com/source.mp3", False),
        ("https://example.com/source.mp3?signature=private", False),
        ("https://127.0.0.1/source.mp3", False),
        ("https://localhost./source.mp3", False),
        ("https://127.0.0.1./source.mp3", False),
        ("https://metadata.google.internal./source.mp3", False),
        ("https://2130706433/source.mp3", False),
        ("https://0x7f000001/source.mp3", False),
        ("https://127.1/source.mp3", False),
        ("https://example.com./source.mp3", True),
        ("https://example.com../source.mp3", False),
        ("https://example..com/source.mp3", False),
        ("../private/source.mp3", False),
        ("./a", False),
        ("a//b", False),
        ("a/", False),
        (".hidden/source.mp3", False),
    ],
)
def test_portable_artifact_references(reference: str, portable: bool) -> None:
    assert is_portable_artifact_reference(reference) is portable
