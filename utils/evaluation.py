

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
    return_details: bool = False,
    eval_context: Optional["EvaluationContext"] = None,
    identifier: Optional[str] = None
) -> Union[str, float, dict]:
    """
    General-purpose LLM vision evaluation function supporting both single and dual image modes.

    Args:
        prompt: The question or instruction to send to the LLM
        image_bytes: Primary image to evaluate (required)
        reference_image_bytes: Optional reference image for comparison mode.
                              If provided, the LLM will see both images.
        model: OpenAI model to use (default: "gpt-5.2")
        max_tokens: Maximum tokens for the response
        return_binary_score: If True, parses response for YES/NO and returns 1.0/0.0.
                            If False, returns the raw text response.
        api_key: OpenAI API key. If None, uses OPENAI_API_KEY from environment.
        return_details: If True, returns a dict with full details including VLM response,
                       score, prompt, model, etc. Overrides return_binary_score.
        eval_context: Optional EvaluationContext for automatic logging. When provided,
                     the result will be automatically logged to the context.
        identifier: Identifier for logging (required if eval_context is provided)

    Returns:
        - dict with full evaluation details if return_details=True
        - float (0.0-1.0) if return_binary_score=True
        - str with LLM response otherwise
    """
    result = None
    error_msg = None
    
    try:
        # Initialize OpenAI client
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        api_base = os.environ.get("OPENAI_API_BASE")
        
        # Create client with base_url if OPENAI_API_BASE is set (e.g., for LiteLLM)
        if api_base:
            client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        else:
            client = AsyncOpenAI(api_key=api_key)

        # Build content array
        primary_b64 = base64.b64encode(image_bytes).decode('utf-8')
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{primary_b64}"}}
        ]

        # Add reference image if in comparison mode
        mode = "single"
        if reference_image_bytes is not None:
            reference_b64 = base64.b64encode(reference_image_bytes).decode('utf-8')
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{reference_b64}"}
            })
            mode = "comparison"

        # Call OpenAI Vision API
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            max_completion_tokens=max_tokens
        )

        # Parse response
        answer = response.choices[0].message.content.strip()
        logger.info(f"LLM vision judge ({mode} mode): {answer}")

        # Calculate score if needed
        score = 1.0 if "YES" in answer.upper() else 0.0 if (return_binary_score or return_details or eval_context) else None

        result = {
            "vlm_response": answer,
            "score": score,
            "prompt": prompt,
            "model": model,
            "mode": mode,
            "max_tokens": max_tokens,
            "error": None
        }

    except Exception as e:
        logger.error(f"Error in llm_vision_judge: {e}")
        error_msg = f"Error: {str(e)}"
        mode = "comparison" if reference_image_bytes else "single"

        result = {
            "vlm_response": None,
            "score": 0.0,
            "prompt": prompt,
            "model": model,
            "mode": mode,
            "max_tokens": max_tokens,
            "error": error_msg
        }

    # Auto-log to EvaluationContext if provided
    if eval_context is not None and identifier is not None:
        eval_context.log_evaluation(
            identifier=identifier,
            score=result["score"],
            vlm_response=result["vlm_response"],
            prompt=result["prompt"],
            model=result["model"],
            error=result["error"]
        )

    # Return based on requested format
    if return_details:
        return result
    elif return_binary_score:
        return result["score"]
    else:
        return result["vlm_response"] if result["vlm_response"] else error_msg


async def llm_vision_judge_single(
    prompt: str,
    image_bytes: bytes,
    eval_context: Optional["EvaluationContext"] = None,
    identifier: Optional[str] = None,
    **kwargs
) -> Union[str, float, dict]:
    """Simplified single-image LLM vision evaluation function."""
    return await llm_vision_judge(
        prompt=prompt,
        image_bytes=image_bytes,
        reference_image_bytes=None,
        eval_context=eval_context,
        identifier=identifier,
        **kwargs
    )


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


class EvaluationContext:
    """
    Context manager for tracking and logging evaluation results automatically.
    
    Usage:
        async with EvaluationContext(task_tag="my_task", mode="custom") as ctx:
            for file in files:
                result = await llm_vision_judge(...)
                ctx.log_evaluation(
                    identifier=file,
                    score=result["score"],
                    vlm_response=result["vlm_response"],
                    # ... any additional fields
                )
                ctx.add_score(result["score"] * weight)
            
            return [ctx.get_final_score(num_items=len(files))]
    """
    
    def __init__(
        self,
        task_tag: str,
        mode: str = "custom",
        output_dir: Optional[str] = None,
        auto_save: bool = True,
        **extra_metadata
    ):
        """
        Initialize evaluation context.
        
        Args:
            task_tag: Identifier for the task
            mode: Evaluation mode name (e.g., "milestone", "custom", "deliverable")
            output_dir: Directory for saving results
            auto_save: Whether to automatically save results on context exit
            **extra_metadata: Additional metadata to include in evaluation details
        """
        self.task_tag = task_tag
        self.mode = mode
        self.output_dir = output_dir
        self.auto_save = auto_save
        
        self.evaluation_details = {
            "mode": mode,
            "task_tag": task_tag,
            "timestamp": datetime.now().isoformat(),
            "evaluations": [],
            **extra_metadata
        }
        self._total_score = 0.0
        self._num_evaluated = 0
        self._finalized = False
    
    def log_evaluation(
        self,
        identifier: str,
        score: float,
        vlm_response: Optional[str] = None,
        prompt: Optional[str] = None,
        model: Optional[str] = None,
        error: Optional[str] = None,
        **extra_fields
    ) -> None:
        """
        Log a single evaluation result with automatic logging.
        
        Args:
            identifier: Unique identifier for this evaluation (e.g., filename, milestone)
            score: Score for this evaluation (0.0-1.0)
            vlm_response: Optional VLM response text
            prompt: Optional prompt used
            model: Optional model name
            error: Optional error message
            **extra_fields: Any additional fields to store
        """
        eval_entry = {
            "identifier": identifier,
            "score": score,
            "vlm_response": vlm_response,
            "prompt": prompt,
            "model": model,
            "error": error,
            **extra_fields
        }
        # Remove None values for cleaner output
        eval_entry = {k: v for k, v in eval_entry.items() if v is not None}
        
        self.evaluation_details["evaluations"].append(eval_entry)
        self._num_evaluated += 1
        
        # Automatic logging
        if vlm_response:
            logger.info(f"Identifier '{identifier}' VLM response: {vlm_response}")
        logger.info(f"Identifier '{identifier}' judgment score: {score}")
        if error:
            logger.error(f"Identifier '{identifier}' error: {error}")
    
    def log_error(self, identifier: str, error: Union[str, Exception], score: float = 0.0) -> None:
        """Log an evaluation error."""
        error_msg = str(error)
        self.log_evaluation(identifier=identifier, score=score, error=error_msg)
        logger.error(f"Error evaluating identifier '{identifier}': {error_msg}")
    
    def add_score(self, score: float) -> None:
        """Add to the cumulative total score."""
        self._total_score += score
    
    def get_final_score(self, num_items: Optional[int] = None) -> float:
        """
        Get the final normalized score.
        
        Args:
            num_items: If provided, divides total_score by this number.
                      If None, returns raw total_score.
        """
        if num_items and num_items > 0:
            return self._total_score / num_items
        return self._total_score
    
    @property
    def total_score(self) -> float:
        """Get the raw cumulative score."""
        return self._total_score
    
    @property
    def num_evaluated(self) -> int:
        """Get the number of evaluations logged."""
        return self._num_evaluated
    
    def finalize(self, **extra_summary) -> tuple[float, dict]:
        """
        Finalize evaluation, add summary, and save results.
        
        Args:
            **extra_summary: Additional fields to include in summary
            
        Returns:
            Tuple of (final_score, evaluation_details)
        """
        if self._finalized:
            return self._total_score, self.evaluation_details
        
        self.evaluation_details["summary"] = {
            "total_score": self._total_score,
            "num_evaluated": self._num_evaluated,
            **extra_summary
        }
        
        logger.info(f"Evaluation complete. Total score: {self._total_score} ({self._num_evaluated} evaluated)")
        
        if self.auto_save:
            save_evaluation_results(self.evaluation_details, self.task_tag, self.output_dir)
        
        self._finalized = True
        return self._total_score, self.evaluation_details
    
    async def __aenter__(self) -> "EvaluationContext":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Async context manager exit - auto-finalize on success."""
        if exc_type is None and not self._finalized:
            self.finalize()
        return False
    
    def __enter__(self) -> "EvaluationContext":
        """Sync context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Sync context manager exit - auto-finalize on success."""
        if exc_type is None and not self._finalized:
            self.finalize()
        return False


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

    async with EvaluationContext(
        task_tag=task_tag,
        mode="milestone",
        output_dir=output_dir,
        target_path=target_path,
        reference_path=reference_path
    ) as ctx:
        # Evaluate matching files
        for file in target_files:
            if file in reference_files:
                try:
                    target_file_path = os.path.join(target_path, file)
                    reference_file_path = os.path.join(reference_path, file)
                    identifier = os.path.splitext(file)[0]

                    logger.info(f"Evaluating milestone: {file}")

                    # Download images from remote server
                    target_image_bytes = await session.read_bytes(target_file_path)
                    reference_image_bytes = await session.read_bytes(reference_file_path)

                    # Compare screenshots
                    eval_result = await comparison_fn(
                        target_image_bytes, reference_image_bytes, identifier
                    )

                    score = eval_result["score"]
                    ctx.log_evaluation(
                        identifier=identifier,
                        score=score,
                        vlm_response=eval_result["vlm_response"],
                        prompt=eval_result["prompt"],
                        model=eval_result["model"],
                        mode=eval_result["mode"],
                        error=eval_result["error"],
                        target_file_path=target_file_path,
                        reference_file_path=reference_file_path,
                        file=file
                    )
                    ctx.add_score(score / len(reference_files))

                except Exception as e:
                    ctx.log_error(identifier=file, error=e)

        return ctx.finalize(
            num_reference_files=len(reference_files),
            num_target_files=len(target_files)
        )


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
    """
    from cua_bench import replay_trajectory

    async with EvaluationContext(
        task_tag=task_tag,
        mode="deliverable",
        output_dir=output_dir,
        trajectory_dir=str(trajectory_dir),
        reference_path=reference_path,
        screenshot_points=screenshot_points
    ) as ctx:
        try:
            # Get reference files to know what to compare
            reference_files = await session.list_dir(reference_path)

            # Replay trajectory with screenshots at specified points
            logger.info(f"Replaying trajectory from: {trajectory_dir}")

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
                        point_index = screenshot_points.index(i + 1)
                        if point_index < len(reference_files):
                            identifier = os.path.splitext(reference_files[point_index])[0]
                            screenshots_taken[identifier] = screenshot_bytes
                            logger.info(f"Screenshot taken at action {i+1} for identifier '{identifier}'")
                    except Exception as e:
                        logger.error(f"Failed to take screenshot at action {i+1}: {e}")

                await asyncio.sleep(action_delay)

            # Now compare screenshots with references
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
                        ctx.log_evaluation(
                            identifier=identifier,
                            score=score,
                            vlm_response=eval_result["vlm_response"],
                            prompt=eval_result["prompt"],
                            model=eval_result["model"],
                            mode=eval_result["mode"],
                            error=eval_result["error"],
                            reference_file=ref_file,
                            reference_file_path=reference_file_path
                        )
                        ctx.add_score(score / len(reference_files))

                    except Exception as e:
                        ctx.log_error(identifier=identifier, error=e)
                else:
                    ctx.log_evaluation(
                        identifier=identifier,
                        score=0.0,
                        error="No screenshot taken at corresponding point"
                    )

            return ctx.finalize(
                num_reference_files=len(reference_files),
                num_screenshots_taken=len(screenshots_taken),
                total_actions_replayed=len(actions_to_execute)
            )

        except Exception as e:
            logger.error(f"Error in deliverable evaluation: {e}")
            ctx.evaluation_details["error"] = str(e)
            return ctx.finalize(error=str(e))
