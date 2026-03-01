# Pitfalls — gcode

Task-specific bugs and surprises found during implementation.
For cross-task general issues, see `tasks/guides/KNOWN_ISSUES.md`.

---

## [2026-03-01] PowerMill macros require GBK encoding
**Symptom:** Macro runs but produces garbled text or silently fails on the Chinese Windows VM.
**Cause:** PowerMill on a Chinese locale Windows expects GBK-encoded `.mac` files.
**Fix:** Always write macro files with `encoding="gbk"`:
```python
await iface.write_text(r"C:\tmp\macro.mac", macro_content, encoding="gbk")
```

---

## [2026-03-01] PowerShell shortcut creation fails with nested quotes
**Symptom:** PowerShell `WScript.Shell` commands with arguments that have nested single/double quotes fail silently or produce an empty `.lnk`.
**Fix:** Use a Python script with `win32com.client` instead. Uploaded as `/tmp/create_shortcuts_v2.py`.

---

## [2026-03-01] Remote `scripts/` directory should NOT exist on VM
**Context:** Early in the session, a `scripts/` directory was created on the remote VM. The user later deleted it.
**Rule:** All scripts live in the local codebase (`tasks/manufacturing/gcode/scripts/`). During `evaluate()`, they are uploaded to a temp folder at runtime. Never deploy a permanent `scripts/` dir to the VM.

---

## [2026-03-01] `generate_ref_stls.py` must run with PowerMill already open
**Symptom:** Script fails with COM error `"PowerMill not found"` or `"Cannot connect to server"`.
**Cause:** `win32com.client.GetActiveObject("pmill.Document")` requires an already-running PowerMill instance.
**Fix:** Always open PowerMill manually before running `generate_ref_stls.py`. Tell the user to open it and confirm before starting the script.

---

## [2026-03-01] MDBZDHZJ25 task has mixed underscore/hyphen naming
**Symptom:** `copy_references.py` fails to find the reference PM project for `MDBZDHZJ25_SKC_1_NCSM_T`.
**Cause:** The task folder uses underscores (`MDBZDHZJ25_SKC_1_NCSM_T`) but the PM project inside is named with a hyphen (`MDBZDHZJ25_SKC-1_NCSM_T`).
**Fix:** The `VARIANTS` list in `main.py` explicitly maps each task tag to its PM project folder name:
```python
("MDBZDHZJ25_SKC_1_NCSM_T", "MDBZDHZJ25_SKC-1_NCSM_T"),
```

---

## [2026-03-01] `verify_stl.py` must print only JSON to stdout
**Symptom:** `json.loads(result["stdout"])` throws a parse error in `evaluate()`.
**Cause:** Debug `print()` statements in the script pollute stdout.
**Fix:** Use `sys.stderr.write()` for all debug output. Only `print(json.dumps(result))` to stdout.
