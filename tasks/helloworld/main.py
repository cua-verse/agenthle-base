"""Test Milestone Task - Verify milestone screenshot saving."""

import asyncio
import logging
import os
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig

logger = logging.getLogger(__name__)

#################################################################
############################# Setup #############################
#################################################################

@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "HELLOWORLD"
    TASK_CATEGORY: str = "tasks"
    
    @property
    def milestone_path(self) -> str:
        return fr"{self.REMOTE_ROOT_DIR}\step1_opened.png"

    @property
    def task_description(self) -> str:
        return f"""
Goal: Save a milestone screenshot.
1. Save milestone: save_milestone_screenshot(path="{self.milestone_path}", description="Test")

Verification: The task is successful if the milestone screenshot file exists.
"""

    def to_metadata(self) -> dict:
        metadata = super().to_metadata()
        metadata.update({
            "milestone_path": self.milestone_path,
        })
        return metadata

config = TaskConfig()

@cb.tasks_config(split="train")
def load():
    """Define the test milestone task."""
    return [
        cb.Task(
            description=config.task_description,
            metadata=config.to_metadata(),
            computer={
                "provider": "computer",
                "setup_config": {
                    "os_type": config.OS_TYPE,
                }
            }
        )
    ]


@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    """Initialize the environment."""
    logger.info(f"Setting up test milestone task")
    # No specific setup needed for this test
    await asyncio.sleep(1)


@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the task based on the existence of the milestone screenshot."""
    milestone_path = task_cfg.metadata["milestone_path"]
    
    try:
        # Use session.exists to check if the milestone screenshot file exists
        if await session.exists(milestone_path):
            logger.info(f"Evaluation: Success! Milestone screenshot found at {milestone_path}")
            return [1.0]
        else:
            logger.info(f"Evaluation: Milestone screenshot NOT found at {milestone_path}")
            return [0.0]
            
    except Exception as e:
        logger.error(f"Evaluation error: {e}")
    
    return [0.0]
