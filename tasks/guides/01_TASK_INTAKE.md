# Guide 01 — Task Intake

> **When to read:** While helping the user fill `TASK_INTAKE.md` in their task folder.
>
> The template itself is at `tasks/guides/templates/TASK_INTAKE.md` and gets copied into each new task folder during scaffolding.

---

## Your Job During Intake

You scaffolded the task folder and the user now has a blank `TASK_INTAKE.md`. Your job:

1. **Walk through each section** — ask clarifying questions where answers are vague
2. **Push back on ambiguous evaluation** — the most common trap. If the user says "just compare the output" you need to pin down: compare what? using what metric? what's the tolerance?
3. **Don't start implementing until intake is complete** — especially sections 5 (evaluation) and 6 (reference data)

---

## Section-by-Section Guidance

### Section 2: What the Agent Must Do
- Get the exact step-by-step workflow, not a high-level summary
- Confirm which software the agent uses and whether it's already installed on the VM

### Section 3: Input
- Pin down exact file formats — e.g., "a PowerMill project folder" not just "project files"
- Ask: is the input already on the VM, or do we need to create/copy it?

### Section 4: Output
- Must go into `output/` on the VM — no exceptions
- What exact artifact does the agent save? A folder? A single file? A screenshot?

### Section 5: Evaluation — THE CRITICAL SECTION
Force yourself and the user to answer:

| Question | Why it matters |
|---|---|
| Is there a ground-truth reference? | Most reliable evaluations compare output vs reference |
| Can the scoring be fully automated? | If yes → deterministic. If no → consider simplifying the task scope |
| Are there hard gates (instant score = 0)? | Implement these first — they catch obvious failures |
| What score does a perfect output get? | Must be ~1.0 |
| What score does a random/wrong output get? | Must be clearly different from perfect (ideally < 0.2) |

**Prefer these (in order):**
1. Exact file match / hash comparison → simplest
2. Structured diff (JSON, XML, CSV field comparison) → reliable
3. Metric comparison (geometric distance, pixel diff, SSIM) → needs tolerance design
4. LLM-as-judge → last resort only

### Section 7: Variants
- If there are N variants with identical eval logic, one `main.py` handles all of them via `load()`
- The folder structure on the VM should have one subfolder per variant

---

## After Intake Is Complete

1. Update `CONTEXT.md` — mark intake as done, note key decisions
2. Proceed to Phase 2 (VM exploration) → `02_REMOTE_VM_API.md`
