#!/usr/bin/env python3
"""
Malbolge Translation Session GIF Renderer.

Creates a session.gif similar to FLOW's but for Malbolge translation:
- Left panel: terminal showing Malbolge opcodes being "typed"
- Right panel: live output where Malbolge transforms into Quijote text
- Each word completion triggers a visual transformation
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List, Tuple, Optional

# Colors
BG = (8, 8, 10)
PANEL_BG = (10, 13, 16)
TITLE_BG = (22, 26, 32)
TEXT = (196, 208, 224)
DIM = (96, 108, 128)
GREEN = (92, 210, 120)
YELLOW = (222, 200, 96)
BLUE = (110, 170, 240)
RED_DOT = (230, 84, 84)
YEL_DOT = (232, 190, 84)
GRN_DOT = (94, 214, 112)
MALBOLGE_GREEN = (0, 200, 100)
ORANGE = (255, 165, 0)
PURPLE = (180, 100, 255)

# Lazy-loaded fonts (only when PIL is available)
_FONT_CACHE: dict[int, Optional[object]] = {}
_FONT_BOLD_CACHE: dict[int, Optional[object]] = {}
_FONT_SMALL_CACHE: dict[int, Optional[object]] = {}


def _get_fonts(size: int = 14) -> tuple:
    """Lazy-load fonts when PIL is available."""
    global _FONT_CACHE, _FONT_BOLD_CACHE, _FONT_SMALL_CACHE
    
    try:
        from PIL import ImageFont
    except ImportError:
        return (None, None, None)
    
    if size not in _FONT_CACHE:
        try:
            _FONT_CACHE[size] = ImageFont.truetype("consola.ttf", size)
        except OSError:
            try:
                _FONT_CACHE[size] = ImageFont.truetype("cour.ttf", size)
            except OSError:
                _FONT_CACHE[size] = ImageFont.load_default()
    
    bold_size = size + 2
    if bold_size not in _FONT_BOLD_CACHE:
        try:
            _FONT_BOLD_CACHE[bold_size] = ImageFont.truetype("consola.ttf", bold_size)
        except OSError:
            try:
                _FONT_BOLD_CACHE[bold_size] = ImageFont.truetype("cour.ttf", bold_size)
            except OSError:
                _FONT_BOLD_CACHE[bold_size] = ImageFont.load_default()
    
    small_size = size - 2
    if small_size not in _FONT_SMALL_CACHE:
        try:
            _FONT_SMALL_CACHE[small_size] = ImageFont.truetype("consola.ttf", small_size)
        except OSError:
            try:
                _FONT_SMALL_CACHE[small_size] = ImageFont.truetype("cour.ttf", small_size)
            except OSError:
                _FONT_SMALL_CACHE[small_size] = ImageFont.load_default()
    
    return (_FONT_CACHE[size], _FONT_BOLD_CACHE[bold_size], _FONT_SMALL_CACHE[small_size])


def _check_pil() -> bool:
    """Check if PIL is available."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        return True
    except ImportError:
        return False


def _draw_terminal_chrome(canvas, title: str):
    from PIL import ImageDraw
    w, h = canvas.size
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, w - 1, h - 1], outline=(60, 66, 78), width=2)
    draw.rectangle([2, 2, w - 3, 26], fill=TITLE_BG)
    draw.ellipse([10, 9, 18, 17], fill=RED_DOT)
    draw.ellipse([22, 9, 30, 17], fill=YEL_DOT)
    draw.ellipse([34, 9, 42, 17], fill=GRN_DOT)
    _, font_bold, _ = _get_fonts(14)
    draw.text((50, 6), title, font=font_bold, fill=(230, 234, 240))
    return draw


def _draw_terminal_text(
    canvas,
    lines: List[Tuple[str, str]],
    show_cursor: bool,
    cursor_col: int,
    x_offset: int = 16,
    y_start: int = 38,
) -> int:
    from PIL import ImageDraw
    draw = ImageDraw.Draw(canvas)
    font, _, _ = _get_fonts(14)
    x, y = x_offset, y_start
    for idx, (kind, text) in enumerate(lines):
        if kind == "cmd":
            color = GREEN
        elif kind == "ok":
            color = YELLOW
        elif kind == "mal":
            color = MALBOLGE_GREEN
        elif kind == "word":
            color = ORANGE
        elif kind == "real":
            color = TEXT
        elif kind == "dim":
            color = DIM
        else:
            color = TEXT
        draw.text((x, y), text, font=font, fill=color)
        y += 20
    if show_cursor:
        draw.text((x + cursor_col * 9, y), "\u2588", font=font, fill=GREEN)
    return y


def _draw_output_panel(
    canvas,
    words_done: List[str],
    current_malbolge: str,
    show_cursor: bool,
    x_start: int,
    y_start: int,
    width: int,
) -> None:
    """Draw the right panel showing the transformation."""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(canvas)
    font, _, _ = _get_fonts(14)
    x, y = x_start, y_start
    
    # Draw completed words in real text
    for word in words_done:
        # Handle multiline words (replace newlines with space for display)
        display_word = word.replace('\n', ' ⏎ ')
        draw.text((x, y), display_word, font=font, fill=TEXT)
        text_w = draw.textlength(display_word, font=font)
        x += text_w + 4  # space between words
        if x > x_start + width - 50:
            x = x_start
            y += 22
    
    # Draw current Malbolge being typed (dimmed)
    if current_malbolge:
        draw.text((x, y), current_malbolge[:80], font=font, fill=DIM)
        if show_cursor:
            cur_x = x + draw.textlength(current_malbolge[:80], font=font)
            draw.text((cur_x, y), "\u2588", font=font, fill=MALBOLGE_GREEN)


class MalbolgeSessionRenderer:
    """Renders a Malbolge translation session as a GIF."""
    
    def __init__(
        self,
        translation_result,
        program_name: str = "quijote.mal",
        scale: int = 1,
        duration_ms: int = 100,
        max_frames: int = 300,
        loop: int = 0,
        title: str = "MALBOLGE TRANSLATOR - Quijote",
        chars_per_frame: int = 8,
    ):
        self.result = translation_result
        self.program_name = program_name
        self.scale = scale
        self.duration_ms = duration_ms
        self.max_frames = max_frames
        self.loop = loop
        self.title = title
        self.chars_per_frame = chars_per_frame
        
        # Extract the full opcodes and word boundaries
        self.full_opcodes = translation_result.full_opcodes
        self.words = [w.word for w in translation_result.words if w.success]
        self.word_opcodes = [w.continuation for w in translation_result.words if w.success]
        
    def _build_typing_script(self) -> List[Tuple[str, str]]:
        """Build the sequence of lines to type in the terminal."""
        lines = []
        lines.append(("cmd", f"$ malbolge-translate --quijote --max-chapters 1"))
        lines.append(("ok", "[MALBOLGE] Anchor bootstrap complete"))
        lines.append(("ok", "[MALBOLGE] Word bank loaded (200 common words)"))
        lines.append(("ok", "[MALBOLGE] Translating Chapter I..."))
        lines.append(("cmd", f"$ malbolge run {self.program_name}"))
        lines.append(("dim", "--- Malbolge execution begins ---"))
        return lines
    
    def _get_word_boundaries(self) -> List[Tuple[int, int, str]]:
        """Return list of (start_idx, end_idx, word) for each word in opcodes."""
        boundaries = []
        pos = 0
        for w_opcodes, word in zip(self.word_opcodes, self.words):
            start = pos
            end = pos + len(w_opcodes)
            boundaries.append((start, end, word))
            pos = end
        return boundaries
    
    def render(self, output_path: str) -> Path:
        """Render the session GIF."""
        if not _check_pil():
            raise RuntimeError(
                "PIL (pillow) is required for GIF rendering. "
                "Install with: pip install pillow"
            )
        from PIL import Image, ImageDraw
        
        script_lines = self._build_typing_script()
        word_boundaries = self._get_word_boundaries()
        
        # Calculate total characters to type (opcodes + commands)
        total_opcode_chars = len(self.full_opcodes)
        total_cmd_chars = sum(len(t) for _, t in script_lines)
        total_chars = total_cmd_chars + total_opcode_chars
        
        # Panel dimensions
        panel_w = 520
        output_w = 400
        win_w = panel_w + output_w + 40
        win_h = 500
        
        canvas = Image.new("RGB", (win_w, win_h), BG)
        _draw_terminal_chrome(canvas, self.title)
        
        # Draw panel separators
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([12, 34, panel_w + 4, win_h - 14], fill=PANEL_BG, outline=(36, 42, 52))
        draw.rectangle([panel_w + 16, 34, win_w - 12, win_h - 14], fill=PANEL_BG, outline=(36, 42, 52))
        _, font_bold, _ = _get_fonts(14)
        draw.text((panel_w + 24, 38), "OUTPUT (Malbolge -> Text)", font=font_bold, fill=YELLOW)
        
        frames = []
        words_done = []
        current_malbolge = ""
        current_word_idx = 0
        current_opcode_pos = 0
        
        # Pre-calculate when each word boundary occurs
        word_starts = [b[0] for b in word_boundaries]
        word_ends = [b[1] for b in word_boundaries]
        
        for i in range(self.max_frames):
            frame = canvas.copy()
            
            # Progress through typing
            chars_done = int(total_chars * i / max(1, self.max_frames - 1))
            
            # Build visible lines for terminal
            visible_lines = []
            budget = chars_done
            
            # First, type the script commands
            for kind, text in script_lines:
                if budget <= 0:
                    break
                take = min(budget, len(text))
                visible_lines.append((kind, text[:take]))
                budget -= len(text)
            
            # Then type the opcodes
            if budget > 0:
                opcode_chunk = self.full_opcodes[:budget]
                if opcode_chunk:
                    visible_lines.append(("mal", opcode_chunk))
                    current_malbolge = opcode_chunk
                    # Track word completions
                    while (current_word_idx < len(word_ends) and 
                           word_ends[current_word_idx] <= budget):
                        words_done.append(self.words[current_word_idx])
                        current_word_idx += 1
                else:
                    current_malbolge = ""
            
            # Draw terminal
            _draw_terminal_text(
                frame, visible_lines, 
                show_cursor=(i % 3 == 0 and budget < total_chars),
                cursor_col=len(visible_lines[-1][1]) if visible_lines else 0,
                x_offset=16, y_start=38
            )
            
            # Draw output panel (right side)
            _draw_output_panel(
                frame, words_done, current_malbolge,
                show_cursor=(i % 3 == 0),
                x_start=panel_w + 24, y_start=68,
                width=output_w - 30
            )
            
            # Status line
            from PIL import ImageDraw
            rd = ImageDraw.Draw(frame)
            _, _, font_small = _get_fonts(14)
            rd.text(
                (panel_w + 20, win_h - 30),
                f"opcodes: {min(budget, total_opcode_chars):05d}/{total_opcode_chars:05d} | words: {len(words_done):02d}/{len(self.words):02d}",
                font=font_small,
                fill=BLUE,
            )
            
            frames.append(frame)
            
            if budget >= total_chars and current_word_idx >= len(self.words):
                # Add a few final frames showing completion
                for _ in range(10):
                    frames.append(frame)
                break
        
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        frames[0].save(
            out,
            save_all=True,
            append_images=frames[1:],
            duration=self.duration_ms,
            loop=self.loop,
        )
        return out


def render_malbolge_session(
    translation_result,
    output_path: str,
    program_name: str = "quijote.mal",
    **kwargs,
) -> Path:
    """Convenience function to render a Malbolge translation session GIF."""
    renderer = MalbolgeSessionRenderer(translation_result, program_name, **kwargs)
    return renderer.render(output_path)


if __name__ == "__main__":
    # Demo: generate a session GIF for Chapter 1
    from malbolge_translator import MalbolgeTranslator
    from malbolge_translator.generate_quijote_chapters import split_quijote_chapters
    
    print("Generating Malbolge session GIF for Quijote Chapter I...")
    
    # Load Quijote text
    quijote_path = Path(os.environ.get("QUIJOTE_PATH", "quijote.txt"))
    if quijote_path.exists():
        text = quijote_path.read_text(encoding="utf-8")
        chapters = split_quijote_chapters(text)
        chapter_1 = chapters[0].text
        
        # Translate just chapter 1
        translator = MalbolgeTranslator(anchor_interval=50)
        result = translator.translate(chapter_1)
        
        # Render session GIF
        out_path = Path("malbolge_session.gif")
        render_malbolge_session(
            result,
            str(out_path),
            program_name="quijote_ch001.mal",
            duration_ms=80,
            max_frames=200,
            chars_per_frame=6,
        )
        print(f"Session GIF written to {out_path}")
    else:
        print("Quijote text not found, using sample...")
        translator = MalbolgeTranslator()
        result = translator.translate("En un lugar de la Mancha")
        render_malbolge_session(result, "malbolge_session.gif")
        print(f"Session GIF written to malbolge_session.gif")