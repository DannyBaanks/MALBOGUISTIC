#!/usr/bin/env python3
"""
Generate Don Quijote in Malbolge - standalone entry point.

This is a demo artifact generator for the public repository.
Don Quijote is public domain (Project Gutenberg).
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

from malbolge_translator import MalbolgeTranslator
from malbolge_translator.translator import SPANISH_COMMON


def download_quijote() -> str:
    """Download Don Quijote from Project Gutenberg."""
    import urllib.request
    
    url = "https://www.gutenberg.org/cache/epub/996/pg996.txt"
    path = Path("quijote.txt")
    
    print("[QUIJOTE] Downloading from Project Gutenberg...")
    urllib.request.urlretrieve(url, path)
    print("[QUIJOTE] Downloaded")
    
    text = path.read_text(encoding="utf-8")
    start = text.find("*** START OF THE PROJECT GUTENBERG EBOOK")
    end = text.find("*** END OF THE PROJECT GUTENBERG EBOOK")
    if start != -1 and end != -1:
        text = text[start:end]
        text = text[text.find("\n\n")+2:]
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Don Quijote in Malbolge")
    parser.add_argument("--output-dir", type=Path, default="artifacts/quijote", help="Output directory")
    parser.add_argument("--source", type=Path, help="Local Quijote text file (optional)")
    parser.add_argument("--execute", action="store_true", help="Execute verification")
    parser.add_argument("--max-steps", type=int, default=5_000_000, help="Max execution steps")
    parser.add_argument("--anchor-every", type=int, default=100, help="Anchor reset interval")
    args = parser.parse_args()
    
    # Load text
    if args.source:
        text = args.source.read_text(encoding="utf-8")
    else:
        text = download_quijote()
    
    print(f"[QUIJOTE] Text length: {len(text):,} chars")
    print(f"[QUIJOTE] Estimated words: ~{len(text.split()):,}")
    
    # Initialize translator
    translator = MalbolgeTranslator(anchor_interval=args.anchor_every)
    
    # Pre-populate bank
    print("[QUIJOTE] Pre-populating word bank with common Spanish words...")
    translator.bank.bulk(SPANISH_COMMON[:200], translator.anchors.default())
    
    def progress(i: int, total: int, word: str) -> None:
        if i % 100 == 0:
            pct = (i / total) * 100
            print(f"  Progress: {i}/{total} words ({pct:.1f}%)")
    
    print("[QUIJOTE] Translating...")
    result = translator.translate(text, progress_callback=progress)
    
    # Save
    output_dir = args.output_dir
    result.save_all(output_dir, "quijote")
    translator.save_cache()
    
    print(f"\n[QUIJOTE COMPLETE]")
    print(f"  Words: {len(result.words):,}")
    print(f"  Opcodes: {len(result.full_opcodes):,}")
    print(f"  Program: {len(result.full_program):,} chars ({len(result.full_program)/1e6:.1f} MB)")
    print(f"  Time: {result.stats['duration_s']:.1f}s")
    
    if args.execute:
        print("[QUIJOTE] Verifying execution...")
        translator.execute(result, max_steps=args.max_steps)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())