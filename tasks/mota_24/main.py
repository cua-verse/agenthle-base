"""Magic Tower Demo Task - End-to-End Verifiable."""

import asyncio
import logging
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from utils.evaluation import collect_matching_files, llm_vision_judge, EvaluationContext
import os
logger = logging.getLogger(__name__)


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "mota_24"
    TASK_CATEGORY: str = "game"
    MAX_LAYER: int = 3
    
    @property
    def game_url(self) -> str:
        return fr"{self.task_dir}\input\{self.TASK_TAG}.swf"
    
    @property
    def template_url(self) -> str:
        return fr"{self.task_dir}\input\mota_template"

    @property
    def task_description(self) -> str:
        return f"""
Goal: Reproduced a flash game with RPGMaker.
1. Open the game at {self.game_url} (the game should be opened automatically with full screen).
2. Open the template project at {self.template_url} on RPGMakerXP (also opened automatically). 
3. Reproduce the game from level 1 - {self.MAX_LAYER} including game map, monsters, fighting logics. 
 
Output:
After completing the reproduction:
- Preview the reproduced game in RPGMakerXP.
- Play through the game and successfully navigate to each new floor.
- Upon reaching each floor, save a milestone screenshot using: `save_milestone_screenshot(path="{self.remote_output_dir}\$FLOOR_NUMBER$.png")`, where $FLOOR_NUMBER$ is the floor number you reached.

Verification: 
The task is considered successful if:
- The reproduced game allows the same player operations as the original game.
- The player can reach the same game states (map layout, player status) as in the original game.
- The reproduced game functions correctly when run as an EXE, with no blocking issues in progression from Level 0 (the prologue if exists) to {self.MAX_LAYER}.

"""

    def to_metadata(self) -> dict:
        metadata = super().to_metadata()
        metadata.update({
            "game_url": self.game_url,
            "template_url": self.template_url,
        })
        return metadata

config = TaskConfig()


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

@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    """Initialize the environment by opening the game and replaying a trajectory."""
    logger.info(f"Setting up task: {task_cfg.metadata['game_url']}")
    
    try:
        await session.run_file(task_cfg.metadata['game_url'])

        # Clean up previous runs
        await session.remove_file(task_cfg.metadata['remote_output_dir'])
        await session.makedirs(task_cfg.metadata['remote_output_dir'])
        await session.copy_folder(task_cfg.metadata['template_url'], task_cfg.metadata['remote_output_dir'])

        # Open the template project on RPGMakerXP
        await session.run_file(fr"{task_cfg.metadata['remote_output_dir']}\mota_template\Game.rxproj")
    except Exception as e:
        logger.warning(f"Failed to setup tasks {config.TASK_TAG} via session: {e}")



@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the task based on the existence and content of the demo file."""

    try:
        output_dir = task_cfg.metadata["remote_output_dir"]
        reference_dir = task_cfg.metadata["reference_dir"]
        output_files, reference_files = await collect_matching_files(
            session, output_dir, reference_dir
        )

        prompt_with_question = lambda question: f"""You are evaluating a game screenshot.

        Compare these two images:
        1. First image: A screenshot from the reproduced using game engine RPGMakerXP
        2. Second image: A reference screenshot showing the original flash game screen.
        
        Question: {question}

        Answer with ONLY "YES" or "NO".
        """

        async with EvaluationContext(
            task_tag=config.TASK_TAG,
            mode="custom",
            output_dir=None,  # Use default
            target_path=output_dir,
            reference_path=reference_dir
        ) as ctx:
            # Evaluate matching files
            for file in reference_files:
                if file in output_files:
                    try:
                        target_file_path = os.path.join(output_dir, file)
                        reference_file_path = os.path.join(reference_dir, file)
                        identifier = os.path.splitext(file)[0]

                        logger.info(f"Evaluating output: {file}")

                        # Download images from remote server
                        target_image_bytes = await session.read_bytes(target_file_path)
                        reference_image_bytes = await session.read_bytes(reference_file_path)

                        # First judge if the file is developed using RPGMakerXP (no cheating)
                        question = """Does the first image show that the game is developed using RPGMakerXP? 
                        (One can identify wheter there is an "orange sun-like circle" in the top-left corner of the game window)
                        (If the game is not developed using RPGMakerXP, the answer should be "NO")
                        """
                        eval_result = await llm_vision_judge(
                            prompt=prompt_with_question(question),
                            image_bytes=target_image_bytes,
                            reference_image_bytes=reference_image_bytes,
                            return_details=True,
                            max_tokens=10,
                            eval_context=ctx,
                            identifier=f"{identifier}_rpgmaker_check"
                        )
                        
                        if eval_result["score"] == 0.0:
                            continue

                        # Then judge if the map layout is the same as in the original game
                        question = "Does the first image show with the same map layout as in the original game?"
                        eval_map = await llm_vision_judge(
                            prompt=prompt_with_question(question),
                            image_bytes=target_image_bytes,
                            reference_image_bytes=reference_image_bytes,
                            return_details=True,
                            max_tokens=10,
                            eval_context=ctx,
                            identifier=f"{identifier}_map_layout"
                        )
                        ctx.add_score(eval_map["score"] * 0.5)

                        # Then judge if the player status is the same as in the original game
                        question = "Does the first image show with the same player status as in the original game?"
                        eval_player = await llm_vision_judge(
                            prompt=prompt_with_question(question),
                            image_bytes=target_image_bytes,
                            reference_image_bytes=reference_image_bytes,
                            return_details=True,
                            max_tokens=10,
                            eval_context=ctx,
                            identifier=f"{identifier}_player_status"
                        )
                        ctx.add_score(eval_player["score"] * 0.5)

                    except Exception as e:
                        ctx.log_error(identifier=file, error=e)
                else:
                    logger.warning(f"Reference file {file} not found in output directory")

            # Finalize and return normalized score
            ctx.finalize(num_reference_files=len(reference_files), num_output_files=len(output_files))
            return [ctx.get_final_score(num_items=len(reference_files))]

    except Exception as e:
        logger.error(f"Evaluation error: {e}")

    return [0.0]
