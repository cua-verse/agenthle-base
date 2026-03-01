# GCode CAM Task

## Overview

**Category**: Manufacturing / CAM Engineering  
**Software**: Autodesk PowerMill (on remote Windows VM)  
**Number of tasks**: 15 workpieces  

An LLM Agent is given a blank PowerMill project (with pre-configured tools but no toolpaths) and an ideal workpiece geometry file. The agent must design toolpaths to machine the workpiece from raw stock, achieving a simulated result that closely matches an expert's reference.

## Agent Input

Each task directory provides the agent with:

| File | Description |
|---|---|
| `input/<pm_project>/` | Blank PowerMill project — tools pre-loaded, **zero toolpaths** |
| `input/<workpiece>.prt` | Ideal workpiece geometry (NX .prt format, color-coded by precision) |
| `input/<workpiece>.jpg` | Reference image of the workpiece |

The blank PM project was created by taking the expert's reference project and **deleting all toolpaths and stock models** (via `delete_toopath.py`) — so the agent inherits the correct tool library, machine setup, and block definition, but must design the cutting strategy from scratch.

## Agent Objective

1. Open PowerMill and load the blank project
2. Study the ideal workpiece geometry to understand the target shape
3. Design toolpaths (roughing → semi-finishing → finishing) using the pre-configured tools
4. **Critical**: every toolpath must be free of collisions and gouging
5. Run stock model simulation to verify the result visually
6. Save the project

### Color Coding on the Workpiece

The `.prt` file has faces colored by machining precision:
- **Tight tolerance** (e.g., VDI12/15, 放电镜面): require fine finish passes
- **Loose tolerance** (e.g., 喷涂面, 咬花面): standard finish is acceptable

## Workflow: Copy-to-Output Pattern

During `start()`, the blank PM project from `input/` is copied to `output/`. The agent works on the copy in `output/`, keeping `input/` pristine. Evaluation reads from `output/`.

## Evaluation Pipeline

Evaluation is a 3-step process, all automated on the VM.
Scripts are uploaded from the local codebase to a temp folder on evaluation.

### Step 1 — Gate: Collision / Gouge Check

`check_collision.py` connects to PowerMill via COM, applies collision checking on all agent toolpaths. Any collision or gouge → **score = 0** immediately.

### Step 2 — Simulate Agent Result

`simulate_agent.py` drives PowerMill to create a stock model from the agent's toolpaths (in `output/`), then exports `output/agent_sim.stl`.

### Step 3 — Score: STL Comparison

`verify_stl.py` compares `agent_sim.stl` against `reference_sim.stl` (pre-generated from the expert's reference project):

```
Sample 10,000 points from agent surface
→ compute closest-point distance to reference surface (trimesh)
→ ratio_perfect    = fraction within 0.3mm
→ ratio_acceptable = fraction within 2.0mm
→ score = 0.7 × ratio_perfect + 0.3 × ratio_acceptable   ∈ [0, 1]
```

> **Why compare to the expert's stock model, not the ideal part?**  
> The color-coded faces specify intentional leave-stock (余量) that varies by surface. The expert's stock model already encodes those per-face tolerances. Comparing agent-to-expert avoids the need to automate color-spec parsing.

### Test Mode

When `agent_sim.stl` already exists in the output directory (e.g., via `output_test_pos/`), steps 1-2 are skipped and only the STL comparison runs. This enables testing with:

```bash
export REMOTE_OUTPUT_DIR=output_test_pos  # expected score ~1.0
export REMOTE_OUTPUT_DIR=output_test_neg  # expected score ~0.17
```

## Remote Directory Structure

```
C:\Users\User\Desktop\manufacturing\gcode\
├── scripts\                           ← all automation scripts
│   ├── DATA_PIPELINE.md               ← how task data was constructed
│   └── *.py
└── {TASK_TAG}\                        ← one per workpiece (15 total)
    ├── input\
    │   ├── {pm_project_cleaned}\      ← blank PM project (no toolpaths)
    │   ├── {workpiece}.prt            ← ideal workpiece geometry
    │   └── {workpiece}.jpg            ← reference image
    ├── reference\
    │   ├── ref_pm_project\            ← expert reference PM project
    │   └── reference_sim.stl          ← reference stock model (ground truth)
    ├── output\                        ← agent writes here; evaluate() reads from here
    │   └── agent_sim.stl
    ├── output_test_pos\               ← positive test case (ref copies as agent output)
    │   └── agent_sim.stl
    └── output_test_neg\               ← negative test case (different workpiece STL)
        └── agent_sim.stl
```

## Task Tags (15 Workpieces)

| Task Tag | Workpiece | Reference PM Project |
|---|---|---|
| `125162_319` | `125162` | `125162-319-NCFM-T` |
| `A125117_301` | `A125117` | `A125117-301-NCSM-B` |
| `A125138_301` | `A125138` | `A125138-301-NCFM-T` |
| `A125138_302` | `A125138` | `A125138-302-NCSM-B` |
| `MDBZDHZJ25_SKC_1_NCSM_T` | `MDBZDHZJ25` | `MDBZDHZJ25_SKC-1_NCSM_T` |
| `MR250692C00_M2` | `MR250692C00` | `MR250692C00-M2-NCFM-T` |
| `MR250696C00_F1` | `MR250696C00` | `MR250696C00-F1-NCSM-B` |
| `MR250696C00_S5` | `MR250696C00` | `MR250696C00-S5-NCSM-T` |
| `MR250697C00_M1` | `MR250697C00` | `MR250697C00-M1-NCFM-B` |
| `MR250697C00_S1` | `MR250697C00` | `MR250697C00-S1-NCSM-B` |
| `MR250697C00_S2` | `MR250697C00` | `MR250697C00-S2-NCFM-T` |
| `MR250698C00_F3` | `MR250698C00` | `MR250698C00-F3-NCSM-B` |
| `MR250698C00_P6` | `MR250698C00` | `MR250698C00-P6-NCSM-B` |
| `MR250698C00_U005` | `MR250698C00` | `MR250698C00-U005-NCFM-L` |
| `T29153_050` | `T29153` | `T29153-050-NCRM-F` |

## Environment Setup (One-Time)

### Prerequisites
- Remote Windows VM with PowerMill installed
- Python on VM with: `pip install pywin32 trimesh numpy`

### Steps

```bash
# 1. Copy expert reference PM projects into each task's reference/ folder
python scripts/copy_references.py

# 2. Open PowerMill manually on the VM

# 3. Generate all 15 reference stock model STLs (requires PM open)
python scripts/generate_ref_stls.py

# 4. Create positive/negative test directories
python scripts/setup_test_dirs.py
```

## Script Index

| Script | Phase | Requires PM | Description |
|---|---|---|---|
| `copy_references.py` | Setup | No | Copy 15 expert PM projects to `reference/ref_pm_project/` |
| `generate_ref_stls.py` | Setup | **Yes** | Batch simulate all reference PM projects → export `reference_sim.stl` |
| `setup_test_dirs.py` | Setup | No | Create `output_test_pos/` and `output_test_neg/` for all tasks |
| `simulate_agent.py` | Evaluation | **Yes** | Simulate agent toolpath → export `agent_sim.stl` |
| `verify_stl.py` | Evaluation | No | Score agent STL vs reference STL (point-to-mesh distance) |
| `check_collision.py` | Evaluation | **Yes** | Gate check: any collision/gouge → score = 0 |

## `main.py` Structure

The task follows the AgentHLE `load → start → evaluate` pattern:

- **`load()`** — registers the task with description and metadata
- **`start()`** — cleans output dir, opens the blank PM project in PowerMill
- **`evaluate()`** — runs gate check → simulate → score pipeline

Currently implemented as a pilot for `125162_319`. To extend to all 15 tasks, parameterize `WORKPIECE_TAG` in `GCodeTaskConfig`.
