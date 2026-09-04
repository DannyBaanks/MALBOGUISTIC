#!/usr/bin/env python3
"""
Malbolge Translator - Uses the original malbolge-generator directly.

This is a clean, working implementation that uses the proven
malbolge-generator library directly instead of a buggy custom backend.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    from malbolge import (
        GenerationConfig,
        MalbolgeInterpreter,
        MalbolgeMachine,
        MalbolgeRuntimeError,
        ProgramGenerator,
    )
    from malbolge.encoding import reverse_normalize
    _MALBOLGE_AVAILABLE = True
except Exception as _e:
    # Fallback stub when malbolge-generator not installed (e.g. CI).
    # Codec roundtrip can still be tested; synthesis will report FAIL explicitly.
    _MALBOLGE_AVAILABLE = False
    GenerationConfig = object  # type: ignore[assignment,misc]
    MalbolgeInterpreter = object  # type: ignore[assignment,misc]
    MalbolgeMachine = object  # type: ignore[assignment,misc]
    class MalbolgeRuntimeError(RuntimeError):  # type: ignore[no-redef]
        pass
    ProgramGenerator = object  # type: ignore[assignment,misc]
    def reverse_normalize(x):  # type: ignore[no-redef]
        return x

from .lexicon import Lexicon, DEFAULT_LEXICON, transliterate

from .roundtrip import (
    CODEC_VERSION,
    RoundtripDecodeResult,
    RoundtripEnvelope,
    RoundtripStatus,
    decode_roundtrip_detailed,
    encode_roundtrip_envelope,
)


@dataclass
class WordResult:
    index: int
    word: str
    opcodes: str
    machine_output: str
    anchor_name: str = "default"
    from_bank: bool = False
    success: bool = True
    error: Optional[str] = None


@dataclass
class TranslationResult:
    original_text: str
    processed_text: str
    words: List[WordResult]
    full_opcodes: str
    full_program: str
    stats: dict
    anchors_used: List[str]

    def save_all(self, output_dir: Path, base_name: str = "output") -> None:
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, w in enumerate(self.words):
            (output_dir / f"{base_name}_word_{i:04d}.op").write_text(w.opcodes, encoding="utf-8")
            (output_dir / f"{base_name}_word_{i:04d}.json").write_text(
                json.dumps({
                    "index": w.index, "word": w.word, "opcodes": w.opcodes,
                    "anchor": w.anchor_name, "from_bank": w.from_bank, "success": w.success
                }, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        (output_dir / f"{base_name}_full.op").write_text(self.full_opcodes, encoding="utf-8")
        (output_dir / f"{base_name}_full.mal").write_text(self.full_program, encoding="utf-8")
        (output_dir / f"{base_name}_manifest.json").write_text(json.dumps({
            "schema_version": 1,
            "mode": "transliteration",
            "original": self.original_text, "processed": self.processed_text,
            "words": len(self.words), "anchors": self.anchors_used,
            "opcodes": len(self.full_opcodes), "stats": self.stats
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Saved to {output_dir}")


# ============================================================
# ROUNDTRIP MODE — byte-exact UTF-8 transport over Malbolge
# ============================================================

@dataclass
class RoundtripResult:
    """Result of UTF-8 roundtrip synthesis (before execution)."""
    original_text: str
    original_bytes: bytes
    original_sha256: str
    encoded_payload: str
    codec_version: str
    # Malbolge synthesis of the ASCII-safe payload
    translation: TranslationResult
    # derived
    payload_sha256: str = field(init=False)
    malbolge_program_chars: int = field(init=False)
    malbolge_opcodes: int = field(init=False)

    def __post_init__(self) -> None:
        self.payload_sha256 = hashlib.sha256(self.encoded_payload.encode("utf-8")).hexdigest()
        self.malbolge_program_chars = len(self.translation.full_program)
        self.malbolge_opcodes = len(self.translation.full_opcodes)

    @property
    def success(self) -> bool:
        # synthesis success = we have opcodes and no error in word
        return bool(self.translation.full_opcodes) and all(w.success for w in self.translation.words)

    def save_all(self, output_dir: Path, base_name: str = "roundtrip") -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        # reuse TranslationResult saving for opcodes/program
        self.translation.save_all(output_dir, base_name)
        # Overwrite manifest with roundtrip metadata (versioned, additive)
        manifest_path = output_dir / f"{base_name}_manifest.json"
        base_manifest = {}
        if manifest_path.exists():
            try:
                base_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                base_manifest = {}
        manifest = {
            "schema_version": 2,
            "mode": "utf8-roundtrip",
            "codec_version": self.codec_version,
            "original_text_preview": self.original_text[:200],
            "original_utf8_bytes": len(self.original_bytes),
            "original_sha256": self.original_sha256,
            "encoded_payload": self.encoded_payload,
            "encoded_payload_chars": len(self.encoded_payload),
            "payload_sha256": self.payload_sha256,
            "malbolge_program_chars": self.malbolge_program_chars,
            "malbolge_opcodes": self.malbolge_opcodes,
            "translation_stats": self.translation.stats,
            "original": self.original_text,
            "processed": self.translation.processed_text,
            "words": len(self.translation.words),
            "anchors": self.translation.anchors_used,
            "opcodes": len(self.translation.full_opcodes),
        }
        # keep transliteration manifest fields for compatibility where not conflicting
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Roundtrip saved to {output_dir}")


@dataclass
class RoundtripVerification:
    """Structured evidence for a roundtrip verification."""
    mode: str = "utf8-roundtrip"
    codec_version: str = CODEC_VERSION
    original_text: str = ""
    recovered_text: Optional[str] = None
    original_utf8_sha256: str = ""
    recovered_utf8_sha256: Optional[str] = None
    original_utf8_bytes: int = 0
    recovered_utf8_bytes: Optional[int] = None
    bytes_equal: Optional[bool] = None
    text_equal: Optional[bool] = None
    sha_equal: Optional[bool] = None
    encoded_payload: str = ""
    encoded_payload_chars: int = 0
    payload_sha256: str = ""
    recovered_payload: Optional[str] = None
    payload_match: Optional[bool] = None
    malbolge_execution_status: str = ""
    malbolge_steps: Optional[int] = None
    malbolge_program_chars: int = 0
    malbolge_opcodes: int = 0
    # classification
    codec_roundtrip: str = "UNKNOWN"  # PASS / FAIL
    malbolge_synthesis: str = "UNKNOWN"  # PASS / TIMEOUT / FAIL
    end_to_end_roundtrip: str = "NOT_DEMONSTRATED"  # PASS / NOT_DEMONSTRATED
    # overall
    roundtrip_pass: bool = False
    error: Optional[str] = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "codec_version": self.codec_version,
            "original_text_preview": self.original_text[:200],
            "original_utf8_bytes": self.original_utf8_bytes,
            "original_utf8_sha256": self.original_utf8_sha256,
            "recovered_text_preview": (self.recovered_text[:200] if self.recovered_text else None),
            "recovered_utf8_bytes": self.recovered_utf8_bytes,
            "recovered_utf8_sha256": self.recovered_utf8_sha256,
            "bytes_equal": self.bytes_equal,
            "text_equal": self.text_equal,
            "sha_equal": self.sha_equal,
            "encoded_payload": self.encoded_payload,
            "encoded_payload_chars": self.encoded_payload_chars,
            "payload_sha256": self.payload_sha256,
            "recovered_payload_preview": (self.recovered_payload[:200] if self.recovered_payload else None),
            "payload_match": self.payload_match,
            "malbolge_execution_status": self.malbolge_execution_status,
            "malbolge_steps": self.malbolge_steps,
            "malbolge_program_chars": self.malbolge_program_chars,
            "malbolge_opcodes": self.malbolge_opcodes,
            "codec_roundtrip": self.codec_roundtrip,
            "malbolge_synthesis": self.malbolge_synthesis,
            "end_to_end_roundtrip": self.end_to_end_roundtrip,
            "roundtrip_pass": self.roundtrip_pass,
            "error": self.error,
            "details": self.details,
        }


class MalbolgeTranslator:
    """
    Translates arbitrary text to pure Malbolge programs.
    
    Uses the proven malbolge-generator library directly.
    """

    def __init__(
        self,
        max_search_depth: int = 5,
        random_seed: int = 42,
        cache_dir: Optional[Path] = None,
        lexicon: Optional[Lexicon] = None,
    ):
        if _MALBOLGE_AVAILABLE:
            self.generator = ProgramGenerator()  # type: ignore[operator]
            self.interpreter = MalbolgeInterpreter()  # type: ignore[operator]
            self.config = GenerationConfig(  # type: ignore[operator]
                opcode_choices="op*",
                max_search_depth=max_search_depth,
                random_seed=random_seed,
            )
        else:
            self.generator = None  # type: ignore[assignment]
            self.interpreter = None  # type: ignore[assignment]
            self.config = None  # type: ignore[assignment]
        self.lexicon = lexicon or Lexicon()
        self.max_search_depth = max_search_depth
        self.random_seed = random_seed

    def translate(
        self,
        text: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> "TranslationResult":
        """Translate text to Malbolge opcodes."""
        # 1. Transliterate Unicode to ASCII
        processed = transliterate(text, self.lexicon)

        # 2. Generate the entire text at once (generator handles it efficiently)
        if progress_callback:
            progress_callback(0, 1, processed)

        if not _MALBOLGE_AVAILABLE or self.generator is None:
            return TranslationResult(
                original_text=text,
                processed_text=processed,
                words=[WordResult(0, processed, "", "", "default", False, False, "malbolge-generator not installed; synthesis requires malbolge-generator")],
                full_opcodes="",
                full_program="",
                stats={"words": 1, "evaluations": 0, "duration_s": 0, "anchors_used": 1, "error": "malbolge-generator not installed"},
                anchors_used=["default"],
            )
        
        try:
            result = self.generator.generate_for_string(processed)
            cont = result.opcodes
            machine_output = result.machine_output
            stats = result.stats
        except Exception as e:
            return TranslationResult(
                original_text=text,
                processed_text=processed,
                words=[WordResult(0, processed, "", "", "default", False, str(e))],
                full_opcodes="",
                full_program="",
                stats={"words": 1, "evaluations": 0, "duration_s": 0, "anchors_used": 1},
                anchors_used=["default"],
            )

        if progress_callback:
            progress_callback(1, 1, processed)

        word_result = WordResult(0, processed, cont, machine_output, "default", False)
        full_program = "".join(reverse_normalize(cont))

        return TranslationResult(
            original_text=text,
            processed_text=processed,
            words=[word_result],
            full_opcodes=cont,
            full_program=full_program,
            stats={
                "words": 1,
                "evaluations": stats.get("evaluations", 0),
                "duration_s": stats.get("duration_ns", 0) / 1e9,
                "anchors_used": 1,
            },
            anchors_used=["default"],
        )

    def execute(self, result: "TranslationResult", max_steps: int = 5_000_000) -> str:
        """Execute the generated program and verify output against both processed and original text."""
        if not _MALBOLGE_AVAILABLE or self.interpreter is None:
            print("[WARN] Malbolge interpreter not available (malbolge-generator not installed)")
            print("[WARN] Execution verification requires malbolge-generator; returning empty")
            return ""
        out = self.interpreter.execute(result.full_opcodes, max_steps=max_steps, capture_machine=True)
        processed_match = out.output == result.processed_text
        original_match = out.output == result.original_text
        print(f"Output: {repr(out.output)}")
        print(f"Steps: {out.steps}, Halt: {out.halt_reason}")
        print(f"Processed match: {processed_match}")
        print(f"Original match: {original_match}")
        if not processed_match and not original_match:
            print(f"Expected (processed): {repr(result.processed_text)}")
            print(f"Expected (original): {repr(result.original_text)}")
        return out.output

    # --------------------------------------------------
    # ROUNDTRIP API — byte-exact UTF-8 transport
    # --------------------------------------------------

    def translate_roundtrip(
        self,
        text: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> RoundtripResult:
        """Synthesize pure Malbolge program for reversible UTF-8 roundtrip.

        Steps:
            text (UTF-8) -> encode_roundtrip -> ASCII payload -> Malbolge generation
        No transliteration is applied; original bytes are preserved exactly.
        Fails explicitly when generation budget exhausted (no fallback to '?').
        """
        if not isinstance(text, str):
            raise TypeError("translate_roundtrip expects str")
        envelope = encode_roundtrip_envelope(text)
        payload = envelope.payload

        # Generate Malbolge for payload directly, bypassing lexicon
        if progress_callback:
            progress_callback(0, 1, payload)

        if not _MALBOLGE_AVAILABLE or self.generator is None:
            return RoundtripResult(
                original_text=text,
                original_bytes=envelope.original_bytes,
                original_sha256=envelope.original_sha256,
                encoded_payload=payload,
                codec_version=CODEC_VERSION,
                translation=TranslationResult(
                    original_text=text,
                    processed_text=payload,
                    words=[WordResult(0, payload, "", "", "default", False, False, "malbolge-generator not installed; synthesis requires malbolge-generator")],
                    full_opcodes="",
                    full_program="",
                    stats={"words": 1, "evaluations": 0, "duration_s": 0, "anchors_used": 1, "error": "malbolge-generator not installed"},
                    anchors_used=["default"],
                ),
            )

        try:
            gen_result = self.generator.generate_for_string(payload)
            cont = gen_result.opcodes
            machine_output = gen_result.machine_output
            stats = gen_result.stats
        except Exception as e:
            # Explicit fail, no fake fallback
            err = str(e)
            return RoundtripResult(
                original_text=text,
                original_bytes=envelope.original_bytes,
                original_sha256=envelope.original_sha256,
                encoded_payload=payload,
                codec_version=CODEC_VERSION,
                translation=TranslationResult(
                    original_text=text,
                    processed_text=payload,
                    words=[WordResult(0, payload, "", "", "default", False, False, err)],
                    full_opcodes="",
                    full_program="",
                    stats={"words": 1, "evaluations": 0, "duration_s": 0, "anchors_used": 1, "error": err},
                    anchors_used=["default"],
                ),
            )

        if progress_callback:
            progress_callback(1, 1, payload)

        word_result = WordResult(0, payload, cont, machine_output, "default", False, True, None)
        if machine_output != payload:
            # Generator claimed success but output mismatch – treat as failure
            word_result = WordResult(0, payload, cont, machine_output, "default", False, False, f"generator output mismatch: {repr(machine_output)} != {repr(payload)}")
        full_program = "".join(reverse_normalize(cont)) if cont else ""

        trans = TranslationResult(
            original_text=text,
            processed_text=payload,
            words=[word_result],
            full_opcodes=cont,
            full_program=full_program,
            stats={
                "words": 1,
                "evaluations": stats.get("evaluations", 0),
                "duration_s": stats.get("duration_ns", 0) / 1e9,
                "anchors_used": 1,
            },
            anchors_used=["default"],
        )
        return RoundtripResult(
            original_text=text,
            original_bytes=envelope.original_bytes,
            original_sha256=envelope.original_sha256,
            encoded_payload=payload,
            codec_version=CODEC_VERSION,
            translation=trans,
        )

    def verify_roundtrip(
        self,
        result: RoundtripResult,
        max_steps: int = 5_000_000,
    ) -> RoundtripVerification:
        """Execute Malbolge program and verify byte-exact roundtrip.

        Returns structured evidence; never silently invents '?' for failed Unicode.
        Classification:
            CODEC_ROUNDTRIP = PASS if encode->decode without Malbolge works
            MALBOLGE_SYNTHESIS = PASS / TIMEOUT / FAIL
            END_TO_END_ROUNDTRIP = PASS only if payload'==payload and bytes equal and sha equal
        """
        ver = RoundtripVerification(
            original_text=result.original_text,
            original_utf8_sha256=result.original_sha256,
            original_utf8_bytes=len(result.original_bytes),
            encoded_payload=result.encoded_payload,
            encoded_payload_chars=len(result.encoded_payload),
            payload_sha256=result.payload_sha256,
            malbolge_program_chars=result.malbolge_program_chars,
            malbolge_opcodes=result.malbolge_opcodes,
        )

        # 1. Codec self-check (without Malbolge)
        try:
            decoded_self = decode_roundtrip_detailed(result.encoded_payload)
            if decoded_self.status == RoundtripStatus.VALID and decoded_self.text == result.original_text:
                ver.codec_roundtrip = "PASS"
            else:
                ver.codec_roundtrip = "FAIL"
                ver.error = f"codec self-check failed: {decoded_self.status.value}: {decoded_self.error}"
        except Exception as e:
            ver.codec_roundtrip = "FAIL"
            ver.error = f"codec self-check exception: {e}"

        # 2. Malbolge synthesis check
        if not result.translation.full_opcodes:
            ver.malbolge_synthesis = "FAIL"
            if not ver.error:
                ver.error = result.translation.words[0].error or "synthesis failed: no opcodes"
        elif result.translation.words and not result.translation.words[0].success:
            ver.malbolge_synthesis = "FAIL"
            ver.error = result.translation.words[0].error
        else:
            # synthesis produced opcodes; check if its internal machine_output matches payload
            # The generator already guarantees output == payload if success, but double-check
            w = result.translation.words[0]
            if w.machine_output == result.encoded_payload:
                ver.malbolge_synthesis = "PASS"
            else:
                ver.malbolge_synthesis = "FAIL"
                ver.error = f"synthesis output mismatch: {repr(w.machine_output)} != payload"

        # 3. Execution
        if not result.translation.full_opcodes:
            ver.malbolge_execution_status = "NOT_EXECUTED"
            ver.end_to_end_roundtrip = "NOT_DEMONSTRATED"
            ver.roundtrip_pass = False
            return ver

        if not _MALBOLGE_AVAILABLE or self.interpreter is None:
            ver.malbolge_execution_status = "NOT_EXECUTED: malbolge-generator not installed"
            ver.error = (ver.error + "; " if ver.error else "") + "interpreter not available; install malbolge-generator to verify execution"
            ver.end_to_end_roundtrip = "NOT_DEMONSTRATED"
            ver.roundtrip_pass = False
            return ver

        try:
            out = self.interpreter.execute(result.translation.full_opcodes, max_steps=max_steps, capture_machine=True)
            ver.malbolge_steps = out.steps
            ver.malbolge_execution_status = getattr(out, "halt_reason", "HALTED")
            recovered_payload = out.output
            ver.recovered_payload = recovered_payload
            ver.payload_match = (recovered_payload == result.encoded_payload)

            # Decode recovered payload
            dec = decode_roundtrip_detailed(recovered_payload)
            if dec.status == RoundtripStatus.VALID:
                ver.recovered_text = dec.text
                assert dec.original_bytes is not None
                ver.recovered_utf8_bytes = len(dec.original_bytes)
                ver.recovered_utf8_sha256 = dec.sha256_actual
                ver.bytes_equal = (dec.original_bytes == result.original_bytes)
                ver.text_equal = (dec.text == result.original_text)
                ver.sha_equal = (dec.sha256_actual == result.original_sha256)
            else:
                # Corrupted/Invalid -> explicit failure, no invented text
                ver.recovered_text = None
                ver.recovered_utf8_bytes = None
                ver.recovered_utf8_sha256 = dec.sha256_actual
                ver.bytes_equal = False
                ver.text_equal = False
                ver.sha_equal = False
                if dec.status == RoundtripStatus.CORRUPTED:
                    ver.error = (ver.error + "; " if ver.error else "") + f"recovered payload corrupted: {dec.error}"
                else:
                    ver.error = (ver.error + "; " if ver.error else "") + f"recovered payload invalid: {dec.error}"
                ver.details["decode_status"] = dec.status.value
                ver.details["decode_error"] = dec.error

        except Exception as e:
            ver.malbolge_execution_status = f"ERROR: {e}"
            ver.payload_match = False
            ver.error = (ver.error + "; " if ver.error else "") + f"execution exception: {e}"
            ver.end_to_end_roundtrip = "NOT_DEMONSTRATED"
            ver.roundtrip_pass = False
            return ver

        # 4. End-to-end verdict
        if (
            ver.codec_roundtrip == "PASS"
            and ver.malbolge_synthesis == "PASS"
            and ver.payload_match is True
            and ver.bytes_equal is True
            and ver.text_equal is True
            and ver.sha_equal is True
            and ver.malbolge_execution_status in ("HALTED", "halted", "Halted", "STOP", "halt")
        ):
            ver.end_to_end_roundtrip = "PASS"
            ver.roundtrip_pass = True
        else:
            # Normalize halt check: malbolge interpreter returns "HALTED" on 'v'
            # Be permissive: any halt_reason containing halt is pass for synthesis but end-to-end requires exact match as above
            if ver.malbolge_execution_status and "HALT" in ver.malbolge_execution_status.upper():
                # If all byte checks pass except halt naming, still PASS
                if ver.payload_match and ver.bytes_equal and ver.sha_equal:
                    ver.end_to_end_roundtrip = "PASS"
                    ver.roundtrip_pass = True
                else:
                    ver.end_to_end_roundtrip = "NOT_DEMONSTRATED"
                    ver.roundtrip_pass = False
            else:
                ver.end_to_end_roundtrip = "NOT_DEMONSTRATED"
                ver.roundtrip_pass = False

        return ver

    def translate_and_verify_roundtrip(
        self,
        text: str,
        max_steps: int = 5_000_000,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> tuple[RoundtripResult, RoundtripVerification]:
        """Convenience: synthesize + execute + verify in one call."""
        result = self.translate_roundtrip(text, progress_callback=progress_callback)
        ver = self.verify_roundtrip(result, max_steps=max_steps)
        return result, ver

    def save_cache(self) -> None:
        print("[Cache] No cache to save in simplified mode")


# ============================================================
# COMMON WORD LISTS FOR PRE-POPULATION
# ============================================================

SPANISH_COMMON = [
    "el","la","de","que","y","en","un","a","se","no","te","lo","le","da","su","por","son","con","para","al",
    "del","los","las","una","uno","sus","les","me","mi","tu","es","ha","he","si","ya","va","ve","muy","más",
    "como","pero","sus","está","esta","esté","están","estás","estoy","somos","sois","son","era","eras","eran",
    "fue","fueron","será","serán","haber","había","hacer","hace","hecho","hacen","hacía","hagan","decir","dice",
    "dicho","dicen","dijo","decía","digan","ver","veo","visto","ven","vio","veía","verán","saber","sé","sabe",
    "sabes","sabemos","sabía","sabrán","querer","quiero","quiere","quería","quisiera","quieren","poder","puedo",
    "puede","puedes","podemos","podía","podrán","tener","tengo","tiene","tienes","tenemos","tenía","tendrán",
    "ir","voy","va","vas","vamos","iba","irán","fui","fue","venir","vengo","vienes","viene","venimos","venía",
    "vendrán","dar","doy","da","das","damos","daba","darán","di","dio","estar","estoy","estás","está","estamos",
    "estaba","estarán","llegar","llego","llega","llegas","llegamos","llegaba","llegarán","pasar","paso","pasa",
    "pasas","pasamos","pasaba","pasarán","deber","debo","debe","debes","debemos","debía","deberán","poner","pongo",
    "pone","pones","ponemos","ponía","pondrán","parecer","parezco","parece","pareces","parecemos","parecía",
    "parecerán","quedar","quedo","queda","quedas","quedamos","quedaba","quedarán","creer","creo","cree","crees",
    "creemos","creía","creerán","hablar","hablo","habla","hablas","hablamos","hablaba","hablarán","llevar","llevo",
    "lleva","llevas","llevamos","llevaba","llevarán","dejar","dejo","deja","dejas","dejamos","dejaba","dejarán",
    "seguir","sigo","sigue","sigues","seguimos","seguía","seguirán","encontrar","encuentro","encuentra",
    "encuentras","encontramos","encontraba","encontrarán","llamar","llamo","llama","llamas","llamamos","llamaba",
    "llamarán","venir","vengo","vienes","viene","venimos","venía","vendrán","pensar","pienso","piensa","piensas",
    "pensamos","pensaba","pensarán","salir","salgo","sale","sales","salimos","salía","saldrán","volver","vuelvo",
    "vuelve","vuelves","volvemos","volvía","volverán","tomar","tomo","toma","tomas","tomamos","tomaba","tomarán",
    "conocer","conozco","conoce","conoces","conocemos","conocía","conocerán","vivir","vivo","vive","vives",
    "vivimos","vivía","vivirán","sentir","siento","siente","sientes","sentimos","sentía","sentirán","tratar",
    "trato","trata","tratas","tratamos","trataba","tratarán","mirar","miro","mira","miras","miramos","miraba",
    "mirarán","contar","cuento","cuenta","cuentas","contamos","contaba","contarán","empezar","empiezo","empieza",
    "empiezas","empezamos","empezaba","empezarán","esperar","espero","espera","esperas","esperamos","esperaba",
    "esperarán","buscar","busco","busca","buscas","buscamos","buscaba","buscarán","existir","existo","existe",
    "existes","existimos","existía","existirán","entrar","entro","entra","entras","entramos","entraba","entrarán",
    "trabajar","trabajo","trabaja","trabajas","trabajamos","trabajaba","trabajarán","escribir","escribo","escribe",
    "escribes","escribimos","escribía","escribirán",
]

ENGLISH_COMMON = [
    "the","be","to","of","and","a","in","that","have","I","it","for","not","on","with","he","as","you","do","at",
    "this","but","his","by","from","they","we","say","her","she","or","an","will","my","one","all","would",
    "there","their","what","so","up","out","if","about","who","get","which","go","me","when","make","can","like",
    "time","no","just","him","know","take","people","into","year","your","good","some","could","them","see",
    "other","than","then","now","look","only","come","its","over","think","also","back","after","use","two",
    "how","our","work","first","well","way","even","new","want","because","any","these","give","day","most","us",
]

CODE_COMMON = [
    "def","class","import","from","return","if","else","elif","for","while","try","except","finally","with",
    "as","lambda","yield","async","await","True","False","None","self","super","init","str","int","float","bool",
    "list","dict","set","tuple","len","range","enumerate","zip","map","filter","print","input","open","read",
    "write","close","append","extend","pop","remove","fn","let","mut","const","struct","impl","trait","mod",
    "use","pub","match","loop","break","continue","move","ref","box","vec","string","option","result","ok",
    "err","some","none","unwrap","expect","panic","assert",
]


def load_text_from_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Malbolge Translator - Generate pure Malbolge programs")
    parser.add_argument("input", nargs="?", help="Input text file or direct text (if --direct)")
    parser.add_argument("--direct", action="store_true", help="Treat input as direct text, not file")
    parser.add_argument("--max-depth", type=int, default=5, help="Max search depth (default: 5)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--output-dir", default="malbolge_output", help="Output directory (default: malbolge_output)")
    parser.add_argument("--base-name", default="output", help="Base filename (default: output)")
    parser.add_argument("--execute", action="store_true", help="Execute the generated program after generation")
    parser.add_argument("--max-steps", type=int, default=5_000_000, help="Max steps for execution")
    parser.add_argument("--populate-bank", action="store_true", help="Pre-populate word bank with common words")

    args = parser.parse_args()

    if not args.input and not args.direct:
        # Read from stdin
        import sys
        text = sys.stdin.read()
    elif args.direct:
        text = args.input
    else:
        text = load_text_from_file(Path(args.input))

    if not text:
        parser.error("No input text provided")

    print(f"[INFO] Input text length: {len(text)} chars")

    translator = MalbolgeTranslator(
        max_search_depth=args.max_depth,
        random_seed=args.seed,
    )

    def progress(i, total, word):
        if i % 10 == 0:
            print(f"  Progress: {i+1}/{total} words")

    result = translator.translate(text, progress_callback=progress)

    result.save_all(Path(args.output_dir), args.base_name)

    print(f"\n[SUMMARY]")
    print(f"  Words: {len(result.words)}")
    print(f"  Opcodes: {len(result.full_opcodes)}")
    print(f"  Program: {len(result.full_program)} chars")
    print(f"  Evaluations: {result.stats['evaluations']}")
    print(f"  Time: {result.stats['duration_s']:.2f}s")
    print(f"  Anchors: {result.stats['anchors_used']}")

    if args.execute:
        print()
        translator.execute(result, max_steps=args.max_steps)


if __name__ == "__main__":
    main()