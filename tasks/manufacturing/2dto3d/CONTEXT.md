# Context — 2dto3d

> **Living doc.** Agent updates this at the end of every session. First thing a resumed agent reads.

## Current State
Phase 7 complete: All implementation, VM setup, data pipeline, testing, and documentation done.

## Completed
- [x] Task intake filled and confirmed
- [x] Remote VM explored (136.117.92.206), data layout understood
- [x] Data pipeline completed — 129 workpieces organized
- [x] main.py implemented (load, start, evaluate) with 129 VARIANTS
- [x] Pos/neg tests passing (POS=1.0, NEG≈0.0)
- [x] README.md and DATA_PIPELINE.md written
- [ ] Committed and PR opened

## Key Decisions Made

| Decision | Rationale |
|---|---|
| Agent exports `.step` from Rhino | Standard exchange format, OCC can read it |
| GT files are `.step` (not `.prt`) | Raw data already in STEP format |
| 3-dimension scoring (volume + quantity + precision) | Matches existing `compare_json.py` approach |
| Pre-extract GT features to JSON | Avoids running OCC on GT during every evaluation |
| Use `build123d`/`cadquery` for OCP | pythonocc-core has no pip wheel, conda not on VM |

## Resolved Questions
- VM IP: **136.117.92.206**
- Workpiece count: **129** (8 SMA夹具 + 121 半自动电阻焊机)
- Rhino version: **Rhino 8** (`C:\Program Files\Rhino 8\System\Rhino.exe`)
- OCC availability: Installed via `pip install build123d` → OCP (`OCP.*` imports)
- Raw data format: **.STEP** (not .prt as initially assumed)

## Important Paths (Remote VM)
- Task root: `C:\Users\User\Desktop\manufacturing\2dto3d\`
- Raw data: `C:\Users\User\Desktop\manufacturing_raw\结构设计工作流\`
- Input: `<task_dir>\input\<TASK_TAG>.pdf`
- Output: `<task_dir>\output\<TASK_TAG>.step`
- Reference GT model: `<task_dir>\reference\<TASK_TAG>.step`
- Reference GT features: `<task_dir>\reference\gt_features.json`

## VM Info
- IP: 136.117.92.206
- OS: Windows
- Python: 3.12.6 (system pip, no conda)
- Software: Rhino 8, `build123d`, `cadquery`, `numpy`, `scipy`
- OCC access: via `OCP.*` imports (installed through `cadquery-ocp` dependency)

## Session Log
<!-- Append a one-line summary after each session -->
- 2026-03-01: Initial scaffold, main.py, evaluation scripts, data pipeline scripts created
- 2026-03-01: VM explored, data organized (129 workpieces), OCP installed, GT features extracted, pos/neg tests verified (POS=1.0, NEG≈0.0)
