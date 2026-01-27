

from openai import AsyncOpenAI
import asyncio
import base64
import os
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from cua_bench.computers.base import DesktopSession

logger = logging.getLogger(__name__)


async def llm_vision_judge(
    prompt: str,
    image_bytes: bytes,
    reference_image_bytes: Optional[bytes] = None,
    model: str = "gpt-5.2",
    max_tokens: int = 2048,
    return_binary_score: bool = False,
    api_key: Optional[str] = None,
    return_details: bool = False
) -> Union[str, float, dict]:
    """
    General-purpose LLM vision evaluation function supporting both single and dual image modes.

    Args:
        prompt: The question or instruction to send to the LLM
        image_bytes: Primary image to evaluate (required)
        reference_image_bytes: Optional reference image for comparison mode.
                              If provided, the LLM will see both images.
        model: OpenAI model to use (default: "gpt-4o")
        max_tokens: Maximum tokens for the response
        return_binary_score: If True, parses response for YES/NO and returns 1.0/0.0.
                            If False, returns the raw text response.
        api_key: OpenAI API key. If None, uses OPENAI_API_KEY from environment.
        return_details: If True, returns a dict with full details including VLM response,
                       score, prompt, model, etc. Overrides return_binary_score.

    Returns:
        - dict with full evaluation details if return_details=True
        - float (0.0-1.0) if return_binary_score=True
        - str with LLM response otherwise

    Example usage:
        # Get full details including VLM response
        result = await llm_vision_judge(
            prompt="What floor is the player on?",
            image_bytes=screenshot,
            return_details=True
        )
        # Returns: {"vlm_response": "...", "score": 1.0, "prompt": "...", ...}

        # Get just the score
        score = await llm_vision_judge(
            prompt="Do these two images show the same game state?",
            image_bytes=target_screenshot,
            reference_image_bytes=reference_screenshot,
            return_binary_score=True
        )
    """
    try:
        # Initialize OpenAI client
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        client = AsyncOpenAI(api_key=api_key)

        # Encode primary image to base64
        primary_b64 = base64.b64encode(image_bytes).decode('utf-8')

        # Build content array starting with the prompt
        content = [{"type": "text", "text": prompt}]

        # Add primary image
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{primary_b64}"
            }
        })

        # Add reference image if in comparison mode
        if reference_image_bytes is not None:
            reference_b64 = base64.b64encode(reference_image_bytes).decode('utf-8')
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{reference_b64}"
                }
            })
            mode = "comparison"
        else:
            mode = "single"

        # Call OpenAI Vision API
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": content
                }
            ],
            max_completion_tokens=max_tokens
        )

        # Parse response
        answer = response.choices[0].message.content.strip()
        logger.info(f"LLM vision judge ({mode} mode): {answer}")

        # Calculate score if needed
        score = None
        if return_binary_score or return_details:
            answer_upper = answer.upper()
            score = 1.0 if "YES" in answer_upper else 0.0

        # Return full details if requested
        if return_details:
            return {
                "vlm_response": answer,
                "score": score,
                "prompt": prompt,
                "model": model,
                "mode": mode,
                "max_tokens": max_tokens,
                "error": None
            }

        # Return binary score or raw text
        if return_binary_score:
            return score
        else:
            return answer

    except Exception as e:
        logger.error(f"Error in llm_vision_judge: {e}")
        error_msg = f"Error: {str(e)}"

        if return_details:
            return {
                "vlm_response": None,
                "score": 0.0,
                "prompt": prompt,
                "model": model,
                "mode": "comparison" if reference_image_bytes else "single",
                "max_tokens": max_tokens,
                "error": error_msg
            }

        return 0.0 if return_binary_score else error_msg


async def compare_screenshots_game(
    target_image_bytes: bytes,
    reference_image_bytes: bytes,
    context_description: str,
    comparison_criteria: Optional[str] = None
) -> dict:
    """
    Compare target and reference screenshots using VLM.

    Args:
        target_image_bytes: The screenshot to evaluate
        reference_image_bytes: The reference screenshot
        context_description: Description of what's being compared (e.g., "floor 3")
        comparison_criteria: Optional additional criteria for comparison

    Returns:
        Dictionary with evaluation details (score, vlm_response, prompt, etc.)
    """
    criteria = comparison_criteria or ""

    prompt = f"""You are evaluating a game screenshot.

Compare these two images:
1. First image: A screenshot from the agent's playthrough
2. Second image: A reference screenshot showing the correct state ({context_description})

Question: Does the first image show that the player has successfully reached the same state as the reference image for {context_description}?

Please analyze:
{criteria}

Answer with ONLY "YES" or "NO"."""

    return await llm_vision_judge(
        prompt=prompt,
        image_bytes=target_image_bytes,
        reference_image_bytes=reference_image_bytes,
        return_details=True,
        max_tokens=10
    )


async def collect_matching_files(
    session: "DesktopSession",
    target_path: str,
    reference_path: str
) -> tuple[list[str], list[str]]:
    """
    Collect files from target and reference directories.

    Args:
        session: Desktop session for file operations
        target_path: Path to target directory
        reference_path: Path to reference directory

    Returns:
        Tuple of (target_files, reference_files)
    """
    target_files = await session.list_dir(target_path)
    reference_files = await session.list_dir(reference_path)
    return target_files, reference_files


def save_evaluation_results(
    evaluation_details: dict,
    task_tag: str,
    output_dir: Optional[str] = None
) -> Optional[str]:
    """
    Save evaluation results to a JSON file.

    Args:
        evaluation_details: Dictionary containing all evaluation details
        task_tag: Tag identifying the task
        output_dir: Optional directory to save results (defaults to ./trycua/cua-bench/)

    Returns:
        Path to saved JSON file, or None if saving failed
    """
    try:
        output_dir = output_dir or os.environ.get("EVALUATION_OUTPUT_DIR", "./trycua/cua-bench/")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_filename = f"{task_tag}_evaluation_{timestamp}.json"
        json_filepath = os.path.join(output_dir, json_filename)

        with open(json_filepath, 'w') as f:
            json.dump(evaluation_details, f, indent=2)

        logger.info(f"Evaluation details saved to: {json_filepath}")
        return json_filepath
    except Exception as e:
        logger.error(f"Failed to save evaluation details to JSON: {e}")
        return None


async def evaluate_milestone_mode(
    session: "DesktopSession",
    target_path: str,
    reference_path: str,
    task_tag: str,
    comparison_fn: callable,
    output_dir: Optional[str] = None
) -> tuple[float, dict]:
    """
    Evaluate using milestone mode: compare agent-saved screenshots with references.

    Args:
        session: Desktop session for file operations
        target_path: Directory containing agent-saved milestone screenshots
        reference_path: Directory containing reference screenshots
        task_tag: Task identifier
        comparison_fn: Function to compare screenshots, signature:
                      async fn(target_bytes, reference_bytes, identifier) -> dict
        output_dir: Optional directory for saving evaluation results

    Returns:
        Tuple of (final_score, evaluation_details)
    """
    # Check if target directory exists
    exists = await session.exists(target_path)
    if not exists:
        logger.info(f"Evaluation: File NOT found at {target_path}")
        return 0.0, {"error": f"Target path not found: {target_path}"}

    # Collect files
    target_files, reference_files = await collect_matching_files(
        session, target_path, reference_path
    )

    evaluation_details = {
        "mode": "milestone",
        "task_tag": task_tag,
        "timestamp": datetime.now().isoformat(),
        "target_path": target_path,
        "reference_path": reference_path,
        "evaluations": []
    }

    total_scores = 0.0
    num_evaluated = 0

    # Evaluate matching files
    for file in target_files:
        if file in reference_files:
            try:
                target_file_path = os.path.join(target_path, file)
                reference_file_path = os.path.join(reference_path, file)

                logger.info(f"Evaluating milestone: {file}")

                # Download images from remote server
                target_image_bytes = await session.read_bytes(target_file_path)
                reference_image_bytes = await session.read_bytes(reference_file_path)

                # Extract identifier from filename
                identifier = os.path.splitext(file)[0]

                # Compare screenshots
                eval_result = await comparison_fn(
                    target_image_bytes, reference_image_bytes, identifier
                )

                score = eval_result["score"]

                # Store detailed evaluation info
                evaluation_details["evaluations"].append({
                    "file": file,
                    "identifier": identifier,
                    "target_file_path": target_file_path,
                    "reference_file_path": reference_file_path,
                    "score": score,
                    "vlm_response": eval_result["vlm_response"],
                    "prompt": eval_result["prompt"],
                    "model": eval_result["model"],
                    "mode": eval_result["mode"],
                    "error": eval_result["error"]
                })

                logger.info(f"Identifier '{identifier}' VLM response: {eval_result['vlm_response']}")
                logger.info(f"Identifier '{identifier}' judgment score: {score}")
                total_scores += score / len(reference_files)
                num_evaluated += 1

            except Exception as e:
                logger.error(f"Error evaluating file {file}: {e}")
                evaluation_details["evaluations"].append({
                    "file": file,
                    "identifier": os.path.splitext(file)[0],
                    "error": str(e),
                    "score": 0.0
                })

    # Calculate final score
    final_score = total_scores if num_evaluated > 0 else 0.0

    # Add summary
    evaluation_details["summary"] = {
        "total_score": final_score,
        "num_evaluated": num_evaluated,
        "num_reference_files": len(reference_files),
        "num_target_files": len(target_files)
    }

    logger.info(f"Evaluation complete. Total score: {final_score} ({num_evaluated} files evaluated)")

    # Save results
    save_evaluation_results(evaluation_details, task_tag, output_dir)

    return final_score, evaluation_details

######## TODO: DELIVERABLE MODE (IN DEVELOPMENT) ########

async def evaluate_deliverable_mode(
    session: "DesktopSession",
    trajectory_dir: str,
    reference_path: str,
    task_tag: str,
    comparison_fn: callable,
    screenshot_points: list[int],
    action_delay: float = 0.5,
    output_dir: Optional[str] = None
) -> tuple[float, dict]:
    """
    Evaluate using deliverable mode: replay trajectory and take screenshots at specified points.

    Args:
        session: Desktop session for file operations
        trajectory_dir: Directory containing agent trajectory files
        reference_path: Directory containing reference screenshots
        task_tag: Task identifier
        comparison_fn: Function to compare screenshots, signature:
                      async fn(target_bytes, reference_bytes, identifier) -> dict
        screenshot_points: List of action indices where screenshots should be taken
                          (e.g., [10, 20, 30] means take screenshots after actions 10, 20, 30)
        action_delay: Delay between actions during replay (seconds)
        output_dir: Optional directory for saving evaluation results

    Returns:
        Tuple of (final_score, evaluation_details)
    """
    from cua_bench import replay_trajectory

    evaluation_details = {
        "mode": "deliverable",
        "task_tag": task_tag,
        "timestamp": datetime.now().isoformat(),
        "trajectory_dir": str(trajectory_dir),
        "reference_path": reference_path,
        "screenshot_points": screenshot_points,
        "evaluations": []
    }

    try:
        # Get reference files to know what to compare
        reference_files = await session.list_dir(reference_path)

        # Replay trajectory with screenshots at specified points
        logger.info(f"Replaying trajectory from: {trajectory_dir}")

        # We'll need to modify replay_trajectory or create a custom version
        # For now, let's replay and take screenshots manually
        from pathlib import Path
        import json

        trajectory_path = Path(trajectory_dir)
        if not trajectory_path.exists():
            raise FileNotFoundError(f"Trajectory directory not found: {trajectory_dir}")

        # Find latest agent response file
        response_files = sorted(trajectory_path.rglob("*_agent_response.json"))
        if not response_files:
            raise ValueError(f"No agent_response.json files found in {trajectory_dir}")

        latest_response_file = response_files[-1]
        logger.info(f"Using trajectory file: {latest_response_file.name}")

        # Load and extract actions
        with open(latest_response_file, "r") as f:
            data = json.load(f)

        messages = data.get("kwargs", {}).get("messages", [])
        actions_to_execute = []
        for item in messages:
            if isinstance(item, dict) and item.get("type") == "computer_call":
                action = item.get("action", {})
                action_type = action.get("type")
                if action_type and action_type != "screenshot":
                    actions_to_execute.append(action)

        logger.info(f"Found {len(actions_to_execute)} actions to replay")

        # Import computer handler
        from agent.computers import cuaComputerHandler
        handler = cuaComputerHandler(session._computer)
        await handler._initialize()

        # Replay actions and take screenshots at specified points
        screenshots_taken = {}

        for i, action in enumerate(actions_to_execute):
            action_type = action.get("type")
            action_args = {k: v for k, v in action.items() if k != "type"}

            logger.info(f"[{i+1}/{len(actions_to_execute)}] Executing: {action_type}({action_args})")

            method = getattr(handler, action_type, None)
            if method:
                try:
                    await method(**action_args)
                except Exception as e:
                    logger.error(f"Action {action_type} failed: {e}")

            # Take screenshot if at a screenshot point
            if i + 1 in screenshot_points:
                try:
                    screenshot_bytes = await session.screenshot()
                    # Map this screenshot to corresponding reference file
                    # Assuming screenshot_points indices map to reference files by index
                    point_index = screenshot_points.index(i + 1)
                    if point_index < len(reference_files):
                        identifier = os.path.splitext(reference_files[point_index])[0]
                        screenshots_taken[identifier] = screenshot_bytes
                        logger.info(f"Screenshot taken at action {i+1} for identifier '{identifier}'")
                except Exception as e:
                    logger.error(f"Failed to take screenshot at action {i+1}: {e}")

            await asyncio.sleep(action_delay)

        # Now compare screenshots with references
        total_scores = 0.0
        num_evaluated = 0

        for ref_file in reference_files:
            identifier = os.path.splitext(ref_file)[0]

            if identifier in screenshots_taken:
                try:
                    reference_file_path = os.path.join(reference_path, ref_file)
                    reference_image_bytes = await session.read_bytes(reference_file_path)
                    target_image_bytes = screenshots_taken[identifier]

                    logger.info(f"Evaluating deliverable: {identifier}")

                    # Compare screenshots
                    eval_result = await comparison_fn(
                        target_image_bytes, reference_image_bytes, identifier
                    )

                    score = eval_result["score"]

                    evaluation_details["evaluations"].append({
                        "identifier": identifier,
                        "reference_file": ref_file,
                        "reference_file_path": reference_file_path,
                        "score": score,
                        "vlm_response": eval_result["vlm_response"],
                        "prompt": eval_result["prompt"],
                        "model": eval_result["model"],
                        "mode": eval_result["mode"],
                        "error": eval_result["error"]
                    })

                    logger.info(f"Identifier '{identifier}' VLM response: {eval_result['vlm_response']}")
                    logger.info(f"Identifier '{identifier}' judgment score: {score}")
                    total_scores += score / len(reference_files)
                    num_evaluated += 1

                except Exception as e:
                    logger.error(f"Error evaluating identifier {identifier}: {e}")
                    evaluation_details["evaluations"].append({
                        "identifier": identifier,
                        "error": str(e),
                        "score": 0.0
                    })
            else:
                logger.warning(f"No screenshot taken for identifier '{identifier}'")
                evaluation_details["evaluations"].append({
                    "identifier": identifier,
                    "error": "No screenshot taken at corresponding point",
                    "score": 0.0
                })

        # Calculate final score
        final_score = total_scores if num_evaluated > 0 else 0.0

        # Add summary
        evaluation_details["summary"] = {
            "total_score": final_score,
            "num_evaluated": num_evaluated,
            "num_reference_files": len(reference_files),
            "num_screenshots_taken": len(screenshots_taken),
            "total_actions_replayed": len(actions_to_execute)
        }

        logger.info(f"Deliverable evaluation complete. Total score: {final_score} ({num_evaluated} evaluated)")

    except Exception as e:
        logger.error(f"Error in deliverable evaluation: {e}")
        evaluation_details["error"] = str(e)
        evaluation_details["summary"] = {
            "total_score": 0.0,
            "num_evaluated": 0,
            "error": str(e)
        }
        final_score = 0.0

    # Save results
    save_evaluation_results(evaluation_details, task_tag, output_dir)

    return final_score, evaluation_details
