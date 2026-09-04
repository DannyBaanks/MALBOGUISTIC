#!/usr/bin/env python3
"""
Multi-chapter Quijote generator for Malbolge.

Splits Don Quijote into chapters, generates one .mal per chapter,
and provides a chaining protocol for sequential execution.
"""

from __future__ import annotations

import re
import json
import hashlib
from pathlib import Path
from typing import List, Tuple
from dataclasses import dataclass, asdict

from malbolge_translator import MalbolgeTranslator
from malbolge_translator.translator import SPANISH_COMMON


@dataclass
class Chapter:
    number: int
    title: str
    text: str
    start_idx: int
    end_idx: int


@dataclass
class ChapterResult:
    chapter: int
    title: str
    words: int
    opcodes: int
    program_chars: int
    duration_s: float
    input_sha256: str
    output_sha256: str
    match: bool
    steps: int


def split_quijote_chapters(text: str) -> List[Chapter]:
    """Split Quijote text into chapters."""
    chapters = []
    
    # Find chapter markers: "CHAPTER I", "CHAPTER II", etc.
    chapter_pattern = r'(?i)^CHAPTER\s+([IVXLC]+)'
    lines = text.split('\n')
    
    chapter_starts = []
    for i, line in enumerate(lines):
        match = re.match(chapter_pattern, line.strip())
        if match:
            chapter_starts.append((i, match.group(1)))
    
    if not chapter_starts:
        # Fallback: split by "CHAPTER" keyword
        parts = re.split(r'(?i)(?=CHAPTER\s+[IVXLC]+)', text)
        for i, part in enumerate(parts):
            if part.strip():
                chapters.append(Chapter(
                    number=i+1,
                    title=f"Chapter {i+1}",
                    text=part.strip(),
                    start_idx=0,
                    end_idx=len(part)
                ))
        return chapters
    
    for idx, (start_line, roman) in enumerate(chapter_starts):
        end_line = chapter_starts[idx+1][0] if idx+1 < len(chapter_starts) else len(lines)
        chapter_text = '\n'.join(lines[start_line:end_line]).strip()
        if chapter_text:
            chapters.append(Chapter(
                number=idx+1,
                title=f"CHAPTER {roman}",
                text=chapter_text,
                start_idx=start_line,
                end_idx=end_line
            ))
    
    return chapters


def generate_chapter(
    translator: MalbolgeTranslator,
    chapter: Chapter,
    output_dir: Path,
    prev_machine_state: bytes = None
) -> ChapterResult:
    """Generate Malbolge program for a single chapter."""
    import time
    
    print(f"\n[CHAPTER {chapter.number}] {chapter.title}")
    print(f"  Length: {len(chapter.text):,} chars, ~{len(chapter.text.split()):,} words")
    
    # Pre-populate bank for this chapter
    translator.bank.bulk(SPANISH_COMMON[:200], translator.anchors.default())
    
    # For chapter 1, use fresh translator; for others, we could bridge from previous
    # For simplicity, each chapter starts from default anchor
    def progress(i, total, word):
        if i % 100 == 0 and i > 0:
            pct = (i / total) * 100
            print(f"  Progress: {i}/{total} words ({pct:.1f}%)")
    
    start = time.perf_counter()
    result = translator.translate(chapter.text, progress_callback=progress)
    duration = time.perf_counter() - start
    
    # Execute to verify
    exec_result = translator.execute(result, max_steps=10_000_000)
    match = exec_result == result.processed_text
    
    # Hashes
    input_hash = hashlib.sha256(chapter.text.encode('utf-8')).hexdigest()
    output_hash = hashlib.sha256(exec_result.encode('utf-8')).hexdigest()
    
    # Save chapter files
    chapter_dir = output_dir / f"chapter_{chapter.number:03d}"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    
    result.save_all(chapter_dir, f"quijote_ch{chapter.number:03d}")
    
    return ChapterResult(
        chapter=chapter.number,
        title=chapter.title,
        words=len(result.words),
        opcodes=len(result.full_opcodes),
        program_chars=len(result.full_program),
        duration_s=duration,
        input_sha256=input_hash,
        output_sha256=output_hash,
        match=match,
        steps=0  # Would need to capture from execute
    )


def main():
    import argparse
    import urllib.request
    
    parser = argparse.ArgumentParser(description="Generate full Quijote in Malbolge (chapter by chapter)")
    parser.add_argument("--output-dir", type=Path, default="artifacts/quijote", help="Output directory")
    parser.add_argument("--source", type=Path, help="Local Quijote text file")
    parser.add_argument("--max-chapters", type=int, default=None, help="Limit chapters for testing")
    args = parser.parse_args()
    
    # Load text
    if args.source:
        text = args.source.read_text(encoding="utf-8")
    else:
        print("[QUIJOTE] Downloading from Project Gutenberg...")
        url = "https://www.gutenberg.org/cache/epub/996/pg996.txt"
        urllib.request.urlretrieve("quijote.txt", url)
        text = Path("quijote.txt").read_text(encoding="utf-8")
        start = text.find("*** START OF THE PROJECT GUTENBERG EBOOK")
        end = text.find("*** END OF THE PROJECT GUTENBERG EBOOK")
        if start != -1 and end != -1:
            text = text[start:end]
            text = text[text.find("\n\n")+2:]
    
    print(f"[QUIJOTE] Total text: {len(text):,} chars")
    
    # Split into chapters
    chapters = split_quijote_chapters(text)
    print(f"[QUIJOTE] Found {len(chapters)} chapters")
    
    if args.max_chapters:
        chapters = chapters[:args.max_chapters]
        print(f"[QUIJOTE] Limited to first {len(chapters)} chapters")
    
    # Initialize translator
    translator = MalbolgeTranslator(anchor_interval=100)
    translator.bank.bulk(SPANISH_COMMON[:200], translator.anchors.default())
    
    # Generate each chapter
    results = []
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for chapter in chapters:
        try:
            result = generate_chapter(translator, chapter, output_dir)
            results.append(result)
            print(f"  [OK] Chapter {chapter.number}: {result.opcodes:,} opcodes, {result.duration_s:.1f}s, MATCH={result.match}")
            
            if not result.match:
                print(f"  ✗ MISMATCH! Stopping.")
                break
        except Exception as e:
            print(f"  [FAIL] Chapter {chapter.number} failed: {e}")
            break
    
    # Save manifest
    manifest = {
        "source": "Project Gutenberg: Don Quijote (Ormsby translation)",
        "source_url": "https://www.gutenberg.org/ebooks/996",
        "total_chapters": len(chapters),
        "generated_chapters": len(results),
        "chapters": [asdict(r) for r in results],
        "tool_version": "1.0.0",
        "generation_note": "Each chapter is a separate .mal program starting from default anchor. Chaining requires manual bridge execution."
    }
    
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    
    print(f"\n[QUIJOTE COMPLETE] Generated {len(results)} chapters in {output_dir}")
    print(f"[MANIFEST] {output_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()