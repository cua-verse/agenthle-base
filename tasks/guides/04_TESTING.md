# Guide 04 — Testing Evaluation

> **When to read:** When setting up pos/neg test cases and running `test_eval_local.sh`.
>
> Full framework details: `agenthle-homepage/docs/program/07_TESTING_YOUR_EVALUATION.md`

---

## The Two Test Dirs

For each task variant, create two test output directories on the VM:

| Directory | Contents | Expected score |
|---|---|---|
| `output_test_pos/` | A known-correct agent output | ~1.0 |
| `output_test_neg/` | A clearly wrong agent output | ~0.0 (or clearly low) |

**How to create them** (this is task-specific, but common patterns):
- **Pos**: copy the reference output (e.g., `reference_sim.stl`) into `output_test_pos/` as the agent's artifact
- **Neg**: use a completely different input's output (e.g., a different workpiece's STL) — or an empty/blank file

Write a `scripts/setup_test_dirs.py` that creates these automatically for all variants.

---

## `REMOTE_OUTPUT_DIR` — How Test Switching Works

`GeneralTaskConfig.remote_output_dir` is built from the `REMOTE_OUTPUT_DIR` environment variable (default: `"output"`):

```
REMOTE_OUTPUT_DIR=output_test_pos
→ remote_output_dir = C:\...\<task_tag>\output_test_pos
```

This means `evaluate()` will read from `output_test_pos/` instead of `output/` — no code changes needed.

---

## Setting Up `test_eval_local.sh`

```bash
cp test_eval.sh test_eval_local.sh
```

Then edit `test_eval_local.sh`:

```bash
export LOCAL_TASK_DIR="./tasks/<category>/<task_name>"
export REMOTE_OUTPUT_DIR="output_test_pos"    # switch to output_test_neg for neg test
export OPENAI_API_KEY="YOUR_KEY"
export CUA_ENV_API_URL="http://<VM_IP>:5000"
```

> ⚠️ **Do NOT commit `test_eval_local.sh`** — it contains credentials.

---

## Running the Test

```bash
bash test_eval_local.sh
```

**What `--evaluate-only` does:** Connects to the VM, runs `evaluate()` only — skips `start()`. Whatever is in the output dir is used as-is.

**Which variant is tested?** By default, `BATCH_TASK_INDEX=0` → the first variant in `load()`. To test another:

```bash
# In the script, add --task-index N to the uv run command
uv run python -m cua_bench.batch.solver $LOCAL_TASK_DIR \
    --evaluate-only \
    --task-index 5 \
    ...
```

To test all variants in a loop:

```bash
for i in {0..14}; do
    BATCH_TASK_INDEX=$i bash test_eval_local.sh
done
```

---

## Confirming Results

| Test | Expected |
|---|---|
| `output_test_pos` | score ≥ 0.95 (ideally 1.0) |
| `output_test_neg` | score ≤ 0.2 (clearly different from pos) |

If pos scores low or neg scores high — the evaluation logic needs rethinking. Stop, diagnose, discuss with user before adjusting thresholds.
