# AgentHLE Task Design — Guide Index

> **You are a Coding Agent helping a user design a new AgentHLE benchmark task.**
> Start here. This index tells you what documents exist, when to read them, and what to do first.

---

## ⛔ Hard Rules (Non-Negotiable)

1. **NEVER delete data on remote VM or local machine.** No `rm -rf`, no `delete_dir` on any `input/`, `output/`, `reference/`, `software/`, or user data directories. Only delete files you explicitly created (e.g., temp scripts in `C:\tmp\`). If you need to clean an `output/` dir during `start()`, only remove contents *you generated in that run*, or confirm with the user first.
2. **Python interpreter: use `python` only.** Do not use `python3`, `conda run`, or any other variant — on both local and remote machines. The environments are set up so `python` points to the correct interpreter.
3. **Never loop on the same error.** If the same error or obstacle occurs 2–3 times in a row, STOP and ask the user for help. Do not keep retrying the same approach. Report what you tried, what failed, and ask for guidance.

---

## Step 0 — Bootstrap a New Task

The user gives you **1–2 sentences** describing a new task (domain, what the agent does, what software is used).

**Step 0a — Create the git branch FIRST:**

```bash
git checkout -b <yourname>/<task_name>
```

Record this branch name in `CONTEXT.md` (see below).

**Step 0b — Scaffold the task folder:**

```
tasks/<category>/<task_name>/
  TASK_INTAKE.md         ← copy from tasks/guides/templates/TASK_INTAKE.md
  CONTEXT.md             ← copy from tasks/guides/templates/CONTEXT.md
  PITFALLS.md            ← copy from tasks/guides/templates/PITFALLS.md
  main.py                ← copy from tasks/guides/templates/main_skeleton.py
  scripts/               ← create empty directory
  README.md              ← create later (Phase 6)
```

Then **ask the user to fill in `TASK_INTAKE.md`** before writing any real code. This is the most important step. Do not proceed until the intake is complete — especially the evaluation method.

---

## Guide Documents (read on demand, not all at once)

```
tasks/guides/
  templates/                  Scaffolding files copied into new task folders
    TASK_INTAKE.md            Template the user fills out to define the task
    CONTEXT.md                Template for tracking running state
    PITFALLS.md               Template for task-specific gotchas
    main_skeleton.py          Skeleton main.py with load/start/evaluate stubs
  01_TASK_INTAKE.md           Detailed guidance on HOW to fill the intake
  02_REMOTE_VM_API.md         session.* and interface.* API quick reference
  03_MAIN_PY_PATTERNS.md      Common main.py patterns (config, copy-to-output, upload-and-run)
  04_TESTING.md               Pos/neg test setup and test_eval_local.sh usage
  05_DOCS_CONVENTIONS.md      What docs to maintain per-task, what to commit
  KNOWN_ISSUES.md             Cross-task pitfalls (Agent contributes back here)
```

| Guide | When to read |
|---|---|
| `01_TASK_INTAKE.md` | While helping user fill the intake template |
| `02_REMOTE_VM_API.md` | When exploring the remote VM or writing eval scripts |
| `03_MAIN_PY_PATTERNS.md` | When implementing `main.py` |
| `04_TESTING.md` | When setting up pos/neg tests |
| `05_DOCS_CONVENTIONS.md` | When writing documentation or before committing |
| `KNOWN_ISSUES.md` | When encountering a generic bug — check if it's already known |

---

## Official Docs (always available, reference as needed)

| Doc | When to open it |
|---|---|
| `agenthle-homepage/docs/program/05_REMOTE_DEVELOPMENT.md` | Remote file structure conventions |
| `agenthle-homepage/docs/program/06_LOCAL_TASK_SPEC_MAIN_PY.md` | Authoritative `main.py` spec |
| `agenthle-homepage/docs/program/07_TESTING_YOUR_EVALUATION.md` | Eval testing details |
| `agenthle-homepage/docs/program/08_SUBMITTING_YOUR_IMPLEMENTED_TASK.md` | PR + submission |
| `agenthle-homepage/docs/program/appendix_SESSION_COMMANDS.md` | Full `session.*` API |
| `submodules/cua/docs/content/docs/cua/reference/computer-sdk/index.mdx` | `interface.*` low-level API |

---

## Task Workflow (Overview)

```
Phase 0  User says 1-2 sentences → Agent scaffolds folder     (this file)
Phase 1  User fills TASK_INTAKE.md → Agent clarifies eval      → 01_TASK_INTAKE.md
Phase 2  Explore remote VM                                     → 02_REMOTE_VM_API.md
Phase 3  Build data pipeline, archive scripts in scripts/      → 02_REMOTE_VM_API.md
Phase 4  Implement main.py                                     → 03_MAIN_PY_PATTERNS.md
Phase 5  Test evaluation (pos/neg)                             → 04_TESTING.md
Phase 6  Write README.md, DATA_PIPELINE.md, commit, submit     → 05_DOCS_CONVENTIONS.md
```

**Throughout all phases:**
- Update `CONTEXT.md` at the end of every session
- Log task-specific bugs in `PITFALLS.md`
- Contribute generic bugs back to `guides/KNOWN_ISSUES.md`

---

## Interaction Rules

| Situation | Action |
|---|---|
| Intake template not complete | Stop, ask user to fill it |
| Evaluation method ambiguous | Discuss, prefer deterministic/automated |
| Long-running VM script (>30s) | Upload script, ask user to run it, hand back control |
| Key design decision (thresholds, scoring) | Ask user to confirm |
| Unexpected VM state | Report finding, ask how to proceed |
| Found a generic bug (not task-specific) | Add to `guides/KNOWN_ISSUES.md` |
| **Same error repeats 2-3 times** | **STOP immediately. Report what you tried and ask user for help. Do NOT keep retrying.** |
| Development complete | Clean up all `/tmp/` and remote temp files before wrapping up |
