"""
copy_references.py — One-time setup script (runs on remote Windows VM)

Copies each expert reference PowerMill project from the raw data directory
(manufacturing_raw) into the corresponding task's reference/ subdirectory.
Also removes PowerMill lockfiles which would prevent re-opening the project.

Usage:
    python copy_references.py            # actually copy
    python copy_references.py --dry-run  # preview only, no file operations
"""

import os
import shutil
import argparse

# ---------------------------------------------------------------------------
# Path constants — adjust these if raw data is stored elsewhere
# ---------------------------------------------------------------------------
RAW_ROOT = r"C:\Users\User\Desktop\manufacturing_raw\G代码工作流\PM"
TASK_ROOT = r"C:\Users\User\Desktop\manufacturing\gcode"

# ---------------------------------------------------------------------------
# Mapping: task_tag -> (workpiece_family, pm_project_folder_name)
#
# The task_tag is the directory name under TASK_ROOT (e.g., "125162_319").
# The workpiece_family is the top-level folder under RAW_ROOT (e.g., "125162").
# The pm_project_folder_name is the subfolder under {workpiece}/CNC/.
# ---------------------------------------------------------------------------
TASK_TO_REF_PM = {
    "125162_319": ("125162", "125162-319-NCFM-T"),
    "A125117_301": ("A125117", "A125117-301-NCSM-B"),
    "A125138_301": ("A125138", "A125138-301-NCFM-T"),
    "A125138_302": ("A125138", "A125138-302-NCSM-B"),
    "MDBZDHZJ25_SKC_1_NCSM_T": ("MDBZDHZJ25", "MDBZDHZJ25_SKC-1_NCSM_T"),
    "MR250692C00_M2": ("MR250692C00", "MR250692C00-M2-NCFM-T"),
    "MR250696C00_F1": ("MR250696C00", "MR250696C00-F1-NCSM-B"),
    "MR250696C00_S5": ("MR250696C00", "MR250696C00-S5-NCSM-T"),
    "MR250697C00_M1": ("MR250697C00", "MR250697C00-M1-NCFM-B"),
    "MR250697C00_S1": ("MR250697C00", "MR250697C00-S1-NCSM-B"),
    "MR250697C00_S2": ("MR250697C00", "MR250697C00-S2-NCFM-T"),
    "MR250698C00_F3": ("MR250698C00", "MR250698C00-F3-NCSM-B"),
    "MR250698C00_P6": ("MR250698C00", "MR250698C00-P6-NCSM-B"),
    "MR250698C00_U005": ("MR250698C00", "MR250698C00-U005-NCFM-L"),
    "T29153_050": ("T29153", "T29153-050-NCRM-F"),
}


def copy_references(dry_run: bool = False):
    """Iterate over all task mappings and copy reference PM projects."""
    print("=" * 60)
    print("GCode Task -- Copy Reference PM Projects")
    print(f"{'[DRY RUN] ' if dry_run else ''}Task root: {TASK_ROOT}")
    print("=" * 60)

    success_count = 0
    skip_count = 0
    error_count = 0

    for task_tag, (workpiece, pm_proj_name) in TASK_TO_REF_PM.items():
        # Build source path: raw_root / workpiece / CNC / pm_project
        src_pm = os.path.join(RAW_ROOT, workpiece, "CNC", pm_proj_name)
        # Build destination path: task_root / task_tag / reference / ref_pm_project
        dst_ref_dir = os.path.join(TASK_ROOT, task_tag, "reference")
        dst_pm = os.path.join(dst_ref_dir, "ref_pm_project")

        print(f"\n[{task_tag}]")
        print(f"  src: {src_pm}")
        print(f"  dst: {dst_pm}")

        # Validate source exists
        if not os.path.exists(src_pm):
            print(f"  WARNING: SOURCE NOT FOUND -- skipping")
            error_count += 1
            continue

        # Skip if destination already exists (checkpoint mechanism)
        if os.path.exists(dst_pm):
            print(f"  OK: Already exists -- skipping")
            skip_count += 1
            continue

        if dry_run:
            print(f"  [DRY RUN] Would copy")
            success_count += 1
            continue

        try:
            os.makedirs(dst_ref_dir, exist_ok=True)
            # Copy entire PM project directory tree
            shutil.copytree(src_pm, dst_pm)
            # Remove PowerMill lockfile if present — PM creates these on open,
            # and they block any subsequent attempt to open the project.
            lockfile = os.path.join(dst_pm, "lockfile")
            if os.path.exists(lockfile):
                os.remove(lockfile)
                print(f"  (removed lockfile)")
            print(f"  OK: Copied successfully")
            success_count += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            error_count += 1

    print("\n" + "=" * 60)
    print(f"Done: {success_count} copied, {skip_count} skipped, {error_count} errors")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Copy expert reference PM projects into each task's reference/ folder"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview operations without actually copying files"
    )
    args = parser.parse_args()
    copy_references(dry_run=args.dry_run)
