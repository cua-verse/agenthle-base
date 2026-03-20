"""PCB Routing Design Task - Hardware Design Benchmark."""

import os
import logging
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from tasks.hardware.PCB_Routing.eval import (
    count_trace_segments,
    count_filled_zone_polygons,
    parse_drc_json,
)
from utils.evaluation import llm_vision_judge, EvaluationContext

logger = logging.getLogger(__name__)


def _cmd_stdout(result):
    """Extract stdout string from run_command result (may be dict or str)."""
    if isinstance(result, dict):
        return result.get("stdout", "")
    return result or ""


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "PCB_Routing"
    TASK_CATEGORY: str = "hardware"
    OS_TYPE: str = "windows"

    # KiCad CLI path on the VM
    KICAD_CLI_PATH: str = os.environ.get("KICAD_CLI_PATH", "kicad-cli")

    # Filenames
    PCB_FILE: str = "Breadboard_power_supply.kicad_pcb"
    PROJECT_FILE: str = "Breadboard_power_supply.kicad_pro"
    SCHEMATIC_FILE: str = "Breadboard_power_supply.kicad_sch"
    DRC_SCREENSHOT: str = "drc_screenshot.png"
    REFERENCE_DRC_SCREENSHOT: str = "reference_drc_screenshot.png"

    # Eval thresholds
    MIN_TRACE_SEGMENTS: int = 50

    @property
    def task_dir(self):
        return f"{self.REMOTE_ROOT_DIR}\\{self.TASK_CATEGORY}\\{self.TASK_TAG}"

    @property
    def task_description(self):
        return f"""Route a breadboard power supply PCB in KiCad.

        Environment:
        - KiCad is already open with a project loaded containing a breadboard power supply design.
        - The schematic is complete — do not modify it.
        - The PCB editor shows all component footprints placed inside the board outline.
        - Blue ratsnest lines show connections that need copper traces between them.
        - A ground zone boundary is defined but unfilled.

        Your task:
        1. Use PCB Editor to Route all connections by drawing copper traces between pads connected by ratsnest lines
        2. Fill the ground zone to connect all ground pads
        3. Run the Design Rules Checker and navigate to the Unconnected Items tab
            - Focus only on unconnected items, not violations/errors
        4. Save a screenshot of the DRC results using save_milestone_screenshot(path="{self.task_dir}\\output\\{self.DRC_SCREENSHOT}")
        5. Generate Gerber files
        6. Generate drill files

        Do not ask for confirmation. Execute each step directly.
        """

    def to_metadata(self):
        metadata = super().to_metadata()
        metadata.update({
            "min_trace_segments": self.MIN_TRACE_SEGMENTS,
        })
        return metadata


config = TaskConfig()


@cb.tasks_config(split="train")
def load():
    return [
        cb.Task(
            description=config.task_description,
            metadata=config.to_metadata(),
            computer={
                "provider": "computer",
                "setup_config": {
                    "os_type": config.OS_TYPE,
                }
            },
        )
    ]


@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    logger.info(f"Setting up task: {config.TASK_TAG}")

    try:
        output_dir = task_cfg.metadata["remote_output_dir"]
        input_dir = os.path.join(os.path.dirname(output_dir), "input")

        # Clean and create output directory
        await session.remove_file(output_dir)
        await session.makedirs(output_dir)

        # Copy KiCad project files from input to output
        for filename in [config.PCB_FILE, config.PROJECT_FILE, config.SCHEMATIC_FILE]:
            src = os.path.join(input_dir, filename)
            dst = os.path.join(output_dir, filename)
            await session.run_command(
                f'powershell -Command "Copy-Item \'{src}\' \'{dst}\'"'
            )

        # Open KiCad with the project
        project_file = os.path.join(output_dir, config.PROJECT_FILE)
        await session.run_command(
            f'powershell -Command "Start-Process \'{project_file}\' -WindowStyle Maximized"'
        )

    except Exception as e:
        logger.warning(f"Failed to setup task {config.TASK_TAG}: {e}")


# ── Evaluation ──

@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the task: file checks + DRC analysis."""

    output_dir = task_cfg.metadata["remote_output_dir"]
    reference_dir = os.path.join(os.path.dirname(output_dir), "reference")
    score = 0.0

    pcb_path = os.path.join(output_dir, config.PCB_FILE)

    # ══════════════════════════════════════════════
    # Checkpoint 0: Gerber files exist (0.10)
    # ══════════════════════════════════════════════
    try:
        result = await session.run_command(
            f'powershell -Command "Get-ChildItem -Path \'{output_dir}\' -Recurse '
            f'-Include *.gbr -ErrorAction SilentlyContinue | Measure-Object | '
            f'Select-Object -ExpandProperty Count"'
        )
        gbr_count = int(_cmd_stdout(result).strip()) if _cmd_stdout(result).strip().isdigit() else 0
        if gbr_count > 0:
            score += 0.10
            logger.info(f"Checkpoint 0 PASSED: {gbr_count} Gerber files found")
        else:
            logger.info("Checkpoint 0 FAILED: No Gerber files found")
    except Exception as e:
        logger.info(f"Checkpoint 0 FAILED: {e}")

    # ══════════════════════════════════════════════
    # Checkpoint 1: Drill files exist (0.10)
    # ══════════════════════════════════════════════
    try:
        result = await session.run_command(
            f'powershell -Command "Get-ChildItem -Path \'{output_dir}\' -Recurse '
            f'-Include *.drl -ErrorAction SilentlyContinue | Measure-Object | '
            f'Select-Object -ExpandProperty Count"'
        )
        drl_count = int(_cmd_stdout(result).strip()) if _cmd_stdout(result).strip().isdigit() else 0
        if drl_count > 0:
            score += 0.10
            logger.info(f"Checkpoint 1 PASSED: {drl_count} drill files found")
        else:
            logger.info("Checkpoint 1 FAILED: No drill files found")
    except Exception as e:
        logger.info(f"Checkpoint 1 FAILED: {e}")

    # ══════════════════════════════════════════════
    # Checkpoint 2: DRC screenshot matches reference (VLM) (0.15)
    # ══════════════════════════════════════════════
    screenshot_bytes = None
    try:
        screenshot_path = os.path.join(output_dir, config.DRC_SCREENSHOT)
        screenshot_bytes = await session.read_bytes(screenshot_path)
        if not (screenshot_bytes and len(screenshot_bytes) > 1000):
            screenshot_bytes = None
    except Exception:
        pass

    if not screenshot_bytes:
        logger.info("Checkpoint 2 FAILED: drc_screenshot.png not found")
    else:
        try:
            reference_screenshot_path = os.path.join(reference_dir, config.REFERENCE_DRC_SCREENSHOT)
            reference_screenshot_bytes = await session.read_bytes(reference_screenshot_path)

            async with EvaluationContext(
                task_tag=config.TASK_TAG,
                mode="custom",
                output_dir=None,
                target_path=screenshot_path,
                reference_path=reference_screenshot_path,
            ) as ctx:
                drc_eval = await llm_vision_judge(
                    prompt="""The first image is the agent's screenshot. The second image is the reference screenshot.

                    Does the first image show KiCad's Design Rules Checker dialog with the Unconnected Items tab visible, similar to the reference image?

                    Answer with ONLY "YES" or "NO".""",
                    image_bytes=screenshot_bytes,
                    reference_image_bytes=reference_screenshot_bytes,
                    return_details=True,
                    max_tokens=10,
                    eval_context=ctx,
                    identifier="drc_screenshot_check",
                )
                vlm_passed = drc_eval.get("score", 0) == 1.0
                if vlm_passed:
                    score += 0.15
                    logger.info("Checkpoint 2 PASSED: DRC screenshot matches reference")
                else:
                    logger.info("Checkpoint 2 FAILED: DRC screenshot does not match reference")
        except Exception as e:
            logger.info(f"Checkpoint 2 FAILED: {e}")

    # Read PCB file once for CP3 and CP4
    pcb_bytes = None
    pcb_text = None
    try:
        pcb_bytes = await session.read_bytes(pcb_path)
        if pcb_bytes:
            pcb_text = pcb_bytes.decode('utf-8', errors='replace')
    except Exception:
        pass

    # ══════════════════════════════════════════════
    # Checkpoint 3: PCB contains traces (0.25)
    # ══════════════════════════════════════════════
    if pcb_text:
        segment_count = count_trace_segments(pcb_text)
        if segment_count >= config.MIN_TRACE_SEGMENTS:
            score += 0.25
            logger.info(f"Checkpoint 3 PASSED: {segment_count} trace segments found (min {config.MIN_TRACE_SEGMENTS})")
        else:
            logger.info(f"Checkpoint 3 FAILED: only {segment_count} trace segments found (need {config.MIN_TRACE_SEGMENTS})")
    else:
        logger.info("Checkpoint 3 FAILED: could not read .kicad_pcb file")

    # ══════════════════════════════════════════════
    # Checkpoint 4: Ground zone filled (0.10)
    # ══════════════════════════════════════════════
    if pcb_text:
        filled_count = count_filled_zone_polygons(pcb_text, net_name="GND")
        if filled_count >= 1:
            score += 0.10
            logger.info(f"Checkpoint 4 PASSED: {filled_count} filled GND zone polygons found")
        else:
            logger.info("Checkpoint 4 FAILED: No filled GND zone polygons found")
    else:
        logger.info("Checkpoint 4 FAILED: could not read .kicad_pcb file")

    # ══════════════════════════════════════════════
    # Checkpoint 5: Zero unconnected items (0.30)
    # ══════════════════════════════════════════════
    try:
        drc_report_path = os.path.join(output_dir, "drc_report.json")

        # Run kicad-cli DRC
        await session.run_command(
            f'powershell -Command "& \'{config.KICAD_CLI_PATH}\' pcb drc '
            f'--format json --output \'{drc_report_path}\' \'{pcb_path}\' 2>&1"'
        )

        # Read and parse the DRC report
        drc_bytes = await session.read_bytes(drc_report_path)
        if drc_bytes:
            drc_text = drc_bytes.decode('utf-8', errors='replace')
            drc_results = parse_drc_json(drc_text)

            if drc_results["parse_error"]:
                logger.info(f"Checkpoint 5 FAILED: {drc_results['parse_error']}")
            elif drc_results["unconnected_count"] == 0:
                score += 0.30
                logger.info("Checkpoint 5 PASSED: Zero unconnected items")
            else:
                logger.info(f"Checkpoint 5 FAILED: {drc_results['unconnected_count']} unconnected items")
        else:
            logger.info("Checkpoint 5 FAILED: could not read DRC report")

    except Exception as e:
        logger.info(f"Checkpoint 5 FAILED: {e}")

    logger.info(f"Final score: {score:.2f}")
    return [score]