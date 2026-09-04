# GUIA — cómo operar MALBOGUISTIC

## El comando que buscas

```
py tools/build_malboguistic.py
```

Eso reconstruye todo: inventario → espejo codec (4.258 archivos) → síntesis
Malbolge real con presupuesto → manifests → métricas → VERDICTS.

## Regla de oro

**Un `.malrt1` NO es un programa Malbolge.** Es el sobre MALRT1 (ASCII) que
garantiza paridad de bytes por códec. Los programas Malbolge de verdad son
solo los de `malbolge/`, y cada uno PASÓ ejecución + decode + SHA-256.
Nunca presentes un `.malrt1` como "código Malbolge".

## Comandos

| Comando | Qué hace | Tiempo típico |
|---|---|---|
| `py tools/build_malboguistic.py --level1-only` | inventario + espejo codec | ~1 min |
| `py tools/build_malboguistic.py --e2e-budget-seconds 300` | espejo + 5 min de Malbolge real | ~6 min |
| `py tools/build_malboguistic.py --resume` | continúa donde quedó (reusa los PASS previos; verificado en producción) | variable |
| `py tools/build_malboguistic.py --resume --serial --search-depth 3` | modo rescate, sin pool; así se terminaron los últimos archivos grandes | ~1-2 min/archivo |
| `py tools/build_malboguistic.py --e2e-max-bytes 256` | NO PROBADO: sube el tope por archivo (teórico ~3 min por archivo de 256 B) | ojo |

Salida exitosa termina con `[done] manifest_sha256=...` y exit 0.

## Cómo leer la salida

| Estado | Significado | Qué hacer |
|---|---|---|
| `PASS` | sintetizado + ejecutado + decodificado + SHA idéntico | nada |
| `FAILED` | la síntesis/ejecución falló para ese archivo | míralo en `manifest/translation_manifest.json` → `malbolge.error`; el build da exit 1 |
| `SKIPPED_TOO_LARGE` | supera `--e2e-max-bytes` | normal: la síntesis cuesta ~0.7 s/BYTE fuente en esta máquina |
| `SKIPPED_BUDGET` | cabía pero se agotó el tiempo | relanza con más `--e2e-budget-seconds` y `--resume` |
| `mismatches=0` en `[level1]` | el espejo codec es 100% íntegro | nada |

## Trampas

- **No uses `python`, usa `py`.** En esta máquina `python` desnudo muere con
  exit 2718 (shim del guardián evo). En otras máquinas da igual.
- **`--e2e-max-bytes` alto = horas.** 128 bytes ≈ ~90 s por archivo. El coste
  es casi lineal, no hay sorpresa agradable.
- **`--workers` alto se estanca en esta máquina.** Medido: con 7 workers la
  contención dispara el watchdog (stalls de 900 s); con 3 workers va bien.
  Cada tarea usa un proceso fresco (`max_tasks_per_child=1`): un traductor
  reutilizado entre tareas degrada el rendimiento (medido: mismo archivo
  42 s solo vs >900 s en worker reutilizado).
- **Si el pool se sigue portando raro, usa `--serial`.** Fue el modo que cerró
  el corpus: 379/379 PASS con 0 fallos.
- **Si borras `evidence/level2_state.json`, pierdes el resume.** No lo borres
  salvo que quieras re-sintetizar todo.
- **Los 3 symlinks del tarball no existen en disco.** Están registrados en
  `manifest/source_inventory.json` con su destino. No los "arregles".
- **Exit 1 con `mismatches>0` es un fallo real**, no un aviso. Investiga antes
  de relanzar.
