# External Collaborator Workflow

> Who this is for: contributors who do not have AgentHLE internal DB/GCS access and will build the task on their own VM.

## Goal

Turn local data plus a rough task description into a complete task folder that:

- has coherent Stage 1 planning artifacts
- has a working Stage 2 implementation
- has been tested on the collaborator VM
- records enough VM/setup context for admin migration
- is ready to submit as a PR to `https://github.com/cua-verse/agenthle-base`

This workflow stops after Stage 2. Do not create Stage 3 validation deliverables unless an admin asks for them explicitly.

## Recommended Order

1. Read `STAGE1_INTAKE_AND_PLANNING.md`
2. Scaffold the task folder from `../templates/`
3. Use `../templates/CONTEXT_EXTERNAL.md` as `CONTEXT.md`
4. Finish planning, including the review loop
5. Read `STAGE2_IMPLEMENTATION_TESTING_AND_HANDOFF.md`
6. Implement and test the task on your own VM
7. Record PR handoff details and grant the required GCP access
8. Open the PR only after the task folder and handoff metadata are complete

## Required Deliverables

- `DATA_INTAKE.md`
- `TASK_INTAKE.md`
- `scripts/DATA_PIPELINE.md`
- `CONTEXT.md`
- `PITFALLS.md`
- `main.py`
- `run_<taskname>.sh`
- `README.md`
- `REPRO_COMMANDS.md`

Do not add `REVIEW_REPORT.md` or `FIX_CHANGELOG.md` in the normal collaborator flow.
