# Guide 05 — Documentation Conventions

> **When to read:** Throughout the task — when creating docs, before committing, and when handing off.

---

## Per-Task Living Documents

Each task folder has these docs, scaffolded from `tasks/guides/templates/`:

| File | Copied from | Purpose | When to update |
|---|---|---|---|
| `TASK_INTAKE.md` | `templates/TASK_INTAKE.md` | User fills this to define the task | Phase 1 — before implementation |
| `CONTEXT.md` | `templates/CONTEXT.md` | Running state: decisions, progress, paths, session log | End of every session |
| `PITFALLS.md` | `templates/PITFALLS.md` | **Task-specific** bugs and surprises only | As bugs are found |

### What Goes Where — PITFALLS.md vs KNOWN_ISSUES.md

| Scope | File | Example |
|---|---|---|
| Specific to this task | `<task>/PITFALLS.md` | "MDBZDHZJ25 has mixed underscore/hyphen naming in PM project" |
| Generic, affects any task | `guides/KNOWN_ISSUES.md` | "PowerShell shortcut creation fails with nested quotes" |

> **When you find a generic bug:** add it to `guides/KNOWN_ISSUES.md` right away. Don't wait until the end.

---

## Task Folder Structure (What to Commit)

```
tasks/<category>/<task_name>/
  main.py               ← COMMIT — core implementation
  TASK_INTAKE.md         ← COMMIT — filled-in task definition
  CONTEXT.md             ← COMMIT — running state & decisions
  PITFALLS.md            ← COMMIT — task-specific gotchas
  README.md              ← COMMIT — reviewer onboarding (write in Phase 6)
  scripts/
    *.py                 ← COMMIT — all scripts that run on the VM
    DATA_PIPELINE.md     ← COMMIT — how data was constructed
```

**Do NOT commit:**
- `input/`, `output/`, `reference/`, `software/` contents (large binaries, stay on VM)
- `test_eval_local.sh` / `test_launch_local.sh` (credentials)
- `/tmp/` scratch files

> ⚠️ **Cleanup obligation:** Before wrapping up development, delete all temp files you created in `/tmp/` (local) and `C:\tmp\` / `C:\Users\User\AppData\Local\Temp\` (remote). Do not leave scratch scripts behind.

---

## `README.md` — Written in Phase 6 (Required Sections)

```markdown
# <Task Name>

## Overview
## Input / Output
## Evaluation Pipeline
## Remote Directory Structure
## Environment Setup
## Script Index
```

## `scripts/DATA_PIPELINE.md` — Written After Data Pipeline (Required Sections)

```markdown
# Data Pipeline — <task_name>

## Raw Data
## Transformation Steps
## Pitfalls
## Script Index
```

---

## Committing & Submitting

```bash
git checkout -b <yourname>/<task_name>
git add tasks/<category>/<task_name>/
git commit -m "Add task: <task_name>"
git push -u origin <yourname>/<task_name>
```

Full instructions: `agenthle-homepage/docs/program/08_SUBMITTING_YOUR_IMPLEMENTED_TASK.md`
