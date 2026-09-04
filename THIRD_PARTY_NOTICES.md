# THIRD-PARTY NOTICES

## github-linguist/linguist

- Snapshot pinned at commit `befd3af35e70150b76458085208435eef9286bb3`
  (see SOURCE_REPO.txt / SOURCE_COMMIT.txt).
- License: **MIT** — full text preserved at `vendor/source_snapshot/LICENSE`.
- The snapshot directory `vendor/source_snapshot/` is an unmodified copy
  (tarball SHA-256 `01EF2366FAA3481608C5B3E9E83E613C12A4A1724947D87EC12B081B1A9A7677`),
  except that 3 symlinks could not be materialized on Windows and are recorded
  in `manifest/source_inventory.json` instead.
- Files under `mirror/` and `malbolge/` are mechanical, byte-exactly
  reversible transformations of those MIT-licensed sources; the MIT license
  of linguist applies to them as derivative encodings.

## Malbolge-Translator (`vendor/malbolge_translator/`)

- Vendored verbatim from the Malbolge-Translator repo
  (commit `16ca88287615588027a1b5b78ec606def02ef4ad`, see
  `vendor/TRANSLATOR_SOURCE.txt`).
- License: **MIT** — `vendor/malbolge_translator/LICENSE`.

## malbolge-generator (runtime dependency, NOT vendored)

- Importable as the `malbolge` package; provides the program generator and the
  canonical Malbolge interpreter used by level 2.
- License: **MIT**.
- Not copied into this repo; install it separately
  (`pip install malbolge-generator` or from the malbolge-toolkit repo).
