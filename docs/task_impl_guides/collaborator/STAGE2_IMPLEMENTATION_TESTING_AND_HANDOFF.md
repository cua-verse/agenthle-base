# External Stage 2 - Implementation, Testing, And Handoff

> Read this once Stage 1 is stable and the task is ready to become runnable code.

## What You Must Build

At minimum:

- `main.py`
- helper scripts under `scripts/`
- `run_<taskname>.sh`
- `README.md`
- `REPRO_COMMANDS.md`

Your code must match `TASK_INTAKE.md`. Do not silently change the task definition in code.

## Runtime Layout Conventions

### Remote directory structure

```text
C:\Users\User\Desktop\<TASK_CATEGORY>\<TASK_TAG>\
  input/
  output/
  reference/
  software/
```

### GS bucket convention

```text
gs://agenthle/<TASK_CATEGORY>/<TASK_TAG>/input/
gs://agenthle/<TASK_CATEGORY>/<TASK_TAG>/reference/
```

### Fixed eval temp dir

```text
C:\Users\User\AppData\Local\Temp\agenthle_eval\<task_name>
```

## `main.py` Principles

1. `start()` does not open software.
2. `start()` does not copy input into output.
3. `start()` only installs eval-required packages and downloads benchmark input.
4. `evaluate()` downloads reference data first, then scores.
5. Eval scripts print machine-readable JSON to stdout and debug logs to stderr.

## `main.py` Shape

### Task config pattern

```python
from dataclasses import dataclass
from tasks.common_config import GeneralTaskConfig

@dataclass
class MyTaskConfig(GeneralTaskConfig):
    TASK_CATEGORY: str = "manufacturing"
    TASK_TAG: str = ""

    @property
    def input_dir(self) -> str:
        return rf"{self.task_dir}\input"

    @property
    def output_file(self) -> str:
        return rf"{self.remote_output_dir}\result.txt"

    @property
    def reference_file(self) -> str:
        return rf"{self.reference_dir}\reference.txt"

    @property
    def task_description(self) -> str:
        return f"""\
You are a ... using ...
## Your Task
...
## Input Files
- Located at: `{self.input_dir}`
## Output
- Save your result to: `{self.remote_output_dir}`
"""
```

### `load()` for multiple variants

```python
@cb.tasks_config(split="train")
def load():
    return [
        cb.Task(
            description=MyTaskConfig(TASK_TAG=tag).task_description,
            metadata=MyTaskConfig(TASK_TAG=tag).to_metadata(),
            computer={
                "provider": "computer",
                "setup_config": {"os_type": "windows"},
            },
        )
        for tag in VARIANTS
    ]
```

### `start()` for setup and input download

```python
@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    meta = task_cfg.metadata
    input_dir = meta["input_dir"]
    tag = meta["task_tag"]

    await session.run_command("pip install trimesh numpy", timeout=120.0)

    if await session.exists(input_dir):
        files = await session.list_dir(input_dir)
        if files:
            return

    await session.makedirs(input_dir)
    gcs_path = f"gs://agenthle/{meta['task_category']}/{tag}/input/"
    await session.run_command(
        f'gsutil -m cp -r "{gcs_path}*" "{input_dir}\\"',
        timeout=300.0,
    )
```

### `evaluate()` for reference download and scoring

```python
@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    meta = task_cfg.metadata
    ref_dir = meta["reference_dir"]
    ref_file = meta["reference_file"]
    output_file = meta["output_file"]

    if not await session.exists(ref_dir) or not await session.list_dir(ref_dir):
        await session.makedirs(ref_dir)
        gcs_path = f"gs://agenthle/{meta['task_category']}/{meta['task_tag']}/reference/"
        await session.run_command(
            f'gsutil -m cp -r "{gcs_path}*" "{ref_dir}\\"',
            timeout=300.0,
        )

    await session.write_file(r"C:\Users\User\AppData\Local\Temp\agenthle_eval\verify.py", verify_script)
    result = await session.run_command(
        f'python "C:\\Users\\User\\AppData\\Local\\Temp\\agenthle_eval\\verify.py" --agent "{output_file}" --ref "{ref_file}"'
    )
    return [float(json.loads(result["stdout"])["score"])]
```

## Testing Rules

### Setup and evaluate separately

| Phase | What to test | How |
|---|---|---|
| setup | `start()` installs dependencies and downloads input | `--setup-only` |
| evaluate | `evaluate()` scores positive and negative outputs correctly | `--eval` with `REMOTE_OUTPUT_DIR` |

### Required output directories per variant

| Directory | Contents | Expected score |
|---|---|---|
| `output_test_pos/` | known-correct output | about `1.0` |
| `output_test_neg/` | clearly wrong output | about `0.0` |

### Run script shape

Each task must commit `run_<taskname>.sh`.

```bash
#!/bin/bash

export LOCAL_TASK_DIR="./tasks/<category>/<task_name>"
export REMOTE_OUTPUT_DIR="${REMOTE_OUTPUT_DIR:-output}"

uv run python -m cua_bench.batch.solver "$LOCAL_TASK_DIR" \
  --eval \
  --dump \
  --output-dir "./trycua/cua-bench/$TASK_NAME"
```

### Commands you should actually run

```bash
uv run python -m cua_bench.batch.solver ./tasks/<category>/<task_name> \
  --setup-only --output-dir ./trycua/cua-bench/<task_name>

REMOTE_OUTPUT_DIR=output_test_pos bash tasks/<category>/<task_name>/run_<taskname>.sh
REMOTE_OUTPUT_DIR=output_test_neg bash tasks/<category>/<task_name>/run_<taskname>.sh
```

Record the exact commands you used in `REPRO_COMMANDS.md`.

## What Must Go Into `CONTEXT.md`

For collaborator tasks, `CONTEXT.md` is part of the admin handoff package.

It must capture:

- current implementation state
- unresolved blockers
- collaborator VM project, name, and zone
- important remote paths
- every software install or download that was required
- any manual setup the admin must reproduce later
- PR URL once opened
- whether GCP access was granted to `agenthle.sv@gmail.com` and `agenthle-admin@agenthle-488519.iam.gserviceaccount.com`

If you installed software, log the exact source, version, and install location.

## What To Commit

Commit:

- `DATA_INTAKE.md`
- `TASK_INTAKE.md`
- `CONTEXT.md`
- `PITFALLS.md`
- `README.md`
- `REPRO_COMMANDS.md`
- `main.py`
- `run_<taskname>.sh`
- `scripts/`

Do not commit:

- `input/`, `output/`, `reference/`
- `.env`
- raw datasets from the collaborator VM
- secrets or bearer tokens
- `REVIEW_REPORT.md`
- `FIX_CHANGELOG.md`

## PR Handoff Requirements

Submit the full task folder as a PR to:

```text
https://github.com/cua-verse/agenthle-base
```

Before you open the PR, confirm that `CONTEXT.md` contains:

- collaborator project / VM / zone
- OS and access method
- important paths on the collaborator VM
- software install and download history
- remaining manual setup
- branch name
- PR URL or PR number
- a short migration note for the admin

Suggested PR body fields:

- task path under `tasks/`
- software used and version
- local data source
- single-variant or multi-variant
- positive and negative tests run
- collaborator VM project / name / zone
- whether the GCP access commands below were executed
- anything the admin should know before migration

After merge, admin ingestion sets the default DB status to `untracked`.

## GCP Access For Admin Migration

Admins need to be able to start the VM, inspect it, retrieve its IP, and access the task data.

Grant access to:

- `agenthle.sv@gmail.com`
- `agenthle-admin@agenthle-488519.iam.gserviceaccount.com`

Set variables:

```bash
export PROJECT_ID="<your-gcp-project>"
export ZONE="<your-vm-zone>"
export VM_NAME="<your-vm-name>"
export AGENTHLE_ADMIN_USER="agenthle.sv@gmail.com"
export AGENTHLE_ADMIN_SA="agenthle-admin@agenthle-488519.iam.gserviceaccount.com"
```

If needed, discover the VM service account:

```bash
export VM_SERVICE_ACCOUNT="$({
  gcloud compute instances describe "$VM_NAME" \
    --project "$PROJECT_ID" \
    --zone "$ZONE" \
    --format='value(serviceAccounts[0].email)'
})"
```

Baseline project-level access:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="user:${AGENTHLE_ADMIN_USER}" \
  --role="roles/compute.viewer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${AGENTHLE_ADMIN_SA}" \
  --role="roles/compute.viewer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="user:${AGENTHLE_ADMIN_USER}" \
  --role="roles/compute.instanceAdmin.v1"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${AGENTHLE_ADMIN_SA}" \
  --role="roles/compute.instanceAdmin.v1"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="user:${AGENTHLE_ADMIN_USER}" \
  --role="roles/iap.tunnelResourceAccessor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${AGENTHLE_ADMIN_SA}" \
  --role="roles/iap.tunnelResourceAccessor"
```

If the instance uses a VM service account and your org requires it:

```bash
gcloud iam service-accounts add-iam-policy-binding "$VM_SERVICE_ACCOUNT" \
  --member="user:${AGENTHLE_ADMIN_USER}" \
  --role="roles/iam.serviceAccountUser"

gcloud iam service-accounts add-iam-policy-binding "$VM_SERVICE_ACCOUNT" \
  --member="serviceAccount:${AGENTHLE_ADMIN_SA}" \
  --role="roles/iam.serviceAccountUser"
```

For Linux VMs using OS Login:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="user:${AGENTHLE_ADMIN_USER}" \
  --role="roles/compute.osAdminLogin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${AGENTHLE_ADMIN_SA}" \
  --role="roles/compute.osAdminLogin"
```

Verification commands:

```bash
gcloud compute instances describe "$VM_NAME" \
  --project "$PROJECT_ID" \
  --zone "$ZONE" \
  --format='table(name,status,zone,networkInterfaces[0].networkIP,networkInterfaces[0].accessConfigs[0].natIP)'
```

```bash
gcloud projects get-iam-policy "$PROJECT_ID" \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:${AGENTHLE_ADMIN_USER} OR bindings.members:serviceAccount:${AGENTHLE_ADMIN_SA}" \
  --format='table(bindings.role,bindings.members)'
```

Record the results in `CONTEXT.md`.

## Exit Criteria

Stage 2 is complete only when:

- `main.py` and supporting scripts are implemented
- `run_<taskname>.sh` is verified on the collaborator VM
- positive and negative outputs score correctly
- `README.md` and `REPRO_COMMANDS.md` reflect what you actually ran
- `CONTEXT.md` fully documents the VM and software state needed for migration
- the PR handoff metadata is complete
