"""
Malbolge Translator - Generate pure Malbolge programs for arbitrary text.

A standalone tool for translating any text (including Unicode) into
executable Malbolge programs using anchor harness technology.
"""

from .translator import MalbolgeTranslator, TranslationResult, WordResult, RoundtripResult, RoundtripVerification
from .lexicon import Lexicon, transliterate, DEFAULT_LEXICON
try:
    from .anchor import AnchorManager, AnchorState, WordBank, BankEntry
except Exception:  # malbolge-generator not installed
    AnchorManager = AnchorState = WordBank = BankEntry = None  # type: ignore[assignment]
from .two_part_roundtrip import DEFAULT_MAX_PART_BYTES, run_two_part_roundtrip, split_utf8_halves
from .roundtrip import (
    CODEC_VERSION,
    RoundtripDecodeResult,
    RoundtripEnvelope,
    RoundtripStatus,
    decode_roundtrip,
    decode_roundtrip_detailed,
    encode_roundtrip,
    encode_roundtrip_envelope,
)

__version__ = "1.0.0"
__all__ = [
    "MalbolgeTranslator",
    "TranslationResult",
    "WordResult",
    "RoundtripResult",
    "RoundtripVerification",
    "DEFAULT_MAX_PART_BYTES",
    "run_two_part_roundtrip",
    "split_utf8_halves",
    "Lexicon",
    "transliterate",
    "DEFAULT_LEXICON",
    "AnchorManager",
    "AnchorState",
    "WordBank",
    "BankEntry",
    "CODEC_VERSION",
    "RoundtripEnvelope",
    "RoundtripDecodeResult",
    "RoundtripStatus",
    "encode_roundtrip",
    "encode_roundtrip_envelope",
    "decode_roundtrip",
    "decode_roundtrip_detailed",
]
