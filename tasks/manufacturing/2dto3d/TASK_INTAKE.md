# Task Intake — 2dto3d

## 1. Name & Domain
- **Task name:** `tasks/manufacturing/2dto3d/`
- **Category:** manufacturing

## 2. What the Agent Must Do
1. Open Rhino on the remote Windows VM
2. Open / view the engineering drawing PDF (2D blueprint of a workpiece)
3. Study the dimensions, views (front/top/side), and annotations in the PDF
4. Build the corresponding 3D solid model in Rhino from scratch
5. Export the 3D model as a `.step` (STEP) file into the output directory
6. Save and close

**Software used:** Rhinoceros 3D (Rhino 8)

## 3. Input

| File | Format | Remote Path | Notes |
|---|---|---|---|
| Engineering drawing | `.pdf` | `input/<TASK_TAG>.pdf` | 2D blueprint with dimensions and multi-view projections |

**Who prepares:** Pre-existing on VM. Organized from raw data via `scripts/organize_data.py`.

## 4. Output

| File/Directory | Format | Remote Path | Notes |
|---|---|---|---|
| 3D model | `.step` | `output/<TASK_TAG>.step` | Agent's 3D reconstruction exported as STEP |

## 5. Evaluation

**Hard gate conditions:**
- Output `.step` file does not exist → score 0
- Output `.step` file cannot be loaded by OCC → score 0

**Scoring method:**
Three-dimensional comparison using `extract_features.py` (OCC/OCP-based) + `verify_3d.py`:
1. **Global geometry (20%)**: volume error + bounding box origin alignment
2. **Feature quantity (30%)**: hole count histogram (correct number of holes per diameter)
3. **Feature precision (50%)**: hole position accuracy + axis alignment (greedy matching)

Final score normalized to [0.0, 1.0].

**Perfect output:** Agent's STEP file matches GT geometry exactly → score ~1.0
**Wrong/empty output:** Missing file or completely wrong geometry → score 0.0

## 6. Reference Data
Ground-truth `.step` files exist for each workpiece. Pre-processed into `reference/gt_features.json` via `generate_gt_json.py` using OCC/OCP feature extraction.

## 7. Variants
- **Number of variants:** 129 (8 SMA夹具 + 121 半自动电阻焊机)
- **How enumerated:** One folder per workpiece under `C:\Users\User\Desktop\manufacturing\2dto3d\`

## 8. Remote VM
- **VM IP:** 136.117.92.206
- **OS:** Windows
- **Pre-installed software:** Rhinoceros 3D (Rhino 8), Python 3.12.6
- **Python packages needed:** `build123d` (provides OCP), `numpy`, `scipy`
- **Manual setup done:** Data organized, GT features extracted, test dirs created
