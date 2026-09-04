#!/usr/bin/env python3
"""
Malbolge Generator Backend Adapter.

Provides a clean interface over malbolge-generator private APIs.
This isolates the translator from internal changes in malbolge-generator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Set
from pathlib import Path

from malbolge import (
    GenerationConfig,
    MalbolgeInterpreter,
    MalbolgeMachine,
    MalbolgeRuntimeError,
    ProgramGenerator,
)
from malbolge.generator import (
    _PrefixState,
    _GenerationStats,
    GenerationResult,
)


@dataclass
class _InternalPrefixState:
    """Wrapper for _PrefixState to avoid direct dependency."""
    opcodes: str
    output: str
    machine: MalbolgeMachine


@dataclass
class _InternalGenerationStats:
    """Wrapper for _GenerationStats."""
    evaluations: int = 0
    cache_hits: int = 0
    pruned: int = 0
    repeated_state_pruned: int = 0


class MalbolgeBackend:
    """
    Adapter for malbolge-generator internals.
    
    This class wraps the private APIs of malbolge-generator to provide
    a stable interface. If malbolge-generator changes its internals,
    only this adapter needs to be updated.
    """
    
    # Limit cache size to prevent memory exhaustion
    MAX_CACHE_SIZE = 10000
    
    def __init__(self, generator: ProgramGenerator):
        self._generator = generator
        self._interpreter = generator._interpreter
    
    @property
    def interpreter(self) -> MalbolgeInterpreter:
        return self._interpreter
    
    def create_prefix_state(
        self,
        opcodes: str,
        output: str,
        machine: MalbolgeMachine
    ) -> _InternalPrefixState:
        """Create a prefix state for generation."""
        return _InternalPrefixState(
            opcodes=opcodes,
            output=output,
            machine=machine.copy() if hasattr(machine, 'copy') else machine
        )
    
    def get_or_extend_state(
        self,
        prefix_state: _InternalPrefixState,
        suffix: str,
        cfg: GenerationConfig,
        cache: Dict[str, _InternalPrefixState],
        stats: _InternalGenerationStats,
    ) -> Tuple[_InternalPrefixState, bool]:
        """
        Get cached state or extend prefix with suffix.
        
        Returns:
            Tuple of (new_state, from_cache)
        """
        candidate_key = prefix_state.opcodes + suffix
        cached = cache.get(candidate_key)
        if cached is not None:
            stats.cache_hits += 1
            return cached, True
        
        extended = self._extend_state(
            prefix_state, suffix, cfg, stats
        )
        # Limit cache size to prevent memory exhaustion
        if len(cache) >= self.MAX_CACHE_SIZE:
            # Remove oldest entries (simple FIFO)
            keys_to_remove = list(cache.keys())[:len(cache) // 4]
            for key in keys_to_remove:
                del cache[key]
        cache[candidate_key] = extended
        return extended, False
    
    def _extend_state(
        self,
        prefix_state: _InternalPrefixState,
        suffix: str,
        cfg: GenerationConfig,
        stats: _InternalGenerationStats,
    ) -> _InternalPrefixState:
        """Extend prefix state with suffix opcodes."""
        if not suffix:
            return prefix_state
        
        new_length = len(prefix_state.opcodes) + len(suffix)
        if new_length > cfg.max_program_length:
            raise MalbolgeRuntimeError(
                "Generated program exceeds maximum allowed length."
            )
        
        # Limit output size to prevent memory exhaustion
        MAX_OUTPUT_LENGTH = 10000
        
        # Convert internal prefix state to malbolge-generator _PrefixState
        from malbolge.generator import _PrefixState as GenPrefixState
        gen_prefix = GenPrefixState(
            opcodes=prefix_state.opcodes,
            output=prefix_state.output,
            machine=prefix_state.machine
        )
        
        result = self._generator._extend_state(
            gen_prefix, suffix, self._interpreter, cfg, stats
        )
        
        if result.machine is None:
            raise MalbolgeRuntimeError(
                "Generator failed to capture machine snapshot during extension."
            )
        
        # Limit output size to prevent memory exhaustion
        output = prefix_state.output + result.output
        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:MAX_OUTPUT_LENGTH]
        
        return _InternalPrefixState(
            opcodes=result.opcodes,
            output=output,
            machine=result.machine
        )
    
    def finalize_state(
        self,
        state: _InternalPrefixState,
        cfg: GenerationConfig,
        add_halt: bool = True,
    ) -> _InternalPrefixState:
        """Finalize state by adding halt opcode if requested."""
        halt_suffix = "v" if add_halt else ""
        final_state, _ = self.get_or_extend_state(
            state, halt_suffix, GenerationConfig(
                opcode_choices=cfg.opcode_choices,
                max_search_depth=cfg.max_search_depth,
                random_seed=cfg.random_seed
            ), {}, _InternalGenerationStats()
        )
        return final_state
    
    def search_continuation(
        self,
        start_machine: MalbolgeMachine,
        target_text: str,
        max_search_depth: int = 5,
        random_seed: int = 42,
        opcode_choices: str = "op*",
    ) -> Tuple[str, MalbolgeMachine, dict]:
        """
        Search for opcodes that produce target_text from start_machine.
        
        Returns:
            Tuple of (continuation_opcodes, final_machine, stats_dict)
        """
        from time import perf_counter_ns
        from random import Random
        
        cfg = GenerationConfig(
            opcode_choices=opcode_choices,
            max_search_depth=max_search_depth,
            random_seed=random_seed,
        )
        rng = Random(random_seed)
        interp = self._interpreter
        stats = _InternalGenerationStats()
        cache: dict = {}
        dead: Set[str] = set()
        # Limit cache size to prevent memory exhaustion
        MAX_CACHE_SIZE = 10000
        
        prefix = self.create_prefix_state("", "", start_machine)
        cur = prefix
        start_ns = perf_counter_ns()
        
        for idx in range(len(target_text)):
            found = False
            combos = list(cfg.opcode_choices)
            depth = 0
            tpref = target_text[:idx+1]
            
            while not found:
                depth += 1
                for cand in combos:
                    suf = cand + "<"
                    pk = cur.opcodes + suf
                    if pk in dead:
                        stats.pruned += 1
                        continue
                    
                    cs, _ = self.get_or_extend_state(
                        cur, suf, cfg, cache, stats
                    )
                    if cs.machine is None:
                        continue
                    
                    out = cs.output
                    if target_text.startswith(out) and len(out) <= len(target_text):
                        if out == tpref:
                            cur = cs
                            found = True
                            break
                
                if found:
                    break
                
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
                    rc = Random(random_seed).choice(viable)
                    rs, _ = self.get_or_extend_state(
                        cur, rc, cfg, cache, stats
                    )
                    if rs.machine is None:
                        continue
                    cur = rs
                    combos = list(cfg.opcode_choices)
                    depth = 0
        
        # Add halt
        fs, _ = self.get_or_extend_state(
            cur, "v", GenerationConfig(
                opcode_choices=cfg.opcode_choices,
                max_search_depth=cfg.max_search_depth,
                random_seed=cfg.random_seed
            ), cache, _InternalGenerationStats()
        )
        
        cont = fs.opcodes  # This will be the continuation from the prefix
        vr = self._interpreter.execute_from_snapshot(
            start_machine, cont, capture_machine=True
        )
        dur = perf_counter_ns() - start_ns
        
        return cont, vr.machine, {"evaluations": stats.evaluations, "duration_ns": dur}
    
    def search_continuation(
        self,
        start_machine: MalbolgeMachine,
        target_text: str,
        max_search_depth: int = 5,
        random_seed: int = 42,
        opcode_choices: str = "op*",
    ) -> Tuple[str, MalbolgeMachine, dict]:
        """
        Search for opcodes that produce target_text from start_machine.
        
        Returns:
            Tuple of (continuation_opcodes, final_machine, stats_dict)
        """
        # This is the core search logic moved from anchor.py
        from time import perf_counter_ns
        from random import Random
        
        cfg = GenerationConfig(
            opcode_choices=opcode_choices,
            max_search_depth=max_search_depth,
            random_seed=random_seed,
        )
        rng = Random(random_seed)
        interp = self._interpreter
        stats = _InternalGenerationStats()
        cache: dict = {}
        dead: Set[str] = set()
        
        prefix = self.create_prefix_state("", "", start_machine)
        cur = prefix
        start_ns = perf_counter_ns()
        
        for idx in range(len(target_text)):
            found = False
            combos = list(cfg.opcode_choices)
            depth = 0
            tpref = target_text[:idx+1]
            
            while not found:
                depth += 1
                for cand in combos:
                    suf = cand + "<"
                    pk = cur.opcodes + suf
                    if pk in dead:
                        stats.pruned += 1
                        continue
                    
                    cs, _ = self.get_or_extend_state(
                        cur, suf, cfg, cache, stats
                    )
                    if cs.machine is None:
                        continue
                    
                    out = cs.output
                    if target_text.startswith(out) and len(out) <= len(target_text):
                        if out == tpref:
                            cur = cs
                            found = True
                            break
                
                if found:
                    break
                
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
                    rc = Random(random_seed).choice(viable)
                    rs, _ = self.get_or_extend_state(
                        cur, rc, cfg, cache, stats
                    )
                    if rs.machine is None:
                        continue
                    cur = rs
                    combos = list(cfg.opcode_choices)
                    depth = 0
        
        # Add halt
        fs, _ = self.get_or_extend_state(
            cur, "v", GenerationConfig(
                opcode_choices=cfg.opcode_choices,
                max_search_depth=cfg.max_search_depth,
                random_seed=cfg.random_seed
            ), cache, _InternalGenerationStats()
        )
        
        cont = fs.opcodes[len(prefix.opcodes):]
        vr = self._interpreter.execute_from_snapshot(
            start_machine, cont, capture_machine=True
        )
        dur = perf_counter_ns() - start_ns
        
        return cont, vr.machine, {"evaluations": stats.evaluations, "duration_ns": dur}
    
    def generate_anchor_target(
        self,
        start_machine: MalbolgeMachine,
        target: str,
        prefix_ops: str,
        max_search_depth: int = 5,
        random_seed: int = 42,
    ) -> str:
        """Generate target text from bootstrap state without halt."""
# This is the _generate_target logic from anchor.py
        from random import Random
        
        cfg = GenerationConfig(
            opcode_choices="op*",
            max_search_depth=max_search_depth,
            random_seed=random_seed,
        )
        rng = Random(cfg.random_seed)
        interp = self._interpreter
        stats = _InternalGenerationStats()
        cache: dict = {}
        dead: set = set()
        
        prefix = self.create_prefix_state(prefix_ops, "", start_machine)
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
                    cs, _ = self.get_or_extend_state(cur, suf, interp, cfg, cache, stats)
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
                    rs, _ = self.get_or_extend_state(cur, rc, interp, cfg, cache, stats)
                    if rs.machine is None: continue
                    cur = rs
                    combos = list(cfg.opcode_choices)
                    depth = 0
        
        return cur.opcodes
    
    def search_bridge(
        self,
        from_machine: MalbolgeMachine,
        target_anchor_machine: MalbolgeMachine,
        verify_text: str = "OK",
        max_search_depth: int = 3,
        random_seed: int = 42,
) -> str:
        """
        Search for opcodes to transition from_machine to target_anchor_machine.
        
        Returns opcodes that, when executed from from_machine, produce a state
        matching target_anchor_machine (verified by executing verify_text).
        """
        from malbolge.generator import _PrefixState
        from malbolge.generator import _GenerationStats
        from random import Random
        
        cfg = GenerationConfig(
            opcode_choices="op*",
            max_search_depth=3,
            random_seed=random_seed
        )
        rng = Random(cfg.random_seed)
        interp = self._interpreter
        stats = _GenerationStats()
        cache: dict = {}
        dead: set = set()
        
        prefix = _PrefixState(opcodes="", output="", machine=from_machine.copy())
        cur = prefix
        target = verify_text
        
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
                    cs, _ = self._generator._get_or_extend_state(
                        cur, suf, interp, cfg, cache, stats
                    )
                    if cs.machine is None:
                        continue
                    out = cs.output
                    if target.startswith(out) and len(out) <= len(target):
                        if out == tpref:
                            cur = cs
                            found = True
                            break
                if found:
                    break
                
                nf = []
                for b in combos:
                    for o in cfg.opcode_choices:
                        c = b + o
                        if (cur.opcodes + c + "<") not in dead:
                            nf.append(c)
                combos = nf
                if not combos:
                    break
        
        fs, _ = self._generator._get_or_extend_state(
            cur, "", interp, cfg, cache, stats
        )
        return fs.opcodes[len(prefix.opcodes):]


# Global backend instance (lazy initialization)
_backend: Optional[MalbolgeBackend] = None


def get_backend(generator: ProgramGenerator) -> MalbolgeBackend:
    """Get or create the global backend instance."""
    global _backend
    if _backend is None:
        _backend = MalbolgeBackend(generator)
    return _backend