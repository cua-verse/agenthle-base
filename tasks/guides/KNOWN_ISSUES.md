# Known Issues — Cross-Task Pitfalls

> Maintained by agents across all tasks. If you find a non-obvious bug or quirk that could affect future tasks, add it here.

---

## Windows / Encoding

### GBK Encoding for Chinese Windows Apps
**Affects:** Any script that writes files consumed by apps with Chinese locale (e.g., PowerMill macros, NX scripts)
**Symptom:** App reads the file but produces garbled output or silently fails.
**Fix:** Use `encoding="gbk"` instead of `"utf-8"` when writing those files.
```python
await iface.write_text(r"C:\path\to\macro.mac", content, encoding="gbk")
```

---

## Windows / Shortcuts

### PowerShell Shortcut Creation is Unreliable
**Symptom:** PowerShell `WScript.Shell` commands with nested quotes fail silently.
**Fix:** Always create shortcuts via a Python script using `win32com.client`:
```python
import win32com.client
shell = win32com.client.Dispatch("WScript.Shell")
lnk = shell.CreateShortcut(r"C:\path\to\App.lnk")
lnk.TargetPath = r"C:\path\to\app.exe"
lnk.Save()
```

---

## session API

### `session.run_command()` Return Format
The return value is a dict, not an object:
```python
result = await session.run_command("python script.py")
# Use: result["stdout"], result["stderr"], result["return_code"]
# NOT: result.stdout
```

### `session.copy_file()` on Application Project Folders
Some apps (e.g., PowerMill) leave lock files inside project folders.
Copying a locked project may fail or produce a corrupted copy.
**Fix:** Delete the lock file before copying.

---

## Testing Framework

### `--evaluate-only` Skips `start()`
When running `test_eval_local.sh` with `--evaluate-only`, the `start()` function is never called. The VM state is whatever it was — no cleanup, no setup. Ensure pos/neg test dirs are pre-populated manually before running.

### Default Task Index is 0
`BATCH_TASK_INDEX` defaults to `0`. Only the first variant is tested unless you pass `--task-index N` or loop in the script.

### `REMOTE_OUTPUT_DIR` Must Match What's on the VM
If `REMOTE_OUTPUT_DIR=output_test_pos` but the VM doesn't have that folder, `evaluate()` will silently score 0. Always verify the dir exists on the VM before running the test.

---

## Evaluation Script Design

### Don't Use `print()` for Anything But the JSON Result
If your eval script prints anything other than the JSON result object, `json.loads(result["stdout"])` in `main.py` will fail.
**Fix:** Use `sys.stderr.write()` for debug logs, `print(json.dumps(result))` for the final output only.
