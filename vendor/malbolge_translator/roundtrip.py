#!/usr/bin/env python3
"""
Reversible UTF-8 roundtrip codec over Malbolge transport.

    UTF-8 bytes -> reversible ASCII representation -> Malbolge program -> canonical execution -> ASCII payload -> UTF-8 bytes

This module is deliberately small, generic, and JS-portable.

No Malbolge-specific logic here; it only deals with Unicode <-> ASCII-safe envelope.
The envelope is:
    MALRT1:<base64(utf8_bytes)>:<sha256_hex>

Where:
- MALRT1 is version marker (ascii)
- base64 is standard RFC4648 base64 (A-Za-z0-9+/=), empty string allowed for empty input
- sha256_hex is 64 lower hex chars of SHA256(original_utf8_bytes)

Properties:
- deterministic
- ASCII-safe (33-126 + colon)
- versioned
- reversible
- malformed payloads rejected
- integrity checked (sha256)

Malbolge never natively handles Unicode; this codec only provides byte-exact transport.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Optional


CODEC_VERSION = "MALRT1"
PREFIX = CODEC_VERSION
# Allowed prefix set for version negotiation
SUPPORTED_VERSIONS = {CODEC_VERSION}


class RoundtripStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    CORRUPTED = "CORRUPTED"


@dataclass(frozen=True)
class RoundtripEnvelope:
    """Result of encoding."""
    original_text: str
    original_bytes: bytes
    original_sha256: str
    payload: str
    codec_version: str = CODEC_VERSION

    @property
    def payload_chars(self) -> int:
        return len(self.payload)

    @property
    def original_utf8_bytes_len(self) -> int:
        return len(self.original_bytes)


@dataclass(frozen=True)
class RoundtripDecodeResult:
    status: RoundtripStatus
    text: Optional[str] = None
    original_bytes: Optional[bytes] = None
    payload: Optional[str] = None
    sha256_expected: Optional[str] = None
    sha256_actual: Optional[str] = None
    error: Optional[str] = None
    codec_version: Optional[str] = None


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode_roundtrip(text: str) -> str:
    """Encode valid UTF-8 text to ASCII-safe envelope.

    Deterministic, versioned.
    """
    if not isinstance(text, str):
        raise TypeError("encode_roundtrip expects str")
    return encode_roundtrip_bytes(text.encode("utf-8")).payload  # type: ignore[no-untyped-call]


def encode_roundtrip_bytes(data: bytes) -> RoundtripEnvelope:
    """Encode raw bytes (interpreted as UTF-8 if caller later decodes)."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("encode_roundtrip_bytes expects bytes")
    b = bytes(data)
    # Validate that bytes are valid UTF-8 if the caller claims text mode
    # For generic bytes, we still encode bytes as-is; decoding will validate UTF-8.
    b64 = base64.b64encode(b).decode("ascii")
    sha = _sha256_hex(b)
    payload = f"{PREFIX}:{b64}:{sha}"
    # For envelope, original_text only if valid UTF-8
    try:
        orig_text = b.decode("utf-8")
    except UnicodeDecodeError:
        orig_text = ""
    return RoundtripEnvelope(
        original_text=orig_text,
        original_bytes=b,
        original_sha256=sha,
        payload=payload,
        codec_version=CODEC_VERSION,
    )


def encode_roundtrip_envelope(text: str) -> RoundtripEnvelope:
    """Return structured envelope for text."""
    if not isinstance(text, str):
        raise TypeError("encode_roundtrip_envelope expects str")
    b = text.encode("utf-8")
    b64 = base64.b64encode(b).decode("ascii")
    sha = _sha256_hex(b)
    payload = f"{PREFIX}:{b64}:{sha}"
    return RoundtripEnvelope(
        original_text=text,
        original_bytes=b,
        original_sha256=sha,
        payload=payload,
        codec_version=CODEC_VERSION,
    )


def decode_roundtrip(payload: str) -> str:
    """Decode envelope, raising on INVALID/CORRUPTED.

    No fallback to '?' – fails explicitly.
    """
    result = decode_roundtrip_detailed(payload)
    if result.status != RoundtripStatus.VALID:
        raise ValueError(f"roundtrip decode {result.status.value}: {result.error}")
    assert result.text is not None
    return result.text


def decode_roundtrip_detailed(payload: str) -> RoundtripDecodeResult:
    """Decode with explicit status VALID / INVALID / CORRUPTED."""
    if not isinstance(payload, str):
        return RoundtripDecodeResult(
            status=RoundtripStatus.INVALID,
            error="payload must be str",
            payload=str(payload) if payload is not None else None,
        )
    if not payload:
        return RoundtripDecodeResult(
            status=RoundtripStatus.INVALID,
            error="empty payload",
            payload=payload,
        )

    # Expect exactly 3 parts split by ":", with b64 possibly empty
    # payload structure: PREFIX:b64:sha
    # base64 never contains ":", sha never contains ":", so split safe
    parts = payload.split(":")
    if len(parts) != 3:
        return RoundtripDecodeResult(
            status=RoundtripStatus.INVALID,
            error=f"malformed envelope: expected 3 colon-separated parts, got {len(parts)}",
            payload=payload,
        )
    version, b64_part, sha_part = parts

    if version not in SUPPORTED_VERSIONS:
        return RoundtripDecodeResult(
            status=RoundtripStatus.INVALID,
            error=f"unknown codec version: {version!r}",
            payload=payload,
            codec_version=version,
        )

    # Validate sha part: must be 64 hex lower
    if len(sha_part) != 64 or any(c not in "0123456789abcdef" for c in sha_part.lower()):
        return RoundtripDecodeResult(
            status=RoundtripStatus.INVALID,
            error=f"invalid sha256 hex: {sha_part!r}",
            payload=payload,
            codec_version=version,
            sha256_expected=sha_part,
        )
    sha_expected = sha_part.lower()

    # Validate and decode b64
    # Allow empty b64 for empty input (payload "MALRT1::sha")
    try:
        # Use validate=True to reject non-base64 chars
        decoded_bytes = base64.b64decode(b64_part, validate=True) if b64_part else b""
    except Exception as e:
        return RoundtripDecodeResult(
            status=RoundtripStatus.INVALID,
            error=f"invalid base64: {e}",
            payload=payload,
            codec_version=version,
            sha256_expected=sha_expected,
        )

    # Integrity check
    sha_actual = _sha256_hex(decoded_bytes)
    if sha_actual != sha_expected:
        return RoundtripDecodeResult(
            status=RoundtripStatus.CORRUPTED,
            error=f"sha256 mismatch: expected {sha_expected} got {sha_actual}",
            payload=payload,
            codec_version=version,
            sha256_expected=sha_expected,
            sha256_actual=sha_actual,
            original_bytes=decoded_bytes,
        )

    # Validate UTF-8
    try:
        text = decoded_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        return RoundtripDecodeResult(
            status=RoundtripStatus.INVALID,
            error=f"decoded bytes not valid UTF-8: {e}",
            payload=payload,
            codec_version=version,
            sha256_expected=sha_expected,
            sha256_actual=sha_actual,
            original_bytes=decoded_bytes,
        )

    return RoundtripDecodeResult(
        status=RoundtripStatus.VALID,
        text=text,
        original_bytes=decoded_bytes,
        payload=payload,
        sha256_expected=sha_expected,
        sha256_actual=sha_actual,
        codec_version=version,
    )


def decode_roundtrip_bytes(payload: str) -> bytes:
    """Decode envelope returning raw bytes (after sha check)."""
    result = decode_roundtrip_detailed(payload)
    if result.status != RoundtripStatus.VALID:
        raise ValueError(f"roundtrip decode {result.status.value}: {result.error}")
    assert result.original_bytes is not None
    return result.original_bytes
