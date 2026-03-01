# 2D-to-3D — Rhino 3D Modeling from Engineering Drawings

## Overview

The agent receives a 2D engineering drawing (PDF) of a mechanical workpiece and must
build the corresponding 3D solid model in Rhinoceros (Rhino 8) on a remote Windows VM.
The agent's output is evaluated by comparing geometric features against a pre-computed
ground truth.

## Task Structure

```
tasks/manufacturing/2dto3d/
├── main.py              ← Task registration, setup, evaluation (129 variants)
├── TASK_INTAKE.md       ← Task definition
├── CONTEXT.md           ← Living context doc
├── PITFALLS.md          ← Task-specific gotchas
├── README.md            ← This file
└── scripts/
    ├── DATA_PIPELINE.md           ← How data was constructed
    ├── organize_data.py           ← [Data prep] Restructure raw data
    ├── generate_gt_json.py        ← [Setup] Extract GT features
    ├── setup_test_dirs.py         ← [Setup] Create pos/neg test dirs
    ├── extract_features.py        ← [Eval] Extract agent features (OCP/OCC dual)
    ├── verify_3d.py               ← [Eval] Score agent vs GT
    ├── original_read_gt.py        ← Original reference script (not used in pipeline)
    └── original_compare_json.py   ← Original reference script (not used in pipeline)
```

## Remote VM Layout (136.117.92.206)

```
C:\Users\User\Desktop\manufacturing\2dto3d\<task_tag>\
├── input\
│   └── <task_tag>.pdf         ← 2D engineering drawing
├── output\                     ← Agent writes here
│   └── <task_tag>.step         ← Agent's 3D model (STEP format)
├── reference\
│   ├── <task_tag>.step         ← Ground truth 3D model (STEP format)
│   └── gt_features.json        ← Pre-extracted GT features
└── software\
    └── Rhino.lnk               ← Shortcut to Rhino 8
```

## Evaluation

Three-dimensional scoring (normalized to 0.0–1.0):

| Dimension | Weight | What it measures |
|---|---|---|
| Global geometry | 20% | Volume error + bounding box origin alignment |
| Feature quantity | 30% | Hole count histogram (correct # of holes per diameter) |
| Feature precision | 50% | Hole position accuracy + axis alignment |

**Gate condition**: Output `.step` file must exist and be loadable by OCC/OCP.

## OCC/OCP Dependencies

The evaluation scripts use Open CASCADE for STEP file analysis. On the VM, this is
installed via `pip install build123d`, which provides `OCP.*` imports (not the more
common `OCC.Core.*` from pythonocc-core). The `extract_features.py` script supports
both import paths transparently.

## Data Pipeline

See [DATA_PIPELINE.md](scripts/DATA_PIPELINE.md) for the full data construction process.

Quick summary:
1. `organize_data.py` — restructure raw data (129 workpieces)
2. `generate_gt_json.py` — extract GT features
3. `setup_test_dirs.py` — create test data

## Testing

```bash
# Positive test (expected score ~1.0)
REMOTE_OUTPUT_DIR=output_test_pos bash test_eval_local_2dto3d.sh

# Negative test (expected score low)
REMOTE_OUTPUT_DIR=output_test_neg bash test_eval_local_2dto3d.sh
```
