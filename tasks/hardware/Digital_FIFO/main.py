"""Synchronous FIFO Design Task - Hardware Design Benchmark."""

import os
import logging
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from tasks.hardware.Digital_FIFO.eval import (
    parse_simulation_output,
)
from utils.evaluation import llm_vision_judge, EvaluationContext

logger = logging.getLogger(__name__)


def _cmd_stdout(result):
    """Extract stdout string from run_command result (may be dict or str)."""
    if isinstance(result, dict):
        return result.get("stdout", "")
    return result or ""


def _cmd_stderr(result):
    """Extract stderr string from run_command result (may be dict or str)."""
    if isinstance(result, dict):
        return result.get("stderr", "")
    return ""


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "Digital_FIFO"
    TASK_CATEGORY: str = "hardware"
    OS_TYPE: str = "windows"

    # FIFO parameters (for reference/metadata)
    FIFO_WIDTH: int = 8
    FIFO_DEPTH: int = 32

    # Vivado project settings
    TARGET_FPGA: str = "xc7a35tcpg236-1"

    # iverilog path on the VM
    IVERILOG_PATH: str = os.path.join(os.environ.get("IVERILOG_BASE", "C:\\iverilog\\bin"), "iverilog.exe")
    VVP_PATH: str = os.path.join(os.environ.get("IVERILOG_BASE", "C:\\iverilog\\bin"), "vvp.exe")   

    # Filenames
    FIFO_FILE: str = "fifo.v"
    FIFO_TB_FILE: str = "fifo_tb.sv"
    WAVEFORM_SCREENSHOT: str = "waveform_screenshot.png"
    VIVADO_PROJECT_DIR: str = "fifo_base"
    HIDDEN_TB_FILE: str = "fifo_tb_hidden.sv"
    REFERENCE_WAVEFORM: str = "reference_waveform.png"

    # Paths inside Vivado project where copied sources live
    FIFO_SRC_PATH: str = "fifo_base.srcs\\sources_1\\imports\\input\\fifo.v"
    FIFO_TB_SRC_PATH: str = "fifo_base.srcs\\sim_1\\imports\\input\\fifo_tb.sv"

    @property
    def task_dir(self):
        return f"{self.REMOTE_ROOT_DIR}\\{self.TASK_CATEGORY}\\{self.TASK_TAG}"

    @property
    def task_description(self):
        return f"""Design and implement a synchronous FIFO in Verilog, write a testbench, \
        and verify using Vivado.

        Design Specification:
        A synchronous FIFO queues data through a write interface and reads it out sequentially. \
        Both interfaces share the same clock. It uses a circular buffer with read/write pointers.

        Functional requirements:
            - Write: On rising clk edge, if wr_en=1 and not full, store din at write pointer and \
            advance it. Writes while full must be ignored (no corruption).
            - Read: On rising clk edge, if rd_en=1 and not empty, output data on dout and advance \
            read pointer. Reads while empty must be ignored. dout is registered (updates one cycle \
            after rd_en).
            - full=1 when FIFO cannot accept writes. empty=1 when FIFO has no valid entries.
            - Synchronous active-high reset: pointers to 0, empty asserts, full deasserts. Memory \
            need not be cleared.
            - Synthesizable Verilog only (no system tasks, no delays, no vendor primitives).

        Environment:
        - Vivado is open with project "fifo_base" loaded.
        - fifo.v is under Design Sources — it contains the module skeleton with the interface \
        and dummy assignments. Replace the dummy logic with your implementation.
        - fifo_tb.sv is under Simulation Sources → sim_1 → Non-module Files (it will move into \
        the hierarchy automatically once you write a module in it). Write your testbench here.
        - Target FPGA: {self.TARGET_FPGA} (Artix-7)
        - Full task should be completed within Vivado

        Flow:
        1. Open fifo.v from Design Sources and implement the FIFO (replace dummy assignments)
        2. Open fifo_tb.sv from Simulation Sources and write a testbench to confirm functionality
        3. Run behavioral simulation
        4. Once waveforms appear, save a screenshot using save_milestone_screenshot(path="{self.task_dir}\\output\\{self.WAVEFORM_SCREENSHOT}")
        5. Run synthesis

        Do not ask for confirmation. Execute each step directly.
        """

    def to_metadata(self):
        metadata = super().to_metadata()
        metadata.update({
            "fifo_width": self.FIFO_WIDTH,
            "fifo_depth": self.FIFO_DEPTH,
            "target_fpga": self.TARGET_FPGA,
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

        # Copy Vivado project (with embedded source files) from input to output
        src_project = os.path.join(input_dir, config.VIVADO_PROJECT_DIR)
        dst_project = os.path.join(output_dir, config.VIVADO_PROJECT_DIR)
        await session.run_command(
            f'powershell -Command "Copy-Item -Path \'{src_project}\' -Destination \'{dst_project}\' -Recurse"'
        )

        # Open Vivado with the copied project
        project_file = os.path.join(dst_project,
                                     f"{config.VIVADO_PROJECT_DIR}.xpr")
        await session.run_command(
            f'powershell -Command "Start-Process \'{project_file}\' -WindowStyle Maximized"'
        )

    except Exception as e:
        logger.warning(f"Failed to setup task {config.TASK_TAG}: {e}")


# ── Evaluation ──
 
@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the task: tool usage + functional correctness."""
 
    output_dir = task_cfg.metadata["remote_output_dir"]
    reference_dir = os.path.join(os.path.dirname(output_dir), "reference")
    project_dir = os.path.join(output_dir, config.VIVADO_PROJECT_DIR)
    score = 0.0
 
    # Agent's source files live inside the Vivado project's srcs directory
    fifo_path = os.path.join(project_dir, config.FIFO_SRC_PATH)
    tb_path = os.path.join(project_dir, config.FIFO_TB_SRC_PATH)
 
    # ══════════════════════════════════════════════
    # Checkpoint 0: fifo_tb.sv compiles with agent's fifo.v (0.10)
    # ══════════════════════════════════════════════
    try:
        agent_compile_dir = os.path.join(output_dir, "_agent_compile")
        await session.makedirs(agent_compile_dir)
 
        compile_result = await session.run_command(
            f'powershell -Command "& \'{config.IVERILOG_PATH}\' -g2012 '
            f'-o \'{agent_compile_dir}\\agent_test\' '
            f'\'{fifo_path}\' \'{tb_path}\' 2>&1"'
        )
 
        compile_check = await session.run_command(
            f'powershell -Command "Test-Path \'{agent_compile_dir}\\agent_test\'"'
        )
 
        if 'True' in _cmd_stdout(compile_check):
            score += 0.10
            logger.info("Checkpoint 0 PASSED: fifo_tb.sv compiles with fifo.v")
        else:
            logger.info(f"Checkpoint 0 FAILED: does not compile — {_cmd_stdout(compile_result)}")
 
        await session.remove_file(agent_compile_dir)
    except Exception as e:
        logger.info(f"Checkpoint 0 FAILED: {e}")
 
    # ══════════════════════════════════════════════
    # Checkpoint 1: Synthesis completed (0.10)
    # ══════════════════════════════════════════════
    try:
        result = await session.run_command(
            f'powershell -Command "Get-ChildItem -Path \'{project_dir}\' -Recurse '
            f'-Include *synth*.rpt,*synth*.log -ErrorAction SilentlyContinue '
            f'| Select-Object -First 1 -ExpandProperty FullName"'
        )
        if _cmd_stdout(result).strip():
            score += 0.10
            logger.info("Checkpoint 1 PASSED: Synthesis artifacts found")
        else:
            logger.info("Checkpoint 1 FAILED: No synthesis artifacts found")
    except Exception as e:
        logger.info(f"Checkpoint 1 FAILED: {e}")
 
    # ══════════════════════════════════════════════
    # Checkpoint 2: Waveform screenshot matches reference (VLM) (0.10)
    # ══════════════════════════════════════════════
    screenshot_bytes = None
    try:
        screenshot_path = os.path.join(output_dir, config.WAVEFORM_SCREENSHOT)
        screenshot_bytes = await session.read_bytes(screenshot_path)
        if not (screenshot_bytes and len(screenshot_bytes) > 1000):
            screenshot_bytes = None
    except Exception:
        pass
 
    if not screenshot_bytes:
        logger.info("Checkpoint 2 FAILED: waveform_screenshot.png not found")
    else:
        try:
            reference_screenshot_path = os.path.join(reference_dir, config.REFERENCE_WAVEFORM)
            reference_screenshot_bytes = await session.read_bytes(reference_screenshot_path)
 
            async with EvaluationContext(
                task_tag=config.TASK_TAG,
                mode="custom",
                output_dir=None,
                target_path=screenshot_path,
                reference_path=reference_screenshot_path,
            ) as ctx:
                waveform_eval = await llm_vision_judge(
                    prompt="""The first image is the agent's waveform screenshot. The second image is the reference waveform from a correct FIFO simulation.
                    
                    Does the first image show a Vivado waveform viewer displaying green signal traces similar to the reference waveform?
                    
                    Answer with ONLY "YES" or "NO".""",
                    image_bytes=screenshot_bytes,
                    reference_image_bytes=reference_screenshot_bytes,
                    return_details=True,
                    max_tokens=10,
                    eval_context=ctx,
                    identifier="waveform_check",
                )
                ctx.add_score(waveform_eval["score"] * 0.10)
                ctx.finalize(file=config.WAVEFORM_SCREENSHOT)
                score += ctx.total_score
 
                if ctx.total_score >= 0.05:
                    logger.info("Checkpoint 2 PASSED: Waveform screenshot matches reference")
                else:
                    logger.info("Checkpoint 2 FAILED: Waveform screenshot does not match reference")
        except Exception as e:
            logger.info(f"Checkpoint 2 FAILED: {e}")
 
    # ══════════════════════════════════════════════
    # Checkpoint 3: Compiles against hidden testbench (0.10)
    # ══════════════════════════════════════════════
    eval_dir = os.path.join(output_dir, "_eval_hidden")
    try:
        await session.makedirs(eval_dir)
 
        hidden_tb = os.path.join(reference_dir, config.HIDDEN_TB_FILE)
 
        await session.run_command(
            f'powershell -Command "Copy-Item \'{fifo_path}\' \'{eval_dir}\\fifo.v\'"'
        )
        await session.run_command(
            f'powershell -Command "Copy-Item \'{hidden_tb}\' \'{eval_dir}\\fifo_tb.sv\'"'
        )
 
        compile_result = await session.run_command(
            f'powershell -Command "& \'{config.IVERILOG_PATH}\' -g2012 -DIVERILOG '
            f'-o \'{eval_dir}\\fifo_test\' '
            f'\'{eval_dir}\\fifo.v\' \'{eval_dir}\\fifo_tb.sv\' 2>&1"'
        )
 
        compile_check = await session.run_command(
            f'powershell -Command "Test-Path \'{eval_dir}\\fifo_test\'"'
        )
 
        compiled = 'True' in _cmd_stdout(compile_check)
        if compiled:
            score += 0.10
            logger.info("Checkpoint 3 PASSED: Compiles against hidden testbench")
        else:
            logger.info(f"Checkpoint 3 FAILED: Compilation errors — {_cmd_stdout(compile_result)}")
            logger.info("Checkpoints 4-5 FAILED: Cannot run simulation without compilation")
            logger.info(f"Final score: {score:.2f}")
            return [score]
 
        # Run simulation
        sim_result = await session.run_command(
            f'powershell -Command "& \'{config.VVP_PATH}\' \'{eval_dir}\\fifo_test\' 2>&1"'
        )
 
        sim_output = _cmd_stdout(sim_result)
        sim_results = parse_simulation_output(sim_output)
 
        for err in sim_results["errors"]:
            logger.info(f"  Sim error: {err}")
 
        # ══════════════════════════════════════════════
        # Checkpoint 4: Basic tests pass (0.30)
        # ══════════════════════════════════════════════
        if sim_results["basic_passed"]:
            score += 0.30
            logger.info("Checkpoint 4 PASSED: All basic tests passed")
        else:
            logger.info("Checkpoint 4 FAILED: Basic tests did not pass")
 
        # ══════════════════════════════════════════════
        # Checkpoint 5: Hard tests pass (0.30)
        # ══════════════════════════════════════════════
        if sim_results["hard_passed"]:
            score += 0.30
            logger.info("Checkpoint 5 PASSED: All hard tests passed")
        else:
            logger.info("Checkpoint 5 FAILED: Hard tests did not pass")
 
    except Exception as e:
        logger.info(f"L3 evaluation failed: {e}")
    finally:
        try:
            await session.remove_file(eval_dir)
        except Exception:
            pass
 
    logger.info(f"Final score: {score:.2f}")
    return [score]