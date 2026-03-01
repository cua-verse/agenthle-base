# Guide 03 — `main.py` Patterns

> **When to read:** When implementing `load()`, `start()`, and `evaluate()`.
>
> This guide covers common patterns. For the authoritative spec, see:
> `agenthle-homepage/docs/program/06_LOCAL_TASK_SPEC_MAIN_PY.md`

---

## Remote Directory Structure

```
C:\Users\User\Desktop\<category>\<task_name>\<TASK_TAG>\
  input/          ← read-only source data
  output/         ← agent writes here (REMOTE_OUTPUT_DIR defaults to "output")
  reference/      ← ground-truth used by evaluate()
  software/       ← app shortcuts for the agent
```

Reference: `agenthle-homepage/docs/program/05_REMOTE_DEVELOPMENT.md`

---

## Task Config — Inheriting from `GeneralTaskConfig`

```python
from dataclasses import dataclass
from tasks.common_config import GeneralTaskConfig

@dataclass
class MyTaskConfig(GeneralTaskConfig):
    TASK_CATEGORY: str = "manufacturing"   # Desktop\<category>\
    TASK_TAG: str = ""                     # Desktop\<category>\<TASK_TAG>\

    # Automatically available from GeneralTaskConfig:
    #   self.task_dir       → Desktop\<category>\<TASK_TAG>
    #   self.remote_output_dir → task_dir\<REMOTE_OUTPUT_DIR env var, default "output">
    #   self.reference_dir  → task_dir\reference
    #   self.software_dir   → task_dir\software

    @property
    def input_file(self) -> str:
        return rf"{self.task_dir}\input\something.txt"

    @property
    def output_file(self) -> str:
        return rf"{self.remote_output_dir}\result.txt"

    def to_metadata(self) -> dict:
        metadata = super().to_metadata()
        metadata.update({
            "input_file": self.input_file,
            "output_file": self.output_file,
        })
        return metadata
```

> `REMOTE_OUTPUT_DIR` is read from the environment — setting it to `output_test_pos` in `test_eval_local.sh` makes `remote_output_dir` point to that test folder automatically. This is how pos/neg testing works.

---

## Multiple Variants — `load()`

```python
VARIANTS = [
    ("tag_a", "extra_info_a"),
    ("tag_b", "extra_info_b"),
    # ... up to N entries
]

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
        for tag, _ in VARIANTS
    ]
```

---

## `start()` — Copy-to-Output Pattern

The agent must work on a **copy** of the input, not the original. This keeps `input/` pristine.

```python
@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    meta = task_cfg.metadata
    output_dir = meta["remote_output_dir"]
    input_src  = meta["input_file"]         # or input folder
    output_dst = meta["output_file"]        # or output folder

    # 1. Clean and recreate output dir
    try:
        await session.remove_file(output_dir)
    except Exception:
        pass
    await session.makedirs(output_dir)

    # 2. Copy input → output (agent works on the copy)
    await session.copy_file(input_src, output_dst)

    # 3. Open the copied artifact for the agent
    await session.run_file(output_dst)

    await asyncio.sleep(5)  # give the app time to open
```

---

## `evaluate()` — Upload-and-Run Pattern

Evaluation scripts live locally in `scripts/` and are uploaded to the VM at eval time. Never deploy persistent scripts to the VM.

```python
SCRIPTS_DIR = Path(__file__).parent / "scripts"

def _read_script(name: str) -> str:
    return (SCRIPTS_DIR / name).read_text(encoding="utf-8")

@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    meta = task_cfg.metadata
    output_dir  = meta["remote_output_dir"]
    output_file = meta["output_file"]
    ref_file    = meta["reference_file"]

    # 1. Upload eval scripts to a temp location
    tmp = r"C:\Users\User\AppData\Local\Temp\task_eval"
    await session.makedirs(tmp)
    for name in ["verify.py"]:
        await session.write_file(rf"{tmp}\{name}", _read_script(name))

    # 2. (Optional) Gate check — return [0.0] immediately if triggered
    result = await session.run_command(f'python "{tmp}\\check.py" --file "{output_file}"')
    if result["return_code"] != 0:
        return [0.0]

    # 3. Score
    result = await session.run_command(
        f'python "{tmp}\\verify.py" --agent "{output_file}" --ref "{ref_file}"'
    )
    data = json.loads(result["stdout"])
    return [float(data["score"])]
```

### Test Mode (Pre-existing Output)

If the agent's output artifact already exists (placed there for pos/neg testing), skip generation steps:

```python
if await session.exists(output_file):
    logger.info("Output exists — test mode, skipping generation")
else:
    # ... run generation pipeline ...
    if not await session.exists(output_file):
        return [0.0]

# Always run scoring
result = await session.run_command(...)
```

---

## Eval Script Output Format

All evaluation scripts (`verify.py`, `check.py`, etc.) should print a single JSON object to stdout:

```python
# verify.py output:
import json, sys
result = {"score": 0.85, "mean_dist_mm": 1.2, "ratio_perfect": 0.73}
print(json.dumps(result))
sys.exit(0)
```

This makes `json.loads(result["stdout"])` reliable in `main.py`.
