"""
organize_data.py — Data pipeline script (runs on remote Windows VM)

Restructures raw workpiece data from the unstructured source directory into
the standard AgentHLE task layout.

Source layout:
    C:\\Users\\User\\Desktop\\manufacturing_raw\\结构设计工作流\\
    ├── <WorkpieceFolder>\\
    │   ├── <name>.pdf         ← engineering drawing
    │   └── <name>.prt         ← ground truth 3D model

Target layout:
    C:\\Users\\User\\Desktop\\manufacturing\\2dto3d\\
    ├── <task_tag>\\
    │   ├── input\\
    │   │   └── <task_tag>.pdf
    │   ├── output\\              (empty, agent writes here)
    │   ├── reference\\
    │   │   └── <task_tag>.prt
    │   └── software\\
    │       └── Rhino.lnk        (created separately)

Usage:
    python organize_data.py                  # real run
    python organize_data.py --dry-run        # preview only
    python organize_data.py --rhino-path "C:\\path\\to\\rhino.exe"  # create shortcut

Prerequisites:
    Run on the remote Windows VM where the raw data resides.
"""

import os
import shutil
import argparse
import re


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
RAW_DATA_ROOT = r"C:\Users\User\Desktop\manufacturing_raw\结构设计工作流"
TARGET_ROOT = r"C:\Users\User\Desktop\manufacturing\2dto3d"

# Default Rhino path (adjust if different)
DEFAULT_RHINO_PATH = r"C:\Program Files\Rhino 8\System\Rhino.exe"


def sanitize_tag(name):
    """Convert a folder/file name to a safe task tag.

    Rules:
    - Replace spaces, hyphens, and special chars with underscores
    - Remove consecutive underscores
    - Strip leading/trailing underscores
    """
    tag = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    tag = re.sub(r'_+', '_', tag)
    tag = tag.strip('_')
    return tag


def discover_workpieces(raw_root):
    """Scan raw data directory and discover workpiece folders.

    Returns list of dicts with:
    - raw_folder: absolute path to raw folder
    - folder_name: original folder name
    - task_tag: sanitized tag
    - pdf_path: path to .pdf file (or None)
    - prt_path: path to .prt file (or None)
    """
    workpieces = []

    if not os.path.exists(raw_root):
        print(f"ERROR: Raw data root not found: {raw_root}")
        return workpieces

    for entry in sorted(os.listdir(raw_root)):
        folder_path = os.path.join(raw_root, entry)
        if not os.path.isdir(folder_path):
            continue

        # Scan for .pdf and .prt files
        pdf_files = []
        prt_files = []

        for fname in os.listdir(folder_path):
            lower = fname.lower()
            if lower.endswith('.pdf'):
                pdf_files.append(os.path.join(folder_path, fname))
            elif lower.endswith('.prt'):
                prt_files.append(os.path.join(folder_path, fname))

        # Also check subdirectories (some raw data may be nested)
        for sub_entry in os.listdir(folder_path):
            sub_path = os.path.join(folder_path, sub_entry)
            if os.path.isdir(sub_path):
                for fname in os.listdir(sub_path):
                    lower = fname.lower()
                    if lower.endswith('.pdf'):
                        pdf_files.append(os.path.join(sub_path, fname))
                    elif lower.endswith('.prt'):
                        prt_files.append(os.path.join(sub_path, fname))

        if not pdf_files and not prt_files:
            print(f"  SKIP: {entry} -- no .pdf or .prt found")
            continue

        # Use the folder name as the base, or the filename if only one
        task_tag = sanitize_tag(entry)

        workpieces.append({
            "raw_folder": folder_path,
            "folder_name": entry,
            "task_tag": task_tag,
            "pdf_files": pdf_files,
            "prt_files": prt_files,
        })

    return workpieces


def create_rhino_shortcut(target_dir, rhino_path):
    """Create a Rhino.lnk shortcut in the target directory."""
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        lnk_path = os.path.join(target_dir, "Rhino.lnk")
        lnk = shell.CreateShortcut(lnk_path)
        lnk.TargetPath = rhino_path
        lnk.Save()
        return True
    except Exception as e:
        print(f"  WARN: Could not create Rhino shortcut: {e}")
        return False


def organize(dry_run=False, rhino_path=None):
    """Main organization pipeline."""
    print("=" * 60)
    print("2D-to-3D Task -- Data Organization Pipeline")
    print(f"{'[DRY RUN] ' if dry_run else ''}")
    print(f"Source: {RAW_DATA_ROOT}")
    print(f"Target: {TARGET_ROOT}")
    print("=" * 60)

    workpieces = discover_workpieces(RAW_DATA_ROOT)
    print(f"\nDiscovered {len(workpieces)} workpiece folders\n")

    results = []

    for wp in workpieces:
        tag = wp["task_tag"]
        task_dir = os.path.join(TARGET_ROOT, tag)

        print(f"\n[{tag}] (from: {wp['folder_name']})")
        print(f"  PDFs: {len(wp['pdf_files'])}, PRTs: {len(wp['prt_files'])}")

        if not wp["pdf_files"]:
            print(f"  SKIP: no PDF found")
            continue
        if not wp["prt_files"]:
            print(f"  SKIP: no PRT found (no ground truth)")
            continue

        input_dir = os.path.join(task_dir, "input")
        output_dir = os.path.join(task_dir, "output")
        reference_dir = os.path.join(task_dir, "reference")
        software_dir = os.path.join(task_dir, "software")

        if not dry_run:
            os.makedirs(input_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(reference_dir, exist_ok=True)
            os.makedirs(software_dir, exist_ok=True)

        # Copy PDF(s) to input/
        for pdf_path in wp["pdf_files"]:
            pdf_basename = os.path.basename(pdf_path)
            # Rename to task_tag.pdf if only one PDF
            if len(wp["pdf_files"]) == 1:
                dst_name = f"{tag}.pdf"
            else:
                dst_name = sanitize_tag(os.path.splitext(pdf_basename)[0]) + ".pdf"
            dst = os.path.join(input_dir, dst_name)
            print(f"  COPY PDF: {pdf_basename} -> input/{dst_name}")
            if not dry_run:
                shutil.copy2(pdf_path, dst)

        # Copy PRT(s) to reference/
        for prt_path in wp["prt_files"]:
            prt_basename = os.path.basename(prt_path)
            if len(wp["prt_files"]) == 1:
                dst_name = f"{tag}.prt"
            else:
                dst_name = sanitize_tag(os.path.splitext(prt_basename)[0]) + ".prt"
            dst = os.path.join(reference_dir, dst_name)
            print(f"  COPY PRT: {prt_basename} -> reference/{dst_name}")
            if not dry_run:
                shutil.copy2(prt_path, dst)

        # Create Rhino shortcut
        if rhino_path and not dry_run:
            create_rhino_shortcut(software_dir, rhino_path)
            print(f"  SHORTCUT: Rhino.lnk in software/")

        results.append({
            "task_tag": tag,
            "folder_name": wp["folder_name"],
            "pdf_count": len(wp["pdf_files"]),
            "prt_count": len(wp["prt_files"]),
        })

    print("\n" + "=" * 60)
    print(f"Organized {len(results)} workpieces")
    print("=" * 60)

    # Print VARIANTS list for main.py
    print("\n# Paste this into main.py VARIANTS list:")
    print("VARIANTS = [")
    for r in results:
        print(f'    ("{r["task_tag"]}", "{r["folder_name"]}"),')
    print("]")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Organize raw 2D-to-3D task data into AgentHLE structure"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview operations without copying files",
    )
    parser.add_argument(
        "--rhino-path",
        default=DEFAULT_RHINO_PATH,
        help=f"Path to Rhino executable (default: {DEFAULT_RHINO_PATH})",
    )
    args = parser.parse_args()
    organize(dry_run=args.dry_run, rhino_path=args.rhino_path)
