#!/usr/bin/env python3
"""
Lexicon/Transliteration system for Malbolge translator.
Maps non-ASCII characters to ASCII equivalents for Malbolge compatibility.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional
import json
from pathlib import Path


# Comprehensive default mappings for non-ASCII -> ASCII
DEFAULT_LEXICON: Dict[str, str] = {
    # Spanish accents
    "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
    "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
    "ñ": "ny", "Ñ": "NY", "ü": "u", "Ü": "U",
    "¿": "?", "¡": "!",
    
    # French
    "à": "a", "â": "a", "ä": "a", "ç": "c", "è": "e", "ê": "e", "ë": "e",
    "î": "i", "ï": "i", "ô": "o", "ö": "o", "ù": "u", "û": "u", "ÿ": "y",
    "À": "A", "Â": "A", "Ä": "A", "Ç": "C", "È": "E", "Ê": "E", "Ë": "E",
    "Î": "I", "Ï": "I", "Ô": "O", "Ö": "O", "Ù": "U", "Û": "U",
    
    # German
    "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ä": "ae", "ö": "oe", "ü": "ue",
    
    # Portuguese
    "ã": "a", "õ": "o", "Ã": "A", "Õ": "O",
    
    # Nordic
    "å": "aa", "Å": "AA", "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE",
    
    # Eastern European
    "č": "c", "Č": "C", "š": "s", "Š": "S", "ž": "z", "Ž": "Z",
    "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
    
    # Greek (basic transliteration)
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i",
    "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
    "ο": "o", "π": "p", "ρ": "r", "σ": "s", "τ": "t", "υ": "y", "φ": "ph",
    "χ": "ch", "ψ": "ps", "ω": "o",
    "Α": "A", "Β": "B", "Γ": "G", "Δ": "D", "Ε": "E", "Ζ": "Z", "Η": "I",
    "Θ": "TH", "Ι": "I", "Κ": "K", "Λ": "L", "Μ": "M", "Ν": "N", "Ξ": "X",
    "Ο": "O", "Π": "P", "Ρ": "R", "Σ": "S", "Τ": "T", "Υ": "Y", "Φ": "PH",
    "Χ": "CH", "Ψ": "PS", "Ω": "O",
    
    # Cyrillic (basic)
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "Yo",
    "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "H", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Sch",
    "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
    
    # Chinese Pinyin (common words)
    "中": "zhong", "文": "wen", "中文": "zhongwen", "世": "shi", "界": "jie", "世界": "shijie",
    "你": "ni", "好": "hao", "你好": "nihao",
    "我": "wo", "是": "shi", "的": "de", "了": "le", "在": "zai", "有": "you",
    "人": "ren", "这": "zhe", "那": "na", "个": "ge", "不": "bu", "也": "ye",
    "一": "yi", "二": "er", "三": "san", "四": "si", "五": "wu", "六": "liu",
    "七": "qi", "八": "ba", "九": "jiu", "十": "shi",
    
    # Japanese (basic romaji)
    "ひらがな": "hiragana", "カタカナ": "katakana", "漢字": "kanji",
    "日本": "nihon", "語": "go", "本": "hon", "日": "nichi",
    "私": "watashi", "は": "wa", "です": "desu", "ます": "masu",
    
    # Korean (basic)
    "한글": "hangul", "한국": "hanguk", "안녕": "annyeong",
    
    # Symbols
    "€": "EUR", "£": "GBP", "¥": "JPY", "©": "(c)", "®": "(r)", "™": "(tm)",
    "§": "S", "¶": "P", "†": "+", "‡": "++", "•": "*", "…": "...",
    "‹": "<", "›": ">", "«": "<<", "»": ">>", "–": "-", "—": "--",
    "‘": "'", "’": "'", "“": '"', "”": '"', "„": '"',
    
    # Math
    "±": "+/-", "×": "x", "÷": "/", "≤": "<=", "≥": ">=", "≠": "!=",
    "∞": "inf", "∑": "sum", "∏": "prod", "√": "sqrt", "∫": "int",
    "π": "pi", "φ": "phi", "θ": "theta", "λ": "lambda", "μ": "mu",
    "σ": "sigma", "Ω": "Omega", "Δ": "Delta",
    
    # Arrows
    "←": "<-", "→": "->", "↑": "^", "↓": "v", "↔": "<->",
    "⇐": "<=", "⇒": "=>", "⇑": "^", "⇓": "v", "⇔": "<=>",
    
    # Box drawing
    "│": "|", "┌": "+", "┐": "+", "└": "+", "┘": "+", "├": "+", "┤": "+",
    "┬": "+", "┴": "+", "┼": "+", "─": "-", "━": "=", "┃": "|",
    
    # Emoji (text descriptions)
    "😀": ":)", "😂": ":D", "😭": ":(", "😡": ">:(", "👍": "(y)",
    "👎": "(n)", "❤️": "<3", "💔": "</3", "🔥": "fire", "⭐": "*",
    "✅": "[OK]", "❌": "[X]", "⚠️": "[!]", "ℹ️": "[i]", "💡": "[idea]",
    "🌍": "[world]", "🌎": "[world]", "🌏": "[world]", "🚀": "[rocket]",
    "💻": "[pc]", "📱": "[phone]", "☕": "[coffee]", "🍕": "[pizza]",
    "🎮": "[game]", "🎵": "[music]", "📚": "[book]", "✏️": "[edit]",
}


@dataclass
class Lexicon:
    mappings: Dict[str, str] = field(default_factory=dict)
    custom_file: Optional[Path] = None
    
    def __post_init__(self):
        if not self.mappings:
            self.mappings = DEFAULT_LEXICON.copy()
        if self.custom_file and self.custom_file.exists():
            self.load_custom()
    
    def add(self, char: str, replacement: str) -> None:
        """Add a custom mapping."""
        if len(char) != 1:
            raise ValueError("char must be a single character")
        self.mappings[char] = replacement
        self._save_custom()
    
    def add_multi(self, mappings: Dict[str, str]) -> None:
        """Add multiple mappings at once."""
        for char, repl in mappings.items():
            if len(char) == 1:
                self.mappings[char] = repl
        self._save_custom()
    
    def remove(self, char: str) -> bool:
        """Remove a custom mapping."""
        if char in self.mappings and char not in DEFAULT_LEXICON:
            del self.mappings[char]
            self._save_custom()
            return True
        return False
    
    def _save_custom(self) -> None:
        if self.custom_file:
            custom = {k: v for k, v in self.mappings.items() if k not in DEFAULT_LEXICON}
            self.custom_file.parent.mkdir(parents=True, exist_ok=True)
            self.custom_file.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def load_custom(self) -> None:
        if self.custom_file and self.custom_file.exists():
            try:
                data = json.loads(self.custom_file.read_text(encoding="utf-8"))
                self.mappings.update(data)
            except Exception:
                pass
    
    def transliterate(self, text: str) -> str:
        """Transliterate text using longest-match-first strategy."""
        if not text:
            return ""
        
        sorted_keys = sorted(self.mappings.keys(), key=len, reverse=True)
        result = []
        i = 0
        
        while i < len(text):
            matched = False
            for key in sorted_keys:
                if text.startswith(key, i):
                    result.append(self.mappings[key])
                    i += len(key)
                    matched = True
                    break
            
            if not matched:
                ch = text[i]
                if ch in ' \t\r\n' or (33 <= ord(ch) <= 126):
                    result.append(ch)
                else:
                    result.append('?')
                i += 1
        
        return ''.join(result)
    
    def get_coverage(self, text: str) -> dict:
        """Analyze coverage of lexicon for given text."""
        total = 0
        covered = 0
        ascii_chars = 0
        unknown = []
        
        i = 0
        while i < len(text):
            total += 1
            matched = False
            for key in sorted(self.mappings.keys(), key=len, reverse=True):
                if text.startswith(key, i):
                    covered += 1
                    i += len(key)
                    matched = True
                    break
            if not matched:
                ch = text[i]
                if ch in ' \t\r\n' or (33 <= ord(ch) <= 126):
                    ascii_chars += 1
                else:
                    unknown.append(ch)
                i += 1
        
        return {
            "total_chars": total,
            "covered_by_lexicon": covered,
            "already_ascii": ascii_chars,
            "unknown": list(set(unknown)),
            "coverage_pct": (covered + ascii_chars) / max(total, 1) * 100,
        }
    
    def list_custom(self) -> Dict[str, str]:
        """List only user-added mappings."""
        return {k: v for k, v in self.mappings.items() if k not in DEFAULT_LEXICON}
    
    def export_custom(self, path: Path) -> None:
        """Export custom mappings for sharing."""
        custom = self.list_custom()
        path.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def import_custom(self, path: Path) -> int:
        """Import mappings shared by another user."""
        data = json.loads(path.read_text(encoding="utf-8"))
        self.add_multi(data)
        return len(data)


# Global default instance
default_lexicon = Lexicon()


def transliterate(text: str, lexicon: Optional[Lexicon] = None) -> str:
    """Quick function to transliterate text."""
    return (lexicon or default_lexicon).transliterate(text)