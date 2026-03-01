# Data Pipeline — How Task Data Was Constructed

This document records the full process of transforming raw manufacturing data into
structured AgentHLE task data for the 2D-to-3D task.

## 1. Raw Data Layout

All raw data lives on the remote Windows VM at:

```
C:\Users\User\Desktop\manufacturing_raw\结构设计工作流\
├── 结构2D-3D-SMA线寿命测试电阻焊夹具(8pair)-20260208\
│   ├── 32300A-000001.pdf    ← 2D engineering drawing
│   ├── 32300A-000001.STEP   ← 3D ground truth model
│   └── ...                   (8 pairs total)
├── 结构2D-3D-半自动电阻焊机(121pair)-20260208\
│   ├── 20630A-000001.pdf
│   ├── 20630A-000001.STEP
│   └── ...                   (121 pairs total)
├── 结构2D-3D-单线马达 Tooling(4pair)-20260208\
│   └── ...                   (4 pairs, duplicates with SMA group)
└── AgentHLE-制造行业landscape-产品开发&结构 -20260204.xlsx  (overview, not used)
```

Each subfolder contains paired `.pdf` + `.STEP` files for workpieces.

> **Note:** The older `结构2D-3D-单线马达 Tooling-20260204` folder is a subset of the
> newer `(4pair)-20260208` version and is skipped. The 4 workpieces in the newer folder
> have the same IDs as SMA group items (32300A-000001..004), so they are also skipped
> as duplicates. Final count: **129 unique workpieces**.

## 2. Transformation Pipeline

### Step 1: Organize raw data (`organize_data.py`)

Restructures raw data into the standard AgentHLE layout:

```bash
python scripts/organize_data.py --dry-run    # preview
python scripts/organize_data.py              # real run
```

This creates:
```
C:\Users\User\Desktop\manufacturing\2dto3d\
├── <task_tag>\
│   ├── input\
│   │   └── <task_tag>.pdf       ← engineering drawing (read-only)
│   ├── output\                   ← empty (agent writes here)
│   ├── reference\
│   │   └── <task_tag>.step       ← ground truth 3D model
│   └── software\
│       └── Rhino.lnk            ← shortcut to Rhino 8
```

The script also prints a `VARIANTS` list to paste into `main.py`.

### Step 2: Generate ground truth feature JSONs (`generate_gt_json.py`)

For each `.step` ground truth file, extracts geometric features using OCP (Open CASCADE):

```bash
python scripts/generate_gt_json.py                    # all tasks
python scripts/generate_gt_json.py --task tag_name     # single task
python scripts/generate_gt_json.py --force             # regenerate
```

Creates `reference/gt_features.json` for each workpiece containing:
- Volume, bounding box
- Hole histogram (count per diameter)
- Hole details (location, axis, diameter)

> **Prerequisite**: OCP must be available. Install via: `pip install build123d`

### Step 3: Build pos/neg test directories (`setup_test_dirs.py`)

Creates test data for validating the evaluation pipeline:

```bash
python scripts/setup_test_dirs.py
```

- **`output_test_pos/agent_features.json`**: Copy of own `gt_features.json` → score ~1.0
- **`output_test_neg/agent_features.json`**: Copy of different task's `gt_features.json` → low score

## 3. Verification Scripts (Evaluation Phase)

These run during `evaluate()` in `main.py`, not during data construction:

### `extract_features.py` — Feature Extraction

Uses OCP/OCC to analyze a STEP file and extract:
- Global geometry (volume, bounding box)
- Cylindrical features (holes, pins, fillets)
- Hole histogram

Supports both `OCP.*` (from build123d/cadquery) and `OCC.Core.*` (from pythonocc-core) imports.

### `verify_3d.py` — Scoring

Compares agent's extracted features against ground truth using three dimensions:
1. **Global geometry (20%)**: volume error + origin alignment
2. **Feature quantity (30%)**: hole histogram match
3. **Feature precision (50%)**: hole position + axis accuracy

## 4. Script Index

| Script | Phase | Needs OCP | Description |
|---|---|---|---|
| `organize_data.py` | Data prep | No | Restructure raw data into task layout |
| `generate_gt_json.py` | Setup | Yes | Batch-extract GT features to JSON |
| `setup_test_dirs.py` | Setup | No | Create pos/neg test directories |
| `extract_features.py` | Eval | Yes | Extract features from agent's STEP |
| `verify_3d.py` | Eval | No | Score agent vs GT features |

## 5. Extending to New Workpieces

1. Place new `.pdf` + `.step` pair in `manufacturing_raw/结构设计工作流/<NewFolder>/`
2. Re-run `organize_data.py`
3. Re-run `generate_gt_json.py --task <new_tag>`
4. Re-run `setup_test_dirs.py`
5. Add new entry to `VARIANTS` in `main.py`
