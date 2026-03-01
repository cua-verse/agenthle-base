# Context — gcode

## Current State

Implementation complete. Evaluation pipeline tested and passing. Branch `weichen/gcode` committed and ready to push/PR.

## Completed
- [x] Task intake filled — 15 PowerMill CAM workpiece variants, identical evaluation logic
- [x] Remote VM explored — data layout understood, all 15 input PM projects verified
- [x] Reference PM projects copied to `reference/ref_pm_project/` via `copy_references.py`
- [x] Reference STLs generated via `generate_ref_stls.py` (PowerMill simulation, GBK macro)
- [x] Pos/neg test dirs created via `setup_test_dirs.py`
- [x] Evaluation scripts written: `check_collision.py`, `simulate_agent.py`, `verify_stl.py`
- [x] `main.py` implemented: 15-variant `load()`, copy-to-output `start()`, test-aware `evaluate()`
- [x] PowerMill shortcuts created in `software/` for all 15 task dirs
- [x] `test_eval_local.sh` tested: pos=1.0000, neg=0.1532–0.1657 for all tested variants
- [x] `README.md` and `scripts/DATA_PIPELINE.md` written
- [x] Branch `weichen/gcode` committed (9 files, 1750 insertions)

## Key Decisions Made

| Decision | Rationale |
|---|---|
| Compare agent STL vs **expert reference STL**, not ideal `.prt` part | The `.prt` has color-coded tolerance zones encoding intentional leave-stock. Automating color parsing is hard. The expert output already encodes correct tolerances. |
| One-sided distance metric (`closest_point`, agent → ref) | Stock models may not be watertight; two-sided `signed_distance` fails on open meshes |
| Gate check (collision/gouge) first | Any collision is a hard failure in machining — score 0 immediately |
| Scripts uploaded per-eval, not deployed permanently | Prevents version drift; all scripts live in the local codebase |
| Copy-to-output pattern | Keeps `input/` pristine across agent runs; agent works on `output/` copy |
| Test mode: skip simulation when `agent_sim.stl` pre-exists | Allows pos/neg testing without needing a full PM project in the test dirs |

## Important Paths (Remote VM)

- Task root: `C:\Users\User\Desktop\manufacturing\gcode\<TASK_TAG>\`
- Input PM project: `...\input\<PM_PROJECT_NAME>\`
- Output (eval): `...\output\<PM_PROJECT_NAME>\` (agent's modified copy)
- Reference: `...\reference\reference_sim.stl`
- Test pos: `...\output_test_pos\agent_sim.stl` (= copy of reference_sim.stl)
- Test neg: `...\output_test_neg\agent_sim.stl` (= different workpiece's reference_sim.stl)
- Eval scripts temp: `C:\Users\User\AppData\Local\Temp\gcode_eval_scripts\`

## VM Info
- IP: 34.168.192.143 (may change — confirm with user before connecting)
- OS: Windows
- PowerMill 2025 installed at `C:\Program Files\Autodesk\PowerMill 2025\sys\exec64\pmill.exe`
- Python packages needed: `trimesh`, `numpy`, `pywin32`

## Last Session Summary
2026-03-01: Completed all phases. Tested eval with pos/neg (score 1.0 / 0.15). Wrote guide system. Committed to `weichen/gcode` branch.
