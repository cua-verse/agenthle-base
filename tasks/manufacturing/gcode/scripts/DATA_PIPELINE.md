# Data Pipeline — How Task Data Was Constructed

This document records the full process of transforming raw manufacturing data into
structured AgentHLE task data. It is intended as a reference for reproducing the
pipeline or extending it to new workpieces.

## 1. Raw Data Layout

All raw data lives on the remote Windows VM at:

```
C:\Users\User\Desktop\manufacturing_raw\G代码工作流\
├── PM\                             ← PowerMill projects (expert ground truth)
│   ├── 125162\
│   │   ├── CNC\
│   │   │   └── 125162-319-NCFM-T\  ← complete PM project (tools + toolpaths)
│   │   └── 3D\
│   │       ├── 125162_319.prt       ← ideal workpiece geometry (NX format)
│   │       └── 125162_319.jpg       ← reference image
│   ├── MR250697C00\
│   │   ├── CNC\
│   │   │   ├── MR250697C00-M1-NCFM-B\
│   │   │   ├── MR250697C00-S1-NCSM-B\
│   │   │   └── MR250697C00-S2-NCFM-T\
│   │   └── 3D\
│   │       ├── MR250697C00_M1.prt
│   │       ├── MR250697C00_M1.jpg
│   │       └── ...
│   └── ... (9 more workpiece families)
└── 颜色规范.png                     ← color-to-tolerance specification image
```

### Naming Conventions

- **Workpiece family**: top-level folder name (e.g., `MR250697C00`)
- **PM project folder**: `{WorkpieceFamily}-{SequenceID}-{MachineType}-{Side}`
  - e.g., `MR250697C00-S2-NCFM-T` → workpiece `MR250697C00`, sequence `S2`, style `NCFM`, side `T` (Top)
- **Task tag**: derived by joining workpiece family + sequence with underscore
  - e.g., `MR250697C00-S2-NCFM-T` → task tag `MR250697C00_S2`

### What the Raw PM Projects Contain

Each PM project under `CNC/` is a **complete expert solution**:
- Pre-configured tools (end mills, ball nose, etc.)
- Fully designed toolpaths (roughing + finishing)
- Stock model configurations
- Machine setup (coordinate system, block definition)

These are the ground truth — the agent needs to reproduce similar toolpath quality.

## 2. Transformation Pipeline

### Step 0: Unzip archives (if needed)

Some raw data arrives as `.zip` / `.7z` / `.rar`. The utility script `unzip.py`
(on VM at `C:\Users\User\Desktop\gcode\unzip.py`) recursively extracts all archives
in-place.

```bash
python unzip.py "C:\Users\User\Desktop\manufacturing_raw" --delete-after
```

### Step 1: Create blank input PM projects (`delete_toopath.py`)

**Key insight**: we cannot give the agent an empty project from scratch, because
setting up tools, machine configuration, and coordinate systems is a separate
(much harder) task. Instead, we take the expert's complete PM project and **delete
only the toolpaths and stock models**, leaving the tool library and machine setup
intact.

The original script lives on the VM at `C:\Users\User\Desktop\gcode\delete_toopath.py`.
It drives PowerMill via COM to:

1. Open each expert PM project (read-only source)
2. Save-As to the target `input/` directory
3. `DELETE TOOLPATH ALL` + `DELETE STOCKMODEL ALL`
4. Save and close
5. Copy the corresponding `.prt` and `.jpg` from the `3D/` folder into `input/`

**PowerMill macro used** (inside `delete_toopath.py`):
```
DIALOGS MESSAGE OFF
DIALOGS ERROR OFF
PROJECT OPEN "{source_path}"
PROJECT SAVE AS "{target_path}"
DELETE TOOLPATH ALL
DELETE STOCKMODEL ALL
PROJECT SAVE
PROJECT CLOSE
DIALOGS MESSAGE ON
DIALOGS ERROR ON
```

> **Pitfall**: PowerMill must be open before running. The script uses
> `win32com.client.GetActiveObject("pmill.Document")` to attach to the
> running instance. If PM is not open, it tries `Dispatch()` to launch
> a new instance, but this can be unreliable on some VM configs.

> **Pitfall**: The script has a checkpoint mechanism (`pm_ready` + `jpg_ready`
> + `prt_ready` checks) to skip already-processed tasks. This is important
> because the pipeline can take 30+ minutes and may be interrupted by VM
> timeouts or PM crashes.

### Step 2: Copy expert reference projects (`copy_references.py`)

After Step 1 created the `input/` directories, we need the expert's original
PM projects as ground-truth references for evaluation.

`copy_references.py` copies each expert PM project from `manufacturing_raw`
into the task's `reference/ref_pm_project/` folder. It also removes PowerMill
lockfiles (which can block re-opening).

```bash
python scripts/copy_references.py          # real run
python scripts/copy_references.py --dry-run # preview only
```

> **Pitfall**: PowerMill creates `lockfile` inside each project folder.
> If not removed, PM refuses to open the project. The script auto-deletes
> these lockfiles after copying.

### Step 3: Generate reference stock model STLs (`generate_ref_stls.py`)

This is the most time-consuming step. For each of the 15 tasks, the script:

1. Connects to the running PowerMill instance via COM
2. Opens the expert reference PM project
3. Creates a stock model ("Ref_Sim_Result")
4. Attaches the block, then inserts all toolpaths sequentially
5. Calculates (simulates) the stock model
6. Exports the result as `reference/reference_sim.stl`

```bash
# PowerMill must be open first!
python scripts/generate_ref_stls.py                 # all 15 tasks
python scripts/generate_ref_stls.py --task 125162_319  # single task
python scripts/generate_ref_stls.py --force           # regenerate existing
```

**Time**: ~3-5 minutes per task (simulation is CPU-bound), ~45-75 min total.

> **Pitfall**: The PowerMill macro file must be written with `encoding="gbk"`
> (not UTF-8), because PowerMill on Chinese Windows expects GBK encoding.
> Using UTF-8 causes the macro to silently fail.

> **Pitfall**: `EXPORT STOCKMODEL_SHADING` exports the visual mesh (what you
> see in the 3D viewport). This is the right command for STL export, not
> `EXPORT STOCKMODEL` which exports internal data.

> **Pitfall**: Large projects (e.g., `MR250697C00_S2` at 8 MB STL) can take
> significantly longer. The script has no explicit timeout — if PM hangs,
> the Python process blocks indefinitely.

### Step 4: Build pos/neg test directories (`setup_test_dirs.py`)

Creates test data for validating the evaluation pipeline:

- **Positive test** (`output_test_pos/agent_sim.stl`):
  Copy of `reference_sim.stl` → self-comparison should score **~1.0**

- **Negative test** (`output_test_neg/agent_sim.stl`):
  Copy of a **different** task's `reference_sim.stl` (round-robin) →
  cross-workpiece comparison should score **low** (~0.17 observed)

```bash
python scripts/setup_test_dirs.py
```

## 3. Verification Scripts (Evaluation Phase)

These run during `evaluate()` in `main.py`, not during data construction:

### `verify_stl.py` — Core Scoring

Uses `trimesh.proximity.closest_point()` (does NOT require watertight meshes):
- Sample 10,000 points from agent surface
- Find closest point on reference surface for each sample
- Compute distance distribution → weighted score

**Design decision**: We chose unsigned closest-point distance over signed
distance (`trimesh.proximity.signed_distance`) because:
1. Signed distance requires watertight meshes (PowerMill STL exports are often
   not watertight)
2. We don't need to distinguish overcut vs undercut — any deviation from
   reference is penalized equally
3. closest_point is significantly faster (seconds vs minutes)

### `check_collision.py` — Gate Check

Connects to PowerMill, applies collision checking to all toolpaths, then
exports a SetupSheet CSV to parse collision/gouge flags.

> **Pitfall**: The exact column names in the SetupSheet CSV export (`Collision`,
> `Gouge`) have not been fully verified across all PM versions. This script
> may need adjustment if the CSV format differs.

### `simulate_agent.py` — Agent STL Export

Same PowerMill COM macro as `generate_ref_stls.py`, but operates on the
agent's modified PM project (after the agent has designed toolpaths).

## 4. Pitfalls Summary

| Issue | Root Cause | Fix |
|---|---|---|
| `UnicodeEncodeError: 'gbk'` in print | Windows terminal uses GBK; Python Unicode symbols (✓ ⚠) cannot be encoded | Use ASCII-only text in print statements |
| `UnicodeEncodeError` in PM macro | PowerMill macro parser expects GBK | Write `.mac` files with `encoding="gbk"` |
| PM lockfile blocks re-open | PowerMill creates lockfile on open | Delete `lockfile` after copying reference projects |
| `signed_distance` fails | Non-watertight mesh | Use `closest_point` instead |
| VM connection timeout | cua-computer WebSocket drops on slow ops | Add retry logic; run long commands in background |
| PM hangs on large project | Stock model simulation is CPU-bound for complex geometry | No workaround; allow generous timeouts |
| Path backslashes in docstrings | Python interprets `\U` as Unicode escape | Use raw strings (r"...") or double-backslash in docstrings |

## 5. Extending to New Workpieces

To add a new workpiece to the benchmark:

1. Place the expert PM project in `manufacturing_raw/G代码工作流/PM/{Workpiece}/CNC/`
2. Place the `.prt` and `.jpg` in `manufacturing_raw/G代码工作流/PM/{Workpiece}/3D/`
3. Add the mapping entry to `TASK_TO_REF_PM` in `copy_references.py`
4. Add the task tag to `TASK_TAGS` in `setup_test_dirs.py` and `generate_ref_stls.py`
5. Run `delete_toopath.py` (with the new workpiece path) to create the blank input
6. Run `copy_references.py` to copy the reference project
7. Run `generate_ref_stls.py --task {new_tag}` to generate the reference STL
8. Run `setup_test_dirs.py` to create pos/neg test data
9. Add a new `GCodeTaskConfig` entry in `main.py`

## 6. Script Index

| Script | Location | Phase | PM Required | Description |
|---|---|---|---|---|
| `delete_toopath.py` | VM `C:\...\gcode\` | Data prep | Yes | Batch-create blank input PM projects from expert originals |
| `unzip.py` | VM `C:\...\gcode\` | Data prep | No | Recursively extract archives in raw data directory |
| `copy_references.py` | `scripts/` | Setup | No | Copy expert PM projects into `reference/` folders |
| `generate_ref_stls.py` | `scripts/` | Setup | Yes | Batch-generate `reference_sim.stl` via PM stock model simulation |
| `setup_test_dirs.py` | `scripts/` | Setup | No | Create `output_test_pos/` and `output_test_neg/` for all tasks |
| `simulate_agent.py` | `scripts/` | Eval | Yes | Simulate agent toolpath, export `agent_sim.stl` |
| `verify_stl.py` | `scripts/` | Eval | No | Score agent STL vs reference STL (point-to-mesh distance) |
| `check_collision.py` | `scripts/` | Eval | Yes | Gate check — collision/gouge detection |
| `simulate.py` | VM `C:\...\gcode\` | Legacy | Yes | Original single-project simulation script |
| `compare.py` | VM `C:\...\gcode\` | Legacy | No | Original signed-distance comparison (requires watertight mesh) |
| `compare_stockmodels.py` | VM `C:\...\gcode\` | Legacy | No | Closest-point comparison prototype (predecessor to `verify_stl.py`) |
