"""<task_name> — AgentHLE Task

TODO: Replace this skeleton with the actual implementation.
See tasks/guides/03_MAIN_PY_PATTERNS.md for patterns and examples.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Variants — one tuple per task instance
# Format: (task_tag, ...any extra info...)
# ---------------------------------------------------------------------------
VARIANTS = [
    # ("variant_tag",),
]


@dataclass
class TaskConfig(GeneralTaskConfig):
    """Task-specific configuration. Extends GeneralTaskConfig."""

    TASK_CATEGORY: str = ""  # TODO: e.g., "manufacturing\\gcode"
    TASK_TAG: str = ""

    @property
    def task_description(self) -> str:
        return f"""\
TODO: Write the task prompt the agent sees.
"""

    def to_metadata(self) -> dict:
        metadata = super().to_metadata()
        # TODO: add task-specific metadata keys
        return metadata


@cb.tasks_config(split="train")
def load():
    """Register task variants."""
    return [
        cb.Task(
            description=TaskConfig(TASK_TAG=tag).task_description,
            metadata=TaskConfig(TASK_TAG=tag).to_metadata(),
            computer={
                "provider": "computer",
                "setup_config": {"os_type": "windows"},
            },
        )
        for (tag,) in VARIANTS
    ]


@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    """Prepare the environment before the agent starts.

    TODO: Implement copy-to-output pattern:
    1. Clean and recreate output dir
    2. Copy input to output
    3. Open the relevant file/app for the agent
    """
    pass


@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the agent's output.

    TODO: Implement evaluation pipeline:
    1. Upload eval scripts from scripts/ to VM temp
    2. (Optional) Gate check — return [0.0] on hard failure
    3. Score — compare output vs reference
    4. Return [score]

    Test mode: if the output artifact already exists, skip generation.
    """
    return [0.0]
