"""Magic Tower Demo Task - End-to-End Verifiable."""

import asyncio
import base64
import logging
import os

import cua_bench as cb
from cua_bench import replay_trajectory

logger = logging.getLogger(__name__)

#################################################################
############################# Setup #############################
#################################################################


# Task constants
# We use the local path if it's the standard on the target environment

TASK_TAG = "GAME_MOTA_24_EZ"
GAME_TAG = "mota-24"
GAME_URL = fr"C:\Users\User\Desktop\mota\mota_swfs\{GAME_TAG}.swf"

# Evaluation file paths
TARGET_FILE_PATH = fr"C:\Users\User\Desktop\mota\mota_tasks\{TASK_TAG}"
REFERENCE_FILE_PATH = fr"C:\Users\User\Desktop\mota\mota_tasks\{TASK_TAG}_REF"


# This task needs to be launched on a GPU work station.

@cb.tasks_config(split="train")
def load():
    """Define the Magic Tower demo task."""
    return [
        cb.Task(
            description=f"""
Goal: Launch Magic Tower and navigate to the 3rd floor.
1. Open the game at {GAME_URL} on Ruffle (the game should be opened automatically).
2. Wait for the game to load and enter the game.
3. Navigate to the 3rd floor.

Verification: 
1. When steps in each new floor, you should save milestone screenshot with `save_milestone_screenshot(path="{TARGET_FILE_PATH}\$FLOOR_NUMBER$.png")`, where $FLOOR_NUMBER$ is the floor number you reached.
2. The task is successful if the screenshots exists and it demonstrates the floor you reached.
""",
            metadata={
                "task_tag": TASK_TAG,
                "game_tag": GAME_TAG,
                "game_url": GAME_URL,
                "target_file": TARGET_FILE_PATH,
                "reference_file": REFERENCE_FILE_PATH,
            },
            computer={
                "provider": "computer",
                "setup_config": {
                    "os_type": "windows",
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
    target_path = task_cfg.metadata["target_file"]
    try:
        await session.run_file(game_url)
        logger.info("Game launched successfully")
        await session.remove_file(target_path)
        await session.makedirs(target_path)
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
    
    target_path = task_cfg.metadata["target_file"]
    reference_path = task_cfg.metadata["reference_file"]
    task_tag = task_cfg.metadata.get("task_tag", "unknown")
    
    try:
        # Use the common milestone evaluation mode
        final_score, _ = await evaluate_milestone_mode(
            session=session,
            target_path=target_path,
            reference_path=reference_path,
            task_tag=task_tag,
            comparison_fn=query_milestone,
            output_dir=os.environ.get("EVALUATION_OUTPUT_DIR", "./trycua/cua-bench/")
        )
        
        return [final_score]
        
    except Exception as e:
        logger.error(f"Evaluation error: {e}")
        return [0.0]




