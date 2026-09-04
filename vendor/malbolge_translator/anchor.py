#!/usr/bin/env python3
"""
Anchor Harness for Malbolge Translator.

Provides canonical machine states (anchors) that serve as known reset points.
Enables periodic state reset during long text generation to prevent drift.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from malbolge import (
    GenerationConfig,
    MalbolgeInterpreter,
    MalbolgeMachine,
    MalbolgeRuntimeError,
    ProgramGenerator,
)
from .backend import get_backend, MalbolgeBackend


@dataclass
class AnchorState:
    """A known machine state that serves as a dictionary anchor."""
    name: str
    machine: MalbolgeMachine
    hash: str
    bootstrap_opcodes: str  # Opcodes to reach this state from empty
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hash": self.hash,
            "bootstrap_opcodes": self.bootstrap_opcodes,
            "tape_len": len(self.machine.tape),
            "a": self.machine.a, "c": self.machine.c, "d": self.machine.d,
        }
    
    @classmethod
    def from_dict(cls, data: dict, machine: MalbolgeMachine) -> 'AnchorState':
        return cls(
            name=data["name"], machine=machine, hash=data["hash"],
            bootstrap_opcodes=data["bootstrap_opcodes"],
        )


class AnchorManager:
    """Manages canonical anchor states."""
    
    def __init__(
        self,
        generator: ProgramGenerator,
        interpreter: MalbolgeInterpreter,
        cache_dir: Path,
    ):
        self.generator = generator
        self.interpreter = interpreter
        self.backend = get_backend(generator)
        self.anchors: Dict[str, AnchorState] = {}
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = cache_dir / "anchors.json"
        self._machine_file = cache_dir / "anchor_machines.pkl"
    
    def create_anchor(self, name: str, target: str = "") -> AnchorState:
        """Create anchor as pure machine state initialization (no output)."""
        interp = self.generator._interpreter
        bootstrap_seq = "i" + "o" * 99  # Standard Malbolge bootstrap
        bs_r = interp.execute(bootstrap_seq, capture_machine=True)
        if bs_r.machine is None:
            raise MalbolgeRuntimeError("bootstrap failed")
        
        bootstrap_ops = bootstrap_seq
        if target:
            bootstrap_ops = self.backend.generate_anchor_target(
                bs_r.machine, target, bootstrap_seq
            )
        
        exec_r = interp.execute(bootstrap_ops, capture_machine=True)
        if exec_r.machine is None:
            raise MalbolgeRuntimeError("anchor exec failed")
        
        h = self._hash(exec_r.machine)
        anchor = AnchorState(
            name=name, machine=exec_r.machine, hash=h[:12],
            bootstrap_opcodes=bootstrap_ops
        )
        self.anchors[name] = anchor
        print(f"[Anchor] '{name}' hash={anchor.hash} ({len(bootstrap_ops)} ops)")
        return anchor
    
    def get(self, name: str) -> Optional[AnchorState]:
        return self.anchors.get(name)
    
    def default(self) -> AnchorState:
        if "default" not in self.anchors:
            self.create_anchor("default", "")
        return self.anchors["default"]
    
    def bridge(self, from_m: MalbolgeMachine, to: AnchorState, random_seed: int = 42) -> str:
        """Generate opcodes to transition from_m -> to.machine state, verifying the result matches target."""
        prefix = _PrefixState(opcodes="", output="", machine=from_m.copy())
        bridge_ops = self._search_bridge(prefix, to, "OK", random_seed=random_seed)
        
        # Verify the bridge actually reaches the target anchor state
        if bridge_ops:
            br = self.interpreter.execute_from_snapshot(from_m, bridge_ops, capture_machine=True)
            if br.machine:
                # Verify critical machine state matches target anchor
                target_m = to.machine
                result_m = br.machine
                if not self._states_match(result_m, target_m):
                    raise MalbolgeRuntimeError(
                        f"Bridge verification failed: resulting state does not match target anchor '{to.name}'. "
                        f"Expected a={target_m.a}, c={target_m.c}, d={target_m.d}, "
                        f"got a={result_m.a}, c={result_m.c}, d={result_m.d}"
                    )
        return bridge_ops
    
    def _states_match(self, m1: MalbolgeMachine, m2: MalbolgeMachine) -> bool:
        """Check if two machine states match in critical registers and tape prefix."""
        if m1.a != m2.a or m1.c != m2.c or m1.d != m2.d:
            return False
        # Compare tape prefix (first 100 cells)
        min_len = min(len(m1.tape), len(m2.tape), 100)
        return m1.tape[:min_len] == m2.tape[:min_len]
    
    def _search_bridge(self, prefix, target_anchor: AnchorState, verify: str, random_seed: int = 42) -> str:
        from malbolge.generator import _GenerationStats
        from random import Random
        
        cfg = GenerationConfig(opcode_choices="op*", max_search_depth=3, random_seed=random_seed)
        rng = Random(cfg.random_seed)
        interp = self.generator._interpreter
        stats = _GenerationStats()
        cache: dict = {}
        dead: set = set()
        
        cur = prefix
        target = verify
        
        for idx in range(len(target)):
            found = False
            combos = list(cfg.opcode_choices)
            depth = 0
            tpref = target[:idx+1]
            
            while not found and depth < cfg.max_search_depth:
                depth += 1
                for cand in combos:
                    suf = cand + "<"
                    pk = cur.opcodes + suf
                    if pk in dead:
                        stats.pruned += 1
                        continue
                    cs, _ = self.generator._get_or_extend_state(cur, suf, interp, cfg, cache, stats)
                    if cs.machine is None: continue
                    out = cs.output
                    if target.startswith(out) and len(out) <= len(target):
                        if out == tpref:
                            cur = cs
                            found = True
                            break
                if found: break
                
                nf = []
                for b in combos:
                    for o in cfg.opcode_choices:
                        c = b + o
                        if (cur.opcodes + c + "<") not in dead:
                            nf.append(c)
                combos = nf
                if not combos: break
        
        fs, _ = self.generator._get_or_extend_state(cur, "", interp, cfg, cache, stats)
        return fs.opcodes[len(prefix.opcodes):]
    
    def _hash(self, m: MalbolgeMachine) -> str:
        return hashlib.md5(f"{m.a},{m.c},{m.d},{m.tape[:100]}".encode()).hexdigest()
    
    def save(self) -> None:
        data = {n: a.to_dict() for n, a in self.anchors.items()}
        self._cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        machines = {n: a.machine for n, a in self.anchors.items()}
        self._machine_file.write_bytes(pickle.dumps(machines))
    
    def load(self) -> None:
        if not self._cache_file.exists():
            return
        data = json.loads(self._cache_file.read_text(encoding="utf-8"))
        if self._machine_file.exists():
            # SECURITY WARNING: Only load pickle files generated by this tool.
            # Do not load pickle files from untrusted sources.
            ms = pickle.loads(self._machine_file.read_bytes())
            for n, d in data.items():
                if n in ms:
                    self.anchors[n] = AnchorState.from_dict(d, ms[n])


# ============================================================
# WORD BANK - Cache for words from anchor state
# ============================================================

@dataclass
class BankEntry:
    word: str
    anchor_hash: str
    continuation: str  # Opcodes from anchor state
    stats: dict


class WordBank:
    """Caches word continuations generated FROM anchor state."""
    
    def __init__(
        self,
        generator: ProgramGenerator,
        interpreter: MalbolgeInterpreter,
        cache_dir: Path,
    ):
        self.generator = generator
        self.interpreter = interpreter
        self.entries: Dict[Tuple[str, str], BankEntry] = {}
        self.cache_dir = cache_dir
        self._file = cache_dir / "word_bank.json"
    
    def add(self, word: str, anchor: AnchorState) -> BankEntry:
        """Generate and cache word continuation from anchor state."""
        from malbolge.generator import _PrefixState
        prefix = _PrefixState(
            opcodes=anchor.bootstrap_opcodes, output="", machine=anchor.machine.copy()
        )
        result = self._generate_word(word, prefix, random_seed=anchor.hash.__hash__() & 0x7fffffff)
        cont = result.opcodes[len(anchor.bootstrap_opcodes):]
        entry = BankEntry(
            word=word, anchor_hash=anchor.hash,
            continuation=cont, stats=result.stats,
        )
        self.entries[(anchor.hash, word)] = entry
        return entry
    
    def get(self, word: str, anchor_hash: str) -> Optional[BankEntry]:
        return self.entries.get((anchor_hash, word))
    
    def verify(self, entry: BankEntry, anchor: AnchorState) -> bool:
        """Verify bank entry still works by executing from anchor state."""
        r = self.interpreter.execute_from_snapshot(
            anchor.machine, entry.continuation, capture_machine=True
        )
        return r.output == entry.word
    
    def bulk(self, words: List[str], anchor: AnchorState) -> int:
        c = 0
        for w in words:
            try:
                self.add(w, anchor)
                c += 1
            except Exception:
                pass
        return c
    
    def _generate_word(self, target: str, prefix, random_seed: int = 42) -> GenerationResult:
        from malbolge.generator import _GenerationStats, GenerationResult
        from random import Random
        
        cfg = GenerationConfig(opcode_choices="op*", max_search_depth=5, random_seed=random_seed)
        rng = Random(cfg.random_seed)
        interp = self.generator._interpreter
        stats = _GenerationStats()
        cache: dict = {}
        dead: set = set()
        
        cur = prefix
        
        for idx in range(len(target)):
            found = False
            combos = list(cfg.opcode_choices)
            depth = 0
            tpref = target[:idx+1]
            
            while not found:
                depth += 1
                for cand in combos:
                    suf = cand + "<"
                    pk = cur.opcodes + suf
                    if pk in dead:
                        stats.pruned += 1
                        continue
                    cs, _ = self.generator._get_or_extend_state(cur, suf, interp, cfg, cache, stats)
                    if cs.machine is None: continue
                    out = cs.output
                    if target.startswith(out) and len(out) <= len(target):
                        if out == tpref:
                            cur = cs
                            found = True
                            break
                
                if found: break
                
                nf = []
                for b in combos:
                    for o in cfg.opcode_choices:
                        c = b + o
                        if (cur.opcodes + c + "<") not in dead:
                            nf.append(c)
                combos = nf
                if not combos:
                    raise MalbolgeRuntimeError(f"exhausted {tpref}")
                
                if depth >= cfg.max_search_depth and combos:
                    viable = [c for c in combos if (cur.opcodes + c + "<") not in dead]
                    if not viable:
                        combos = list(cfg.opcode_choices)
                        depth = 0
                        continue
                    rc = Random(cfg.random_seed).choice(viable)
                    rs, _ = self.generator._get_or_extend_state(cur, rc, interp, cfg, cache, stats)
                    if rs.machine is None: continue
                    cur = rs
                    combos = list(cfg.opcode_choices)
                    depth = 0
        
        fs, _ = self.generator._get_or_extend_state(cur, "v", interp, cfg, cache, stats)
        return GenerationResult(
            target=target, opcodes=fs.opcodes, machine_output=fs.output,
            stats={"evaluations": stats.evaluations}, trace=[]
        )
    
    def save(self) -> None:
        data = {f"{ah}:{w}": {"word": e.word, "anchor_hash": e.anchor_hash,
                              "continuation": e.continuation, "stats": e.stats}
                for (ah, w), e in self.entries.items()}
        self._file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    
    def load(self) -> None:
        if not self._file.exists():
            return
        data = json.loads(self._file.read_text(encoding="utf-8"))
        for k, v in data.items():
            ah, w = k.split(":", 1)
            self.entries[(ah, w)] = BankEntry(
                word=v["word"], anchor_hash=v["anchor_hash"],
                continuation=v["continuation"], stats=v["stats"],
            )