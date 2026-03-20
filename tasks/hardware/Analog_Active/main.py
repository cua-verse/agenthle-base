"""Active Analog Circuit Design Task - Hardware Design Benchmark."""

import os
import logging
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from tasks.hardware.Analog_Active.eval import (
    check_rload_value,
    check_tran_directive,
    analyze_raw_output,
)
from utils.evaluation import llm_vision_judge, EvaluationContext

logger = logging.getLogger(__name__)


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "Analog_Active"
    TASK_CATEGORY: str = "hardware"
    OS_TYPE: str = "windows"

    # Design spec
    INPUT_VOLTAGE: float = 5.0
    OUTPUT_V_TARGET: float = 1.5
    OUTPUT_V_TOL: float = 0.05
    RIPPLE_MAX_MV: float = 30.0
    LOAD_I_TARGET: float = 10.0
    LOAD_I_TOL: float = 0.10

    # Component thresholds
    FEEDBACK_R_TARGET: float = 6650.0
    FEEDBACK_R_TOL: float = 0.1       
    LOAD_R_TARGET: float = 0.15
    LOAD_R_TOL: float = 0.01            # essentially exact

    # Measurement window
    MEAS_START_MS: float = 0.7
    MEAS_END_MS: float = 1.0

    # Output filenames
    CIRCUIT_FILE: str = "circuit.asc"
    RAW_FILE: str = "circuit.raw"
    SCHEMATIC_SCREENSHOT: str = "schematic_screenshot.png"

    @property
    def task_dir(self):
        return f"{self.REMOTE_ROOT_DIR}\\{self.TASK_CATEGORY}\\{self.TASK_TAG}"

    @property
    def task_description(self):
        return f"""You are given an LTspice schematic with the LTM4648 µModule DC/DC buck regulator IC already \
        placed on the canvas. Your task is to complete the circuit design by adding all required external components, \
        wiring them to the correct IC pins, and running a transient simulation to verify the output.

        Existing File Structure:
        {self.task_dir}\\
        ├── input\\
        │   └── design_spec.txt               # Design specification
        │   └── ltm4648_datasheet.pdf         # Datasheet for LTM4648 IC
        └── output\\
            └── circuit.asc                    # LTspice schematic with LTM4648 IC (open in LTspice)

        Design Specification:
        - IC: LTM4648 µModule DC/DC Buck Regulator
        - Input Voltage: {self.INPUT_VOLTAGE}V
        - Output Voltage: {self.OUTPUT_V_TARGET}V
        - Output Current: {self.LOAD_I_TARGET}A
        - Output Ripple: < {self.RIPPLE_MAX_MV}mV peak-to-peak
        - Startup Settling Time: Output must reach {self.OUTPUT_V_TARGET}V within ~0.6ms
        - Simulation: Transient analysis, 1ms duration, with startup.

        Component Value Formats (use these exact formats in LTspice):
        - Voltage source: Set value to "{self.INPUT_VOLTAGE}" (plain number, no suffix)
        - Resistors: Use plain numeric values (e.g., "5700" not "5.7k", "0.19" not "190m")

        Environment:
        - LTspice is open with circuit.asc loaded, showing the LTM4648 µModule IC on the canvas
        - The output node is pre-labeled "out"

        Once the circuit is complete:
        1. Save the schematic (Ctrl+S) to ensure circuit.asc is updated
        2. Run the transient simulation to verify output behavior
        3. Save a screenshot of the completed schematic using save_milestone_screenshot(path="{self.task_dir}\\output\\{self.SCHEMATIC_SCREENSHOT}")

        Do not ask for confirmation. Execute each step directly.
        """

    def to_metadata(self):
        metadata = super().to_metadata()
        metadata.update({
            "input_voltage": self.INPUT_VOLTAGE,
            "output_v_target": self.OUTPUT_V_TARGET,
            "output_v_tol": self.OUTPUT_V_TOL,
            "ripple_max_mv": self.RIPPLE_MAX_MV,
            "load_i_target": self.LOAD_I_TARGET,
            "load_i_tol": self.LOAD_I_TOL,
            "feedback_r_target": self.FEEDBACK_R_TARGET,
            "feedback_r_tol": self.FEEDBACK_R_TOL,
            "load_r_target": self.LOAD_R_TARGET,
            "load_r_tol": self.LOAD_R_TOL,
            "meas_start_ms": self.MEAS_START_MS,
            "meas_end_ms": self.MEAS_END_MS,
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

        # Copy template .asc to output directory
        template_src = os.path.join(input_dir, "buck_template.asc")
        circuit_dst = os.path.join(output_dir, config.CIRCUIT_FILE)
        await session.run_command(
            f'powershell -Command "Copy-Item \'{template_src}\' \'{circuit_dst}\'"'
        )

        # Open circuit.asc in LTspice
        await session.run_command(
            f'powershell -Command "Start-Process \'{circuit_dst}\' -WindowStyle Maximized"'
        )

    except Exception as e:
        logger.warning(f"Failed to setup task {config.TASK_TAG}: {e}")


# ── Evaluation ──

@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the task: L1 component checks + VLM, L2 simulation output."""

    output_dir = task_cfg.metadata["remote_output_dir"]
    score = 0.0

    # ══════════════════════════════════════════════
    # L1: Schematic Component Checks (weight: 0.40)
    # ══════════════════════════════════════════════

    # Read ASC file for deterministic checks (Rload value, .tran directive)
    asc_bytes = None
    try:
        asc_path = os.path.join(output_dir, config.CIRCUIT_FILE)
        asc_bytes = await session.read_bytes(asc_path)
    except Exception:
        pass

    # Read screenshot for VLM checks
    screenshot_bytes = None
    try:
        screenshot_path = os.path.join(output_dir, config.SCHEMATIC_SCREENSHOT)
        screenshot_bytes = await session.read_bytes(screenshot_path)
        if not (screenshot_bytes and len(screenshot_bytes) > 1000):
            screenshot_bytes = None
    except Exception:
        pass

    # ── Checkpoints 0-1: Voltage Source + Feedback Resistor via VLM (0.20) ──
    if not screenshot_bytes:
        logger.info("Checkpoints 0-1 FAILED: schematic_screenshot.png not found")
    else:
        try:
            async with EvaluationContext(
                task_tag=config.TASK_TAG,
                mode="custom",
                output_dir=None,
                target_path=screenshot_path,
                reference_path=None,
            ) as ctx:
                
                fb_min_k = config.FEEDBACK_R_TARGET * (1 - config.FEEDBACK_R_TOL) / 1000
                fb_max_k = config.FEEDBACK_R_TARGET * (1 + config.FEEDBACK_R_TOL) / 1000

                component_eval = await llm_vision_judge(
                    prompt=f"""You are evaluating an LTspice circuit schematic for an LTM4648 buck converter design.

                    Examine the schematic and answer each question with T (true) or F (false).

                    1. Does the schematic contain a DC voltage source with a value of exactly {config.INPUT_VOLTAGE}V connected as the input supply?
                    2. Does the schematic contain a feedback resistor with a value between {fb_min_k:.1f}kΩ and {fb_max_k:.1f}kΩ connected to the feedback pin of the IC?

                    Respond with ONLY two comma-separated values, e.g.: T,F""",

                    image_bytes=screenshot_bytes,
                    return_details=True,
                    max_tokens=20,
                    eval_context=ctx,
                    identifier="component_values",
                )

                # Parse VLM response: expect "T,F" or similar
                vlm_response = component_eval.get("vlm_response", "").strip().upper()
                checks = [c.strip() == "T" for c in vlm_response.split(",")]

                # Pad to length 2 if VLM returned fewer tokens
                while len(checks) < 2:
                    checks.append(False)

                check_names = [
                    ("Checkpoint 0", "Voltage source 5V", 0.10),
                    (f"Checkpoint 1", "Feedback resistor between {fb_min_k:.1f}kΩ and {fb_max_k:.1f}kΩ", 0.10),
                ]
                for i, (cp_name, desc, weight) in enumerate(check_names):
                    if checks[i]:
                        score += weight
                        logger.info(f"{cp_name} PASSED: {desc}")
                    else:
                        logger.info(f"{cp_name} FAILED: {desc}")

                ctx.add_score(sum(weight for i, (_, _, weight) in enumerate(check_names) if checks[i]))
                ctx.finalize(file=config.SCHEMATIC_SCREENSHOT)

        except Exception as e:
            logger.info(f"Checkpoints 0-1 FAILED: {e}")

    # ── Checkpoint 2: Load Resistor via ASC parsing (0.10) ──
    # Rload is pre-placed in the template — check its value deterministically
    if asc_bytes:
        if check_rload_value(asc_bytes.decode('latin-1'), config):
            score += 0.10
            logger.info("Checkpoint 2 PASSED: Rload value ~0.15Ω")
        else:
            logger.info("Checkpoint 2 FAILED: Rload value not ~0.15Ω")
    else:
        logger.info("Checkpoint 2 FAILED: circuit.asc not found")

    # ── Checkpoint 3: Capacitor Placement VLM (0.10) ──
    if not screenshot_bytes:
        logger.info("Checkpoint 3 FAILED: schematic_screenshot.png not found")
    else:
        try:
            async with EvaluationContext(
                task_tag=config.TASK_TAG,
                mode="custom",
                output_dir=None,
                target_path=screenshot_path,
                reference_path=None,
            ) as ctx:
                cap_eval = await llm_vision_judge(
                    prompt="""You are evaluating an LTspice circuit schematic for a buck converter design.

                    Does this schematic show capacitors in all three of these locations:
                    (1) on the input side connected to the voltage source,
                    (2) on the output side connected to the load, and
                    (3) connected to the Track/SS pin of the IC?

                    Answer with ONLY "YES" or "NO".""",
                    image_bytes=screenshot_bytes,
                    return_details=True,
                    max_tokens=10,
                    eval_context=ctx,
                    identifier="cap_placement",
                )
                ctx.add_score(cap_eval["score"] * 0.10)
                ctx.finalize(file=config.SCHEMATIC_SCREENSHOT)
                score += ctx.total_score

                if ctx.total_score >= 0.05:
                    logger.info(f"Checkpoint 3 PASSED: Capacitor placement score={ctx.total_score:.2f}")
                else:
                    logger.info(f"Checkpoint 3 FAILED: Capacitor placement score={ctx.total_score:.2f}")
        except Exception as e:
            logger.info(f"Checkpoint 3 FAILED: {e}")

    # ══════════════════════════════════════════════
    # L2: Simulation Output (weight: 0.60)
    # ══════════════════════════════════════════════

    # ── Checkpoint 4: Transient Directive + Simulation Ran (0.10) ──
    # Agent must have both configured the correct .tran directive AND run the sim
    tran_ok = False
    if asc_bytes:
        tran_ok = check_tran_directive(asc_bytes.decode('latin-1'), config)

    raw_bytes = None
    try:
        raw_path = os.path.join(output_dir, config.RAW_FILE)
        raw_bytes = await session.read_bytes(raw_path)
        if not (raw_bytes and len(raw_bytes) > 100):
            raw_bytes = None
    except Exception:
        raw_bytes = None

    if tran_ok and raw_bytes:
        score += 0.10
        logger.info(f"Checkpoint 4 PASSED: .tran directive found and circuit.raw exists ({len(raw_bytes)} bytes)")
    else:
        logger.info(f"Checkpoint 4 FAILED: .tran directive={'found' if tran_ok else 'missing'}, "
                     f"circuit.raw={'found' if raw_bytes else 'missing'}")

    if not raw_bytes:
        logger.info(f"Final score: {score:.2f}")
        return [score]

    # Analyze the .raw file for checkpoints 5-7
    raw_results = analyze_raw_output(raw_bytes, config)

    # ── Checkpoint 5: Output Voltage (0.20) ──
    # This is the gate for checkpoints 6 and 7: ripple and load current
    # are only meaningful at the correct operating point.
    v = raw_results["output_voltage"]["value"]
    voltage_ok = v is not None and raw_results["output_voltage"]["pass"]

    if voltage_ok:
        score += 0.20
        logger.info(f"Checkpoint 5 PASSED: Output voltage {v:.4f}V")

        # ── Checkpoint 6: Output Ripple (0.15) ──
        # Only evaluated when output voltage is correct — any stable
        # (but wrong) operating point will naturally have low ripple.
        r = raw_results["output_ripple"]["value_mv"]
        if r is not None and raw_results["output_ripple"]["pass"]:
            score += 0.15
            logger.info(f"Checkpoint 6 PASSED: Output ripple {r:.2f}mV pk-pk")
        else:
            logger.info(f"Checkpoint 6 FAILED: Output ripple {r}mV pk-pk")

        # ── Checkpoint 7: Load Current (0.15) ──
        # Only evaluated when output voltage is correct — current through
        # Rload is V/R, so it's only a valid check at the target voltage.
        i = raw_results["load_current"]["value"]
        if i is not None and raw_results["load_current"]["pass"]:
            score += 0.15
            logger.info(f"Checkpoint 7 PASSED: Load current {i:.2f}A")
        else:
            logger.info(f"Checkpoint 7 FAILED: Load current {i}A")
    else:
        logger.info(f"Checkpoint 5 FAILED: Output voltage {v}V "
                     "(checkpoints 6-7 skipped — require correct output voltage)")

    logger.info(f"Final score: {score:.2f}")
    return [score]