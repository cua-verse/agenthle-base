# Task Intake - <task_name>

> Fill this out before any implementation begins. Use this together with `DATA_INTAKE.md` and `scripts/DATA_PIPELINE.md`.

## 1. Name & Domain

- **Task name:** <!-- will become tasks/<category>/<task_name>/ -->
- **Category:** <!-- e.g., manufacturing, game, productivity, web -->

## 2. What the Agent Must Do

1.
2.
3.

**Software used:** <!-- e.g., Autodesk PowerMill 2025, Excel, Blender -->

## 3. Input

| File | Format | Remote Path | Notes |
|---|---|---|---|
| | | | |

**Who prepares this input?** <!-- Already on VM? Produced by scripts/DATA_PIPELINE.md? -->

## 4. Output

| File/Directory | Format | Remote Path | Notes |
|---|---|---|---|
| | | `output/...` | |

## 5. Evaluation

**Hard gate conditions** (auto score=0 if triggered):

- <!-- e.g., any collision detected -> 0 -->

**Scoring method:**

<!-- How to compute a score between 0.0 and 1.0? File diff? Metric? Structured comparison? -->

**What does a PERFECT output look like?**

<!-- Score should be ~1.0 -->

**What does a WRONG/empty output look like?**

<!-- Score should be ~0.0 -->

## 6. Reference Data

<!-- Is there an expert/ground-truth reference to compare against? -->
<!-- Where is it? Was it provided directly or generated through the data pipeline? -->

## 7. Variants

- **Number of variants:**
- **How enumerated:** <!-- e.g., one folder per workpiece under gcode/ -->

## 8. Remote VM

- **VM IP:**
- **OS:** <!-- windows / linux -->
- **Pre-installed software:**
- **Manual setup already done:**
