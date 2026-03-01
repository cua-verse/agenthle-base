# Task Intake — gcode

## 1. Name & Domain
- **Task name:** `tasks/manufacturing/gcode/`
- **Category:** manufacturing

## 2. What the Agent Must Do
1. Open Autodesk PowerMill 2025 on the remote Windows VM
2. Load a blank PowerMill project (pre-configured tools, zero toolpaths)
3. Study the ideal workpiece geometry (`.prt` file) and reference image (`.jpg`)
4. Design toolpaths (roughing + finishing) to machine the workpiece from raw stock
5. Ensure toolpaths have NO collisions and NO gouging
6. Run a stock model simulation to verify
7. Save the PowerMill project (Ctrl+S)

**Software used:** Autodesk PowerMill 2025

## 3. Input

| File | Format | Remote Path | Notes |
|---|---|---|---|
| Blank PM project | PowerMill folder | `input/<PM_PROJECT_NAME>/` | Pre-configured tools, zero toolpaths |
| Ideal workpiece | `.prt` (NX) | `input/<TASK_TAG>.prt` | Color-coded faces = precision zones |
| Reference image | `.jpg` | `input/<TASK_TAG>.jpg` | Visual reference |

**Who prepares:** Pre-existing on the VM. Blank projects were derived from expert projects by deleting all toolpaths (via `delete_toopath.py`).

## 4. Output

| File/Directory | Format | Remote Path | Notes |
|---|---|---|---|
| Modified PM project | PowerMill folder | `output/<PM_PROJECT_NAME>/` | Agent's designed toolpaths |

## 5. Evaluation

**Hard gate conditions:**
- Any collision detected → score 0
- Any gouge detected → score 0

**Scoring method:** Point-to-mesh distance comparison between agent's simulated stock model STL and expert's reference stock model STL. Score = weighted combination of fraction-within-tolerance bands.

**Perfect output:** Agent's stock model is identical to expert's → score 1.0 (mean distance = 0mm)
**Wrong output:** Completely different workpiece geometry → score < 0.2 (mean distance ~20mm)

## 6. Reference Data
Expert CAM engineers designed toolpaths for each workpiece. Their PM projects were simulated in PowerMill to produce `reference/reference_sim.stl`. We compare against this expert result, not the ideal `.prt` part, because the ideal part has intentional leave-stock (余量) encoded via color specs that we can't easily parse automatically.

## 7. Variants
- **Number of variants:** 15
- **How enumerated:** One folder per workpiece under `C:\Users\User\Desktop\manufacturing\gcode\`

## 8. Remote VM
- **VM IP:** 34.168.192.143
- **OS:** Windows
- **Pre-installed software:** Autodesk PowerMill 2025, Python 3.x
- **Python packages needed:** `trimesh`, `numpy`, `pywin32`
- **Manual setup done:** Reference STLs generated, pos/neg test dirs created, PM shortcuts in `software/`
