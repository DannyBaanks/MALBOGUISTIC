"""Two-phase MALRT1 transport without per-chunk artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_MAX_PART_BYTES = 4096


def split_utf8_halves(text: str) -> tuple[str, str]:
    """Split at the nearest valid UTF-8 boundary at or before the byte midpoint."""
    data = text.encode("utf-8")
    midpoint = len(data) // 2
    while midpoint and data[midpoint] & 0xC0 == 0x80:
        midpoint -= 1
    return data[:midpoint].decode("utf-8"), data[midpoint:].decode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_two_part_roundtrip(
    text: str,
    output_dir: Path,
    translator,
    *,
    mode: str = "independent",
    max_part_bytes: int = DEFAULT_MAX_PART_BYTES,
    max_steps: int = 5_000_000,
) -> dict[str, Any]:
    """Run one of the bounded two-phase roundtrip modes.

    ``independent`` synthesizes and verifies one MALRT1 program for each
    continuous half. ``verify-first`` synthesizes the first half only; phase
    two reopens its persisted source and verification evidence. It deliberately
    makes no claim about transport of the second half.
    """
    if mode not in {"independent", "verify-first"}:
        raise ValueError("mode must be 'independent' or 'verify-first'")
    if max_part_bytes <= 0:
        raise ValueError("max_part_bytes must be > 0")

    first, second = split_utf8_halves(text)
    parts = [first, second]
    sizes = [len(part.encode("utf-8")) for part in parts]
    if max(sizes, default=0) > max_part_bytes:
        raise ValueError(
            f"refusing part of {max(sizes)} bytes (limit {max_part_bytes}); "
            "a two-part run still synthesizes one whole Malbolge program per part"
        )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "source.txt").write_text(text, encoding="utf-8")

    manifest: dict[str, Any] = {
        "schema": "malrt-two-part/1",
        "mode": mode,
        "source_bytes": len(text.encode("utf-8")),
        "source_sha256": _sha256(text.encode("utf-8")),
        "max_part_bytes": max_part_bytes,
        "parts": [],
    }

    first_dir = output_dir / "part_1"
    first_result = translator.translate_roundtrip(first)
    first_result.save_all(first_dir, "part_1")
    first_verification = translator.verify_roundtrip(first_result, max_steps=max_steps)
    (first_dir / "verification.json").write_text(
        json.dumps(first_verification.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest["parts"].append({
        "number": 1,
        "bytes": sizes[0],
        "sha256": _sha256(first.encode("utf-8")),
        "roundtrip_pass": first_verification.roundtrip_pass,
    })

    if mode == "independent":
        second_dir = output_dir / "part_2"
        second_result = translator.translate_roundtrip(second)
        second_result.save_all(second_dir, "part_2")
        second_verification = translator.verify_roundtrip(second_result, max_steps=max_steps)
        (second_dir / "verification.json").write_text(
            json.dumps(second_verification.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest["parts"].append({
            "number": 2,
            "bytes": sizes[1],
            "sha256": _sha256(second.encode("utf-8")),
            "roundtrip_pass": second_verification.roundtrip_pass,
        })
        manifest["whole_roundtrip_pass"] = (
            first_verification.roundtrip_pass and second_verification.roundtrip_pass
        )
    else:
        # Phase two only reads persisted proof for phase one, as requested.
        persisted = json.loads((first_dir / "verification.json").read_text(encoding="utf-8"))
        reread_first, _ = split_utf8_halves((output_dir / "source.txt").read_text(encoding="utf-8"))
        manifest["phase_2"] = {
            "action": "read_and_verify_part_1",
            "source_sha_match": _sha256(reread_first.encode("utf-8")) == manifest["parts"][0]["sha256"],
            "roundtrip_pass": persisted.get("roundtrip_pass") is True,
        }
        manifest["whole_roundtrip_pass"] = False
        manifest["claim"] = "PART_1_ROUNDTRIP_ONLY"

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
