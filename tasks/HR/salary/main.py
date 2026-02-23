"""
HR Salary Calculation Task - Payroll Processing Evaluation

This task evaluates an AI agent's ability to process complex payroll scenarios
through the Gusto web GUI and produce accurate pay stubs.
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from utils.evaluation import llm_vision_judge, EvaluationContext

from PIL import Image
import io

logger = logging.getLogger(__name__)


def _blank_png_bytes() -> bytes:
    img = Image.new("RGB", (8, 8), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "salary"
    TASK_CATEGORY: str = "HR"

    @property
    def tasks_file(self) -> str:
        return fr"{self.task_dir}\input\tasks.json"

    @property
    def ground_truth_file(self) -> str:
        return fr"{self.task_dir}\reference\ground_truth.json"

    @property
    def task_description(self) -> str:
        return f"""
Goal: Complete 45 payroll processing tasks using the Gusto Demo web GUI.

Instructions:
1. Read the task descriptions from: {self.tasks_file}
2. For each task (ID 1-45):
   - Navigate to Gusto Demo web GUI
   - Create the employee as described
   - Run the payroll
   - Navigate to the pay stub page showing both Employee Name and Net Pay
   - Save a screenshot: save_milestone_screenshot(path="{self.remote_output_dir}\\task_{{task_id:02d}}_paystub.png")
     Example: For task 1, save as "task_01_paystub.png"

Requirements:
- Use ONLY the Gusto web GUI (no API calls)
- Each screenshot must clearly show:
  * The Gusto web interface
  * The employee name
  * The Net Pay amount
- Complete all 45 tasks

Scoring:
- Each task is worth 1/45 of the total score
- A task gets full credit if:
  * Screenshot shows Gusto GUI
  * Employee name matches expected
  * Net Pay matches expected
"""


config = TaskConfig()


@cb.tasks_config(split="train")
def load():
    """Define the HR Salary Calculation task."""
    return [
        cb.Task(
            description=config.task_description,
            metadata=config.to_metadata(),
            computer={
                "provider": "computer",
                "setup_config": {"os_type": config.OS_TYPE},
            },
        )
    ]


@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    """Setup the task environment - clears local config files."""

    # Clean up previous output directory
    try:
        await session.remove_file(task_cfg.metadata["remote_output_dir"])
    except Exception:
        pass
    await session.makedirs(task_cfg.metadata["remote_output_dir"])
    
    # TODO: Clean up previous demo company

    logger.info("Setup complete")


@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession):
    """Evaluate all 45 payroll tasks and return a normalized score."""

    # Load ground truth from remote reference directory
    reference_dir = task_cfg.metadata["reference_dir"]
    ground_truth_path = fr"{reference_dir}\ground_truth.json"

    # Read ground truth from remote machine
    ground_truth_content = await session.read_file(ground_truth_path)
    # session.read_file returns str, not bytes
    if isinstance(ground_truth_content, bytes):
        ground_truth = json.loads(ground_truth_content.decode('utf-8'))
    else:
        ground_truth = json.loads(ground_truth_content)

    gt_tasks = ground_truth.get("tasks", {})
    total_tasks = 45
    correct_tasks = 0

    # Create evaluation context
    ctx = EvaluationContext(
        task_tag=task_cfg.metadata.get("task_tag", "salary"),
        mode="payroll_verification",
        output_dir=os.environ.get("EVALUATION_OUTPUT_DIR", "./trycua/cua-bench/")
    )

    # Evaluate each task
    for task_id in range(1, total_tasks + 1):
        tid_str = str(task_id)

        if tid_str not in gt_tasks:
            logger.info(f"[task {task_id:02d}] Missing in ground_truth.json")
            ctx.log_error(f"task_{task_id:02d}", "Missing in ground_truth.json", score=0.0)
            continue

        gt_task = gt_tasks[tid_str]
        expected_net_pay = gt_task.get("net_pay")
        expected_employee_name = gt_task.get("employee_name", "").strip()

        if expected_net_pay is None:
            logger.info(f"[task {task_id:02d}] Missing expected_net_pay")
            ctx.log_error(f"task_{task_id:02d}", "Missing expected_net_pay", score=0.0)
            continue

        screenshot_path = fr"{task_cfg.metadata['remote_output_dir']}\task_{task_id:02d}_paystub.png"

        # Read screenshot as binary
        try:
            img_bytes = await session.read_bytes(screenshot_path)
        except Exception as e:
            logger.info(f"[task {task_id:02d}] Missing screenshot: {e}")
            ctx.log_error(f"task_{task_id:02d}", f"Missing screenshot: {e}", score=0.0)
            continue

        # Use VLM to extract information from screenshot
        blank_ref = _blank_png_bytes()

        extract_prompt = f"""
Look at this screenshot and extract the following information:

1. Is this a Gusto web GUI showing a pay stub page? (answer: yes or no)
2. What is the employee name shown on the pay stub?
3. What is the Net Pay amount shown on the pay stub?

Respond in JSON format:
{{"is_gusto_gui": "yes/no", "employee_name": "exact name from screenshot", "net_pay": "amount as number"}}

If you cannot find the information, use null for that field.
"""

        try:
            result = await llm_vision_judge(
                prompt=extract_prompt,
                image_bytes=img_bytes,
                reference_image_bytes=blank_ref,
                return_details=True,
                max_tokens=100,
                eval_context=ctx,
                identifier=f"task_{task_id:02d}_extract"
            )

            extraction_details = result["vlm_response"]
            logger.info(f"[task {task_id:02d}] extraction={extraction_details}")

            # Parse extracted data
            json_match = re.search(r'\{.*\}', str(extraction_details), re.DOTALL)
            if json_match:
                try:
                    extracted = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    extracted = {}
            else:
                extracted = {}

            is_gusto = str(extracted.get("is_gusto_gui", "")).lower() == "yes"
            extracted_name = str(extracted.get("employee_name", "")).strip()
            extracted_net_pay_str = str(extracted.get("net_pay", ""))

            # Parse net pay
            extracted_net_pay = None
            if extracted_net_pay_str:
                clean_amount = re.sub(r'[$,]', '', extracted_net_pay_str)
                try:
                    extracted_net_pay = float(clean_amount)
                except:
                    pass

            # Validate
            task_correct = False
            reason = []

            if not is_gusto:
                reason.append("Not Gusto GUI")
            elif not extracted_name or extracted_name.lower() != expected_employee_name.lower():
                reason.append(f"Name mismatch: '{extracted_name}' vs '{expected_employee_name}'")
            elif extracted_net_pay is None:
                reason.append("Could not extract Net Pay")
            elif abs(extracted_net_pay - float(expected_net_pay)) > 0.01:
                reason.append(f"Net Pay mismatch: ${extracted_net_pay:.2f} vs ${float(expected_net_pay):.2f}")
            else:
                task_correct = True
                reason.append("Correct")

            if task_correct:
                correct_tasks += 1
                ctx.add_score(1.0)

            logger.info(f"[task {task_id:02d}] {'; '.join(reason)}")

        except Exception as e:
            logger.error(f"[task {task_id:02d}] Error during evaluation: {e}")
            ctx.log_error(f"task_{task_id:02d}", f"Evaluation error: {e}", score=0.0)

    # Calculate final score
    final_score = correct_tasks / total_tasks
    logger.info(f"Final score: {correct_tasks}/{total_tasks} = {final_score:.4f}")

    # Finalize context and save results
    ctx.finalize(
        total_tasks=total_tasks,
        correct_tasks=correct_tasks,
        final_score=final_score
    )

    return [final_score]
