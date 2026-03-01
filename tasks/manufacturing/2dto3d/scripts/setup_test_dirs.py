"""
setup_test_dirs.py — One-time setup (runs on remote Windows VM)

Creates output_test_pos/ and output_test_neg/ directories for each task,
populated with test feature JSON files for validating the evaluation pipeline:

  output_test_pos/agent_features.json
      Copy of the task's own gt_features.json.
      Self-comparison should produce score ~1.0.

  output_test_neg/agent_features.json
      Copy of a DIFFERENT task's gt_features.json (round-robin assignment).
      Cross-workpiece comparison should produce a low score.

Prerequisites:
    generate_gt_json.py must have been run first to create all gt_features.json files.

Usage:
    python setup_test_dirs.py            # create all test dirs
    python setup_test_dirs.py --dry-run  # preview only
"""

import os
import shutil
import argparse

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
TASK_ROOT = r"C:\Users\User\Desktop\manufacturing\2dto3d"


def discover_task_tags(task_root):
    """Find all task tags that have gt_features.json."""
    tags = []
    if not os.path.exists(task_root):
        print(f"ERROR: Task root not found: {task_root}")
        return tags

    for tag in sorted(os.listdir(task_root)):
        task_dir = os.path.join(task_root, tag)
        gt_json = os.path.join(task_dir, "reference", "gt_features.json")
        if os.path.isdir(task_dir) and os.path.exists(gt_json):
            tags.append(tag)

    return tags


def setup_test_dirs(dry_run=False):
    """Create positive and negative test directories for all tasks."""
    print("=" * 60)
    print("2D-to-3D Task -- Setup Test Directories")
    print(f"{'[DRY RUN] ' if dry_run else ''}")
    print("=" * 60)

    task_tags = discover_task_tags(TASK_ROOT)
    n = len(task_tags)
    print(f"\nDiscovered {n} tasks with gt_features.json\n")

    if n == 0:
        print("ERROR: No tasks found. Run generate_gt_json.py first.")
        return

    for i, task_tag in enumerate(task_tags):
        task_dir = os.path.join(TASK_ROOT, task_tag)

        # Positive source: this task's own GT features
        gt_json = os.path.join(task_dir, "reference", "gt_features.json")

        # Negative source: next task's GT features (wraps around)
        neg_source_tag = task_tags[(i + 1) % n]
        neg_json = os.path.join(TASK_ROOT, neg_source_tag, "reference", "gt_features.json")

        # Destination paths
        pos_dir = os.path.join(task_dir, "output_test_pos")
        neg_dir = os.path.join(task_dir, "output_test_neg")
        pos_dst = os.path.join(pos_dir, "agent_features.json")
        neg_dst = os.path.join(neg_dir, "agent_features.json")

        print(f"\n[{task_tag}]")
        print(f"  pos src: {gt_json}")
        print(f"  neg src: {neg_json} (from {neg_source_tag})")

        # Validate sources exist
        if not os.path.exists(gt_json):
            print(f"  WARN: gt_features.json not found -- run generate_gt_json.py first")
            continue

        if not os.path.exists(neg_json):
            print(f"  WARN: neg source not found ({neg_source_tag})")
            continue

        if not dry_run:
            os.makedirs(pos_dir, exist_ok=True)
            os.makedirs(neg_dir, exist_ok=True)
            shutil.copy2(gt_json, pos_dst)
            shutil.copy2(neg_json, neg_dst)

        print(f"  OK pos: {pos_dst}")
        print(f"  OK neg: {neg_dst}")

    print("\n" + "=" * 60)
    print("Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create positive and negative test directories for all 2D-to-3D tasks"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview operations without copying files",
    )
    args = parser.parse_args()
    setup_test_dirs(dry_run=args.dry_run)
