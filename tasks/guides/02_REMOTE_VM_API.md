# Guide 02 — Remote VM API

> **When to read:** When exploring the remote VM, writing data pipeline scripts, or writing eval scripts that run on the VM.

> ⛔ **DATA SAFETY:** NEVER delete user data, `input/`, `reference/`, or `software/` directories on the remote VM. Only delete files/folders you explicitly created (temp scripts, test outputs). When in doubt, ask the user.

> ⚠️ **Python interpreter:** Always use `python` (not `python3`, not `conda run`) on both local and remote machines.

---

## Connecting for Exploration

Use this pattern in a scratch notebook or `/tmp/explore.py`:

```python
import asyncio
from cua_bench.computers.remote import RemoteDesktopSession

IP = "<VM_IP>"
session = RemoteDesktopSession(api_url=f"http://{IP}:5000", os_type="windows")
await session.start()

# Use the low-level interface for exploration
iface = session._computer.interface
```

> **Scratch files:** Put all exploration code in `/tmp/`. If a script is valuable and needs to be reproducible, move it to `tasks/<category>/<task_name>/scripts/`.

---

## `interface.*` — Low-Level Computer SDK

Use `session._computer.interface` for:
- Direct exploration, debugging
- Running scripts on the VM from outside `main.py`
- Any operation not covered by the high-level `session` API

### File System

```python
# List / check
files = await iface.list_dir(r"C:\Users\User\Desktop")
exists = await iface.file_exists(r"C:\path\to\file.txt")
exists = await iface.directory_exists(r"C:\path\to\dir")
size   = await iface.get_file_size(r"C:\path\to\file")

# Read / write text
content = await iface.read_text(r"C:\path\to\file.txt")
await iface.write_text(r"C:\path\to\file.txt", "content", encoding="utf-8")

# Read / write bytes
data = await iface.read_bytes(r"C:\path\to\file.bin")
await iface.write_bytes(r"C:\path\to\file.bin", data)

# Create / delete
await iface.create_dir(r"C:\path\to\new_dir")
await iface.delete_file(r"C:\path\to\file.txt")
await iface.delete_dir(r"C:\path\to\dir")       # removes recursively
```

> ⚠️ **Encoding pitfall:** If writing files for Chinese Windows apps (e.g., PowerMill macros), use `encoding="gbk"`.

### Running Commands

```python
result = await iface.run_command("python C:\\path\\to\\script.py --arg value")
print(result.stdout)
print(result.stderr)
print(result.returncode)  # 0 = success
```

### Mouse & Keyboard (GUI interaction)

```python
screenshot_bytes = await iface.screenshot()     # PNG bytes

await iface.left_click(x, y)
await iface.double_click(x, y)
await iface.right_click(x, y)
await iface.move_cursor(x, y)
await iface.drag_to(x, y, duration=0.5)
await iface.scroll(0, -3)                       # negative y = scroll down

await iface.type_text("Hello World")
await iface.press("enter")                      # or Key.ENTER
await iface.hotkey("ctrl", "s")
```

### Clipboard

```python
text = await iface.copy_to_clipboard()
await iface.set_clipboard("text to paste")
```

### Window Management

```python
wid = await iface.get_current_window_id()
title = await iface.get_window_title(wid)
await iface.activate_window(wid)
await iface.maximize_window(wid)
await iface.close_window(wid)
```

> **Full reference:** `submodules/cua/docs/content/docs/cua/reference/computer-sdk/index.mdx`

---

## `session.*` — High-Level API (for use in `main.py`)

In `start()` and `evaluate()`, use the high-level session methods. Do not use `session._computer.interface` inside `main.py`.

```python
# File system
await session.makedirs(path)
await session.remove_file(path)          # removes file or directory
await session.copy_file(src, dst)
await session.move_file(src, dst)
exists = await session.exists(path)
files  = await session.list_dir(path)

# Text / binary files
await session.write_file(path, text)
text = await session.read_file(path)
await session.write_bytes(path, data)
data = await session.read_bytes(path)

# Commands
result = await session.run_command("python script.py", timeout=120.0)
# result: {"success": bool, "stdout": str, "stderr": str, "return_code": int}

# Opening files / launching apps
await session.run_file(r"C:\path\to\file.exe")          # open with default app
await session.launch_application(r"C:\path\to\app.exe")
```

> **Full reference:** `agenthle-homepage/docs/program/appendix_SESSION_COMMANDS.md`

---

## Long-Running Scripts

When a VM script will take >30s (e.g., batch processing data for all variants):

1. Write the script to `tasks/<category>/<task_name>/scripts/<name>.py`
2. Upload it: `await iface.write_text(r"C:\tmp\<name>.py", script_content)`
3. Tell the user to run it and report back: **hand back control**
4. Resume once the user confirms it finished

Do not try to `await` a long-running command inline — it will time out.

> ⚠️ **Cleanup:** After development is finished, delete all temp scripts you uploaded to `C:\tmp\` or `C:\Users\User\AppData\Local\Temp\`. Do not leave debris on the VM.

---

## Creating Windows Shortcuts

```python
shortcut_script = r"""
import win32com.client
shell = win32com.client.Dispatch("WScript.Shell")
lnk = shell.CreateShortcut(r"C:\path\to\software\App.lnk")
lnk.TargetPath = r"C:\path\to\app.exe"
lnk.Save()
"""
await iface.write_text(r"C:\tmp\create_shortcut.py", shortcut_script)
await iface.run_command(r"python C:\tmp\create_shortcut.py")
```

> ⚠️ Do not use PowerShell for shortcut creation — quoting issues make it unreliable. Always use a Python script.

---

## Installing Python Packages on the VM

```python
result = await iface.run_command("pip install trimesh numpy pywin32")
```
