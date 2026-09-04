# MALBOGUISTIC

> GitHub Linguist does not currently recognize Malbolge.
>
> So we translated GitHub Linguist into Malbolge instead. :p

**This project does NOT claim that Linguist executes in Malbolge.**

This project takes a pinned snapshot of [github-linguist/linguist](https://github.com/github-linguist/linguist)
and mechanically transports it, byte for byte, through a Malbolge toolchain,
verifying byte-identical reconstruction with SHA-256.

```
github-linguist/linguist  (pinned snapshot, commit SOURCE_COMMIT.txt)
        ↓
Malbolge-Translator  (vendored under vendor/malbolge_translator/)
        ↓
Level 1: mirror/<path>.malrt1     (MALRT1 envelope, every text file, codec-verified)
Level 2: malbolge/<path>.mal      (REAL pure Malbolge programs, executed, verified)
        ↓
reverse translation (decode + execution)
        ↓
SHA-256 parity against the original bytes
```

## Two levels, no fakes

| Level | Scope | Artifact | Claim |
|---|---|---|---|
| 1 — Codec mirror | **every** TEXT file | `mirror/**/*.malrt1` | `CODEC_MIRROR_PARITY`: source bytes → MALRT1 → decode → identical SHA-256 |
| 2 — Real Malbolge | TEXT files ≤ N bytes, under a wall-clock budget | `malbolge/**/*.mal` | `FULL_EXECUTED_ROUNDTRIP`: source → synthesized pure Malbolge → canonical execution → decode → identical SHA-256 |

CODEC ROUNDTRIP ≠ FULL MALBOLGE E2E FOR ARBITRARILY HUGE FILES.
Level 2 synthesis cost in this toolchain is roughly **~0.7 s per source byte**
(measured on this host), so a 130 KB `languages.yml` would take ~25 hours.
We do not pretend otherwise: every file not synthesized is marked
`SKIPPED_TOO_LARGE` or `SKIPPED_BUDGET` in the manifest. Nothing is hidden.

A `.malrt1` envelope is ASCII text (`MALRT1:<base64>:<sha256>`), **not** a
Malbolge program. Only files under `malbolge/` are executable Malbolge.

## Current run (commit pinned: befd3af35e70150b76458085208435eef9286bb3)

| Metric | Value |
|---|---|
| Source files (incl. 3 recorded symlinks) | 4,281 |
| Text files mirrored (level 1) | 4,258 / 4,258 (codec parity, 0 mismatches) |
| Binary files skipped | 20 |
| **Real Malbolge programs synthesized + executed (level 2)** | **379 / 379 eligible (≤128 B), 0 failures** |
| Original text bytes | 31,647,823 |
| Mirror envelope bytes (`mirror/`) | 42,509,444 (×1.34) |
| Real Malbolge program bytes (`malbolge/`) | 1,421,372 from 21,902 source bytes |
| Expansion ratio (level 2) | min ×41.7 · median ×67.8 · max ×462.8 |

Full details: `evidence/metrics.json`, `evidence/roundtrip.json`,
`evidence/VERDICTS.md` (claim table), and `manifest/translation_manifest.json`
(one entry per text file; its SHA-256 is `evidence/manifest_sha256.txt`).

## Reproduce

Requires Python ≥ 3.10 and the `malbolge-generator` package (importable as
`malbolge`, MIT). On this rig: `py` (bare `python` is shimmed away).

```
py tools/build_malboguistic.py                # full: level 1 + level 2 (default 1 h budget)
py tools/build_malboguistic.py --level1-only  # codec mirror only, seconds
```

Options: `--e2e-max-bytes` (default 128), `--e2e-budget-seconds` (default 3600),
`--workers`, `--resume` (reuses prior PASS results for unchanged sources).

Exit code 0 ⇔ zero codec mismatches AND zero failed executions.

## Disclaimers

GENERATED CORPUS ≠ ORGANIC USAGE.

This corpus must NOT be presented as evidence of real-world Malbolge adoption.
Do not say "Malbolge now has N thousand files of real usage" because of this
repo. That would be false.

The claim here is:

```
LINGUIST_TRANSLATED_TO_MALBOLGE = DEMONSTRATED (for the files listed PASS)
```

and emphatically NOT:

```
LINGUIST_RUNS_ON_MALBOLGE = NOT_CLAIMED
```

Malbolge contains Linguist. Linguist still contains no Malbolge. :p

## Layout

```
vendor/source_snapshot/      pinned linguist tree (no .git) + its LICENSE
vendor/malbolge_translator/  vendored translator package (MIT), see vendor/TRANSLATOR_SOURCE.txt
mirror/                      LEVEL 1 artifacts: <path>.malrt1 (codec envelopes)
malbolge/                    LEVEL 2 artifacts: <path>.mal (real, executed programs)
manifest/                    source_inventory.json, translation_manifest.json
evidence/                    roundtrip.json, metrics.json, VERDICTS.md, hashes
tools/build_malboguistic.py  the one-command reproducible build
SOURCE_REPO.txt / SOURCE_COMMIT.txt   provenance of the snapshot
```

## License

MALBOGUISTIC build tooling: MIT (see LICENSE).
The Linguist snapshot retains its own MIT license (`vendor/source_snapshot/LICENSE`).
The vendored translator is MIT (`vendor/malbolge_translator/LICENSE`).
See THIRD_PARTY_NOTICES.md.
