# Pitfalls — 2dto3d

> **Task-specific** bugs and surprises only. For generic cross-task issues, contribute to `tasks/guides/KNOWN_ISSUES.md`.

---

## [2026-03-01] OCC Installation — Use OCP, Not pythonocc-core
**Symptom:** `ImportError: No module named OCC` when running extract_features.py
**Cause:** pythonocc-core has no pip wheel and requires conda, which is not available on the VM.
**Fix:** Install `build123d` via pip: `pip install build123d`. This pulls in `cadquery-ocp` which provides equivalent Open CASCADE functionality via `OCP.*` imports (instead of `OCC.Core.*`). The `extract_features.py` script supports both import paths.

## [2026-03-01] OCP Static Methods Use `_s` Suffix
**Symptom:** `AttributeError: 'BRepGProp' has no attribute 'VolumeProperties'`
**Cause:** In OCP (from cadquery), static methods need a `_s` suffix: `BRepGProp.VolumeProperties_s()`, `BRepBndLib.Add_s()`, `TopoDS.Face_s()`.
**Fix:** `extract_features.py` wraps these behind compat shims so the rest of the code uses the same API.

## [2026-03-01] Raw Data Is STEP, Not PRT
**Symptom:** Initial assumption was ground truth files were `.prt` (NX native), but actual files are `.STEP`.
**Cause:** Raw data in `结构设计工作流` uses open STEP format, not proprietary PRT.
**Fix:** All references updated to `.step`. No format conversion needed.
