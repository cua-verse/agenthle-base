#!/usr/bin/env python3
"""
Upload output_test_pos, output_test_neg, and reference to the remote VM.

Run this before test_eval.sh when using --evaluate-only. The remote VM needs
these folders populated for evaluation to work.

Usage:
  # Set env vars (same as test_eval.sh), then:
  uv run python upload_test_data_to_remote.py

  # Or use the wrapper:
  ./upload_test_data.sh
"""

import asyncio
import os
import re
import sys
from pathlib import Path


def get_env_config():
    """Read config from environment (same as test_eval.sh)."""
    local_task_dir = os.environ.get("LOCAL_TASK_DIR", "")
    if not local_task_dir:
        local_task_dir = str(Path(__file__).resolve().parent)

    # Auto-extract TASK_CATEGORY and TASK_NAME from LOCAL_TASK_DIR
    match = re.search(r"[/\\]tasks[/\\]([^/\\]+)[/\\]([^/\\]+)\s*$", local_task_dir)
    if match:
        task_category = match.group(1)
        task_name = match.group(2)
    else:
        task_category = os.environ.get("TASK_CATEGORY", "tasks")
        task_name = os.environ.get("TASK_NAME", "unknown")

    remote_root = os.environ.get("REMOTE_ROOT_DIR", r"C:\Users\User\Desktop")
    api_url = os.environ.get("CUA_ENV_API_URL", "")
    env_type = os.environ.get("CUA_ENV_TYPE", "windows")

    local_base = Path(local_task_dir).resolve()
    remote_task_dir = f"{remote_root}\\{task_category}\\{task_name}"

    return {
        "local_base": local_base,
        "remote_task_dir": remote_task_dir,
        "api_url": api_url,
        "env_type": env_type,
    }


async def copy_folder_to_remote(session, local_dir: Path, remote_dir: str) -> int:
    """Copy all files from local_dir to remote_dir. Returns count of files copied."""
    if not local_dir.exists() or not local_dir.is_dir():
        return 0

    await session.makedirs(remote_dir)
    count = 0
    for f in local_dir.iterdir():
        if f.is_file():
            content = f.read_bytes()
            remote_path = f"{remote_dir}\\{f.name}"
            await session.write_bytes(remote_path, content)
            print(f"  Copied {f.name} -> {remote_path}")
            count += 1
    return count


async def main():
    cfg = get_env_config()

    if not cfg["api_url"]:
        print("Error: CUA_ENV_API_URL must be set (e.g. from test_eval.sh)")
        sys.exit(1)

    local_base = cfg["local_base"]
    remote_task_dir = cfg["remote_task_dir"]

    folders = ["output_test_pos", "output_test_neg", "reference"]
    local_folders = {name: local_base / name for name in folders}

    print(f"Local task dir: {local_base}")
    print(f"Remote task dir: {remote_task_dir}")
    print()

    from cua_bench.computers.remote import RemoteDesktopSession

    session = RemoteDesktopSession(
        api_url=cfg["api_url"],
        vnc_url=os.environ.get("CUA_ENV_VNC_URL", ""),
        os_type=cfg["env_type"],
    )

    print("Connecting to remote VM...")
    if not await session.wait_until_ready(timeout=300 if cfg["env_type"] == "windows" else 120):
        print("Error: Remote VM did not become ready")
        sys.exit(1)
    print("Connected.\n")

    total = 0
    for name in folders:
        local_path = local_folders[name]
        remote_path = f"{remote_task_dir}\\{name}"
        print(f"Uploading {name}...")
        n = await copy_folder_to_remote(session, local_path, remote_path)
        if n == 0:
            if local_path.exists():
                print(f"  (folder empty)")
            else:
                print(f"  (folder not found, skipped)")
        else:
            print(f"  -> {n} file(s)")
        total += n

    print(f"\nDone. Uploaded {total} files total.")


if __name__ == "__main__":
    asyncio.run(main())
