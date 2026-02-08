"""Magic Tower Demo Task - End-to-End Verifiable."""

import asyncio
import base64
import logging
import os
from dataclasses import dataclass

import cua_bench as cb
from cua_bench import replay_trajectory
from tasks.common_config import GeneralTaskConfig

logger = logging.getLogger(__name__)

#################################################################
############################# Setup #############################
#################################################################

@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_CATEGORY: str = "game"
    TASK_TAG: str = "GAME_MOTA_24_EZ"
    GAME_TAG: str = "mota-24"

    @property
    def game_url(self) -> str:
        return fr"{self.task_dir}\input\{self.GAME_TAG}.swf"

    @property
    def task_description(self) -> str:
        return f"""
Goal: Launch Magic Tower and navigate to the 3rd floor.
1. Open the game at {self.game_url} on Ruffle (the game should be opened automatically).
2. Wait for the game to load and enter the game.
3. Navigate to the 3rd floor.

Verification: 
1. When steps in each new floor, you should save milestone screenshot with `save_milestone_screenshot(path="{self.remote_output_dir}\$FLOOR_NUMBER$.png")`, where $FLOOR_NUMBER$ is the floor number you reached.
2. The task is successful if the screenshots exists and it demonstrates the floor you reached.
"""

    def to_metadata(self) -> dict:
        metadata = super().to_metadata()
        metadata.update({
            "game_tag": self.GAME_TAG,
            "game_url": self.game_url,
        })
        return metadata

config = TaskConfig()

# This task needs to be launched on a GPU work station.

@cb.tasks_config(split="train")
def load():
    """Define the Magic Tower demo task."""
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


#################################################################
######################### Initialization ########################
#################################################################


@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    """Initialize the environment by opening the game and replaying a trajectory."""
    logger.info(f"Setting up task: {task_cfg.metadata['game_url']}")
    game_url = task_cfg.metadata['game_url']
    remote_output_path = task_cfg.metadata["remote_output_dir"]
    try:
        await session.run_file(game_url)
        logger.info("Game launched successfully")
        await session.remove_file(remote_output_path)
        await session.makedirs(remote_output_path)
    except Exception as e:
        logger.warning(f"Failed to launch game via session: {e}")

    # Wait for game to load
    await asyncio.sleep(3)



#################################################################
########################### Evaluation ##########################
#################################################################

async def query_milestone(
    target_image_bytes: bytes, 
    reference_image_bytes: bytes, 
    floor_number: str
) -> dict:

    from utils.evaluation import compare_screenshots_game
    
    # Custom comparison criteria for Magic Tower
    comparison_criteria = "- Is the player on the same floor number?"
    
    return await compare_screenshots_game(
        target_image_bytes=target_image_bytes,
        reference_image_bytes=reference_image_bytes,
        context_description=f"floor {floor_number}",
        comparison_criteria=comparison_criteria
    )


@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the task based on the existence and content of the demo file."""
    from utils.evaluation import evaluate_milestone_mode
    
    remote_output_path = task_cfg.metadata["remote_output_dir"]
    reference_path = task_cfg.metadata["reference_dir"]
    task_tag = task_cfg.metadata.get("task_tag", "unknown")
    
    try:
        # Use the common milestone evaluation mode
        final_score, _ = await evaluate_milestone_mode(
            session=session,
            target_path=remote_output_path,
            reference_path=reference_path,
            task_tag=task_tag,
            comparison_fn=query_milestone,
            output_dir=os.environ.get("EVALUATION_OUTPUT_DIR", "./trycua/cua-bench/")
        )
        
        return [final_score]
        
    except Exception as e:
        logger.error(f"Evaluation error: {e}")
        return [0.0]
