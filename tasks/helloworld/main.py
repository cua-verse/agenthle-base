"""Test Milestone Task - Verify milestone screenshot saving."""

import asyncio
import logging

import cua_bench as cb

logger = logging.getLogger(__name__)

# Task constants
MILESTONE_PATH = r"C:\Users\User\Desktop\step1_opened.png"
MILESTONE_DESCRIPTION = "Test"


@cb.tasks_config(split="train")
def load():
    """Define the test milestone task."""
    return [
        cb.Task(
            description=f"""
Goal: Save a milestone screenshot.
1. Save milestone: save_milestone_screenshot(path="{MILESTONE_PATH}", description="{MILESTONE_DESCRIPTION}")

Verification: The task is successful if the milestone screenshot file exists.
""",
            metadata={
                "milestone_path": MILESTONE_PATH,
                "milestone_description": MILESTONE_DESCRIPTION,
            },
            computer={
                "provider": "computer",
                "setup_config": {
                    "os_type": "windows",
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
        # Use PowerShell to check if the milestone screenshot file exists (Windows-compatible)
        check_file_cmd = f'powershell -Command "if (Test-Path \'{milestone_path}\') {{ Write-Output \'FILE_EXISTS\' }} else {{ Write-Output \'FILE_NOT_EXISTS\' }}"'
        file_result = await session.run_command(check_file_cmd)

        print(file_result)
        
        stdout = file_result.get("stdout", "") if isinstance(file_result, dict) else str(file_result)
        
        if "FILE_EXISTS" in stdout:
            logger.info(f"Evaluation: Success! Milestone screenshot found at {milestone_path}")
            return [1.0]
        else:
            logger.info(f"Evaluation: Milestone screenshot NOT found at {milestone_path}")
            return [0.0]
            
    except Exception as e:
        logger.error(f"Evaluation error: {e}")
    
    return [0.0]
