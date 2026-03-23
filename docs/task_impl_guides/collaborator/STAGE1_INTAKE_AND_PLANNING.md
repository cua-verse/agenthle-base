# External Stage 1 - Intake And Planning

> Read this before any implementation work.

## Inputs You Must Already Have

- a local data path
- a task description
- the software name and version
- the expected output
- a rough verification idea
- your collaborator VM project name, VM name, and zone

If any of these are missing, stop and get them first.

## Recommended Prompt Format

```text
VM Name / Project / Zone:
<where the task is being built>

Local data path:
<absolute path>

Software:
<software name and version>

Task description:
<what the agent should do>

Expected output:
<what should be saved to output/>

Verification idea:
<how correctness should roughly be checked>

Notes / caveats:
<known missing files, setup assumptions, edge cases>
```

## Step 1: Scaffold The Task Folder

Create:

- `DATA_INTAKE.md`
- `TASK_INTAKE.md`
- `scripts/DATA_PIPELINE.md`
- `PITFALLS.md`
- `CONTEXT.md` copied from `../templates/CONTEXT_EXTERNAL.md`

Do this before drafting `main.py`.

## Step 2: Build `DATA_INTAKE.md`

Capture at least:

- the canonical local source path
- the raw directory and file inventory
- file formats and approximate sizes
- what appears to define one variant
- which files look like agent input
- which files look like reference data
- which files look like metadata or noise
- missing metadata and unresolved questions

Questions to answer early:

| Question | Why it matters |
|---|---|
| What is the true source of the raw data? | Avoid planning against stale copied folders |
| Is the data already benchmark-ready? | Many tasks still need preprocessing or filtering |
| What constitutes one variant? | Variant boundaries drive both `load()` and evaluation |
| Is any data corrupt, incomplete, or irrelevant? | Prevents building around unusable assets |
| Can the data support the intended verification method? | The task definition must match what the data can actually prove |

If something is unknown, write it down explicitly.

## Step 3: Build `TASK_INTAKE.md`

Translate the rough request into a concrete task design.

### What the agent must do

- write the exact step-by-step workflow, not a vague summary
- confirm the required software and version
- make sure the workflow matches what the processed data will really allow

### Input

- describe the benchmark-ready inputs after preprocessing, not just the upstream raw dump
- pin down formats and remote paths
- note what is copied directly versus produced by the data pipeline

### Output

- output must land under `output/`
- define the artifact type exactly: file, folder, screenshot set, report, exported asset, and so on
- make sure the output can actually be verified against the planned reference data

### Evaluation

Force yourself to answer:

| Question | Why it matters |
|---|---|
| Is there a ground-truth reference? | Most reliable evaluations compare output against a reference |
| Can scoring be fully automated? | If yes, keep it deterministic |
| Are there hard gates that force score `0`? | Implement these first |
| What does a perfect output score? | Should be close to `1.0` |
| What does a wrong or empty output score? | Should be clearly separated from perfect |

Preferred scoring patterns, in order:

1. exact file match or hash comparison
2. structured diff such as JSON, XML, or CSV field comparison
3. metric comparison with tolerances
4. LLM-as-judge only as a last resort

### Reference data

- say where the reference comes from
- explain whether it was provided directly or produced from the data pipeline
- make sure every reference artifact can be explained

### Variants

- define how variants are enumerated from the processed data
- if many variants share the same evaluation logic, one `main.py` should handle them via `load()`

## Step 4: Build `scripts/DATA_PIPELINE.md`

Record:

- raw source locations
- transformation steps in order
- scripts used and where they run
- naming conventions for variants
- validation checks after each step
- what lands in `input/`, `reference/`, `output_test_pos/`, and `output_test_neg/`

Rules:

- keep the pipeline deterministic
- avoid undocumented manual steps
- if manual work is unavoidable, document exactly what and why
- validate the processed data against `TASK_INTAKE.md`, not just file existence

## Step 5: Run The Review Loop

Collaborators still need the Stage 1 review pass.

Use an environment variable for the bearer token. Do not hardcode secrets in the task folder.

```bash
curl -N https://agenthle-backend-preview-nlsao4fgla-uc.a.run.app/agent/evaluate \
  -H "Authorization: Bearer ${AGENTHLE_REVIEW_BEARER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "taskDescription": ""
}'
```

Record stable takeaways in:

- `CONTEXT.md` for decisions and current state
- `PITFALLS.md` for repeatable task-specific traps

## Step 6: Record VM Handoff State Early

Before leaving Stage 1, `CONTEXT.md` should already contain:

- collaborator GCP project name
- collaborator VM name
- collaborator VM zone
- OS and access method
- where the task data lives on the VM
- what software is already installed
- what software still had to be installed

## Exit Criteria

Do not start implementation until all of these are true:

- `DATA_INTAKE.md` matches the actual local data
- `TASK_INTAKE.md` defines a concrete workflow and scorer
- `scripts/DATA_PIPELINE.md` is specific enough to rerun
- the processed data supports the task design
- the review loop no longer surfaces unresolved planning issues
- `CONTEXT.md` already records the collaborator VM identity and software context
