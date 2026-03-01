"""
generate_gt_json.py — Pre-extract ground truth features (runs on remote Windows VM)

For each workpiece's ground truth .prt file, runs the OCC feature extraction
pipeline and saves the result as reference/gt_features.json.

This pre-computation step avoids running OCC on the GT during every evaluation.
The gt_features.json is then used by verify_3d.py as the comparison reference.

Prerequisites:
    - organize_data.py must have been run first
    - pythonocc-core must be installed (conda install -c conda-forge pythonocc-core)

Usage:
    python generate_gt_json.py                        # process all
    python generate_gt_json.py --task workpiece_A     # single task
    python generate_gt_json.py --force                # regenerate existing
    python generate_gt_json.py --dry-run              # preview only
"""

import os
import sys
import json
import argparse

# Add the scripts directory to path so we can import extract_features
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from extract_features import StepFeatureExtractor

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
TASK_ROOT = r"C:\Users\User\Desktop\manufacturing\2dto3d"


def discover_tasks(task_root):
    """Find all task directories that have a reference .prt file."""
    tasks = []
    if not os.path.exists(task_root):
        print(f"ERROR: Task root not found: {task_root}")
        return tasks

    for tag in sorted(os.listdir(task_root)):
        task_dir = os.path.join(task_root, tag)
        if not os.path.isdir(task_dir):
            continue

        ref_dir = os.path.join(task_dir, "reference")
        if not os.path.exists(ref_dir):
            continue

        # Find .prt files in reference/
        prt_files = [
            f for f in os.listdir(ref_dir) if f.lower().endswith(".prt")
        ]
        if not prt_files:
            continue

        tasks.append({
            "task_tag": tag,
            "reference_dir": ref_dir,
            "prt_file": os.path.join(ref_dir, prt_files[0]),
            "gt_json": os.path.join(ref_dir, "gt_features.json"),
        })

    return tasks


def generate_gt_features(task_filter=None, force=False, dry_run=False):
    """Generate gt_features.json for all (or filtered) tasks."""
    print("=" * 60)
    print("2D-to-3D Task -- Generate Ground Truth Features")
    print(f"{'[DRY RUN] ' if dry_run else ''}")
    print("=" * 60)

    tasks = discover_tasks(TASK_ROOT)
    print(f"\nDiscovered {len(tasks)} tasks with GT .prt files\n")

    if task_filter:
        tasks = [t for t in tasks if t["task_tag"] == task_filter]
        if not tasks:
            print(f"ERROR: Task '{task_filter}' not found")
            return

    success = 0
    failed = 0

    for task in tasks:
        tag = task["task_tag"]
        prt = task["prt_file"]
        gt_json = task["gt_json"]

        print(f"\n[{tag}]")
        print(f"  PRT: {prt}")

        if os.path.exists(gt_json) and not force:
            print(f"  SKIP: gt_features.json already exists (use --force to overwrite)")
            success += 1
            continue

        if dry_run:
            print(f"  WOULD CREATE: {gt_json}")
            continue

        try:
            extractor = StepFeatureExtractor(prt)
            report = extractor.generate_report()

            with open(gt_json, "w") as f:
                json.dump(report, f, indent=2)

            hole_count = report["features"]["hole_count_unique"]
            volume = report["geometry"]["volume"]
            print(f"  OK: {hole_count} holes, volume={volume:.1f}")
            print(f"  SAVED: {gt_json}")
            success += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Done: {success} success, {failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate gt_features.json for all 2D-to-3D tasks"
    )
    parser.add_argument(
        "--task", help="Process only this task tag"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate existing gt_features.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview operations without running extraction",
    )
    args = parser.parse_args()
    generate_gt_features(
        task_filter=args.task, force=args.force, dry_run=args.dry_run
    )
