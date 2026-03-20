"""IC Layout Design Task - Hardware Design Benchmark."""

import os
import logging
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from tasks.hardware.IC_Layout.eval import (
    check_required_layers,
    check_transistor_gates,
    check_metal_and_contacts,
    check_net_labels,
    parse_drc_report,
    parse_lvs_report,
)
from utils.evaluation import llm_vision_judge, EvaluationContext

logger = logging.getLogger(__name__)

@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "IC_Layout"
    TASK_CATEGORY: str = "hardware"
    OS_TYPE: str = "windows"

    # KLayout path on the VM
    KLAYOUT_PATH: str = os.environ.get(
        "KLAYOUT_PATH",
        "C:\\Users\\User\\AppData\\Roaming\\KLayout\\klayout_app.exe"
    )

    # DRC/LVS scripts pre-installed on VM
    DRC_SCRIPT: str = os.environ.get(
        "SKY130_DRC_SCRIPT",
        "C:\\Users\\User\\KLayout\\drc\\sky130_drc.lydrc"
    )
    LVS_SCRIPT: str = os.environ.get(
        "SKY130_LVS_SCRIPT",
        "C:\\Users\\User\\KLayout\\lvs\\sky130_lvs.lylvs"
    )

    # Filenames
    GDS_FILE: str = "inverter.gds"
    CDL_FILE: str = "inverter.cdl"
    DRC_SCREENSHOT: str = "drc_screenshot.png"
    LVS_SCREENSHOT: str = "lvs_screenshot.png"
    REFERENCE_DRC_SCREENSHOT: str = "reference_drc_screenshot.png"
    REFERENCE_LVS_SCREENSHOT: str = "reference_lvs_screenshot.png"

    @property
    def task_dir(self):
        return f"{self.REMOTE_ROOT_DIR}\\{self.TASK_CATEGORY}\\{self.TASK_TAG}"

    @property
    def task_description(self):
        return f"""Design and lay out a CMOS inverter cell in KLayout using the SkyWater Sky130 PDK. \
        The layout must pass DRC and LVS verification.
 
        Existing File Structure:
        {self.task_dir}\\
        └── output\\
            ├── {self.GDS_FILE}               # Blank Sky130 layout (open in KLayout)
            └── {self.CDL_FILE}               # Reference netlist for LVS
 
        Design Requirements:
        - Circuit: CMOS inverter with 1 NMOS and 1 PMOS transistor
        - Process: SkyWater Sky130 130nm
        - Ports: VDD, VSS, IN, OUT (must be labeled for LVS)
        - The layout must be DRC clean and LVS clean against the provided reference netlist
 
        Environment:
        - KLayout is open in editor mode with {self.GDS_FILE} loaded, showing Sky130 technology layers
        - Sky130 PDK is installed via the Efabless_sky130 package
        - DRC script is available at Tools → DRC → sky130_drc.lydrc
        - LVS script is available at Tools → LVS → sky130_lvs.lylvs
        - The LVS script automatically finds {self.CDL_FILE} in the same directory as the GDS file
        - After running DRC, save a screenshot using \
        save_milestone_screenshot(path="{self.task_dir}\\output\\{self.DRC_SCREENSHOT}")
        - After running LVS, save a screenshot using \
        save_milestone_screenshot(path="{self.task_dir}\\output\\{self.LVS_SCREENSHOT}")
 
        Do not ask for confirmation. Execute each step directly.
        """

    def to_metadata(self):
        metadata = super().to_metadata()
        metadata.update({
            "gds_file": self.GDS_FILE,
            "cdl_file": self.CDL_FILE,
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

        # Copy GDS and CDL from input to output
        for filename in [config.GDS_FILE, config.CDL_FILE]:
            src = os.path.join(input_dir, filename)
            dst = os.path.join(output_dir, filename)
            await session.run_command(
                f'powershell -Command "Copy-Item \'{src}\' \'{dst}\'"'
            )

        # Open GDS in KLayout editor mode
        gds_path = os.path.join(output_dir, config.GDS_FILE)
        await session.run_command(
            f'powershell -Command "Start-Process \'{config.KLAYOUT_PATH}\' '
            f'-ArgumentList \'-e\',\'{gds_path}\'"'
        )

    except Exception as e:
        logger.warning(f"Failed to setup task {config.TASK_TAG}: {e}")


# ── Evaluation ──

@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the task: layout checks + DRC/LVS screenshots + DRC/LVS clean."""

    output_dir = task_cfg.metadata["remote_output_dir"]
    reference_dir = os.path.join(os.path.dirname(output_dir), "reference")
    score = 0.0

    gds_path = os.path.join(output_dir, config.GDS_FILE)
    cdl_path = os.path.join(output_dir, config.CDL_FILE)

    # Read GDS bytes from VM for local analysis (checkpoints 0-3)
    gds_bytes = None
    try:
        gds_bytes = await session.read_bytes(gds_path)
        if not (gds_bytes and len(gds_bytes) > 100):
            gds_bytes = None
    except Exception:
        pass

    if not gds_bytes:
        logger.info("Could not read GDS file — all checkpoints will fail")
        logger.info(f"Final score: {score:.2f}")
        return [score]

    # ══════════════════════════════════════════════
    # Checkpoint 0: Required Layers (0.10)
    # ══════════════════════════════════════════════
    try:
        layer_results = check_required_layers(gds_bytes)
        if layer_results["all_pass"]:
            score += 0.10
            logger.info("Checkpoint 0 PASSED: All required layers populated")
        else:
            missing = [k for k, v in layer_results["layers_found"].items() if not v]
            logger.info(f"Checkpoint 0 FAILED: Missing layers — {missing}")
    except Exception as e:
        logger.info(f"Checkpoint 0 FAILED: {e}")

    # ══════════════════════════════════════════════
    # Checkpoint 1: Transistor Gates (0.10)
    # ══════════════════════════════════════════════
    try:
        gate_results = check_transistor_gates(gds_bytes)
        if gate_results["pass"]:
            score += 0.10
            logger.info(f"Checkpoint 1 PASSED: {gate_results['gate_count']} gate regions found")
        else:
            logger.info(f"Checkpoint 1 FAILED: {gate_results['gate_count']} gate regions (need >= 2)")
    except Exception as e:
        logger.info(f"Checkpoint 1 FAILED: {e}")

    # ══════════════════════════════════════════════
    # Checkpoint 2: Metal and Contacts (0.10)
    # ══════════════════════════════════════════════
    try:
        metal_results = check_metal_and_contacts(gds_bytes)
        if metal_results["pass"]:
            score += 0.10
            logger.info(f"Checkpoint 2 PASSED: {metal_results['contact_count']} contacts, "
                        f"{metal_results['metal_count']} metal shapes")
        else:
            logger.info(f"Checkpoint 2 FAILED: {metal_results['contact_count']} contacts "
                        f"(need >= 4), {metal_results['metal_count']} metals (need >= 3)")
    except Exception as e:
        logger.info(f"Checkpoint 2 FAILED: {e}")

    # ══════════════════════════════════════════════
    # Checkpoint 3: Net Labels (0.10)
    # ══════════════════════════════════════════════
    try:
        label_results = check_net_labels(gds_bytes)
        if label_results["all_pass"]:
            score += 0.10
            logger.info("Checkpoint 3 PASSED: All net labels found (IN, OUT, VDD, VSS)")
        else:
            missing = [k for k, v in label_results["labels_found"].items() if not v]
            logger.info(f"Checkpoint 3 FAILED: Missing labels — {missing}")
    except Exception as e:
        logger.info(f"Checkpoint 3 FAILED: {e}")

    # ══════════════════════════════════════════════
    # Checkpoint 4: Agent Ran DRC — VLM (0.10)
    # ══════════════════════════════════════════════
    drc_screenshot_bytes = None
    try:
        drc_screenshot_path = os.path.join(output_dir, config.DRC_SCREENSHOT)
        drc_screenshot_bytes = await session.read_bytes(drc_screenshot_path)
        if not (drc_screenshot_bytes and len(drc_screenshot_bytes) > 1000):
            drc_screenshot_bytes = None
    except Exception:
        pass

    if not drc_screenshot_bytes:
        logger.info("Checkpoint 4 FAILED: drc_screenshot.png not found")
    else:
        try:
            reference_drc_path = os.path.join(reference_dir, config.REFERENCE_DRC_SCREENSHOT)
            reference_drc_bytes = await session.read_bytes(reference_drc_path)

            async with EvaluationContext(
                task_tag=config.TASK_TAG,
                mode="custom",
                output_dir=None,
                target_path=drc_screenshot_path,
                reference_path=reference_drc_path,
            ) as ctx:
                drc_eval = await llm_vision_judge(
                    prompt="""The first image is the agent's screenshot. The second image is a reference screenshot.

                    Does the first image show KLayout's Marker Database Browser displaying DRC results 
                    for a Sky130 layout, similar to the reference image?

                    Answer with ONLY "YES" or "NO".""",
                    image_bytes=drc_screenshot_bytes,
                    reference_image_bytes=reference_drc_bytes,
                    return_details=True,
                    max_tokens=10,
                    eval_context=ctx,
                    identifier="drc_screenshot_check",
                )
                vlm_passed = drc_eval.get("score", 0) == 1.0
                if vlm_passed:
                    score += 0.10
                    logger.info("Checkpoint 4 PASSED: DRC screenshot shows results")
                else:
                    logger.info("Checkpoint 4 FAILED: DRC screenshot does not show valid results")
        except Exception as e:
            logger.info(f"Checkpoint 4 FAILED: {e}")

    # ══════════════════════════════════════════════
    # Checkpoint 5: Agent Ran LVS — VLM (0.10)
    # ══════════════════════════════════════════════
    lvs_screenshot_bytes = None
    try:
        lvs_screenshot_path = os.path.join(output_dir, config.LVS_SCREENSHOT)
        lvs_screenshot_bytes = await session.read_bytes(lvs_screenshot_path)
        if not (lvs_screenshot_bytes and len(lvs_screenshot_bytes) > 1000):
            lvs_screenshot_bytes = None
    except Exception:
        pass

    if not lvs_screenshot_bytes:
        logger.info("Checkpoint 5 FAILED: lvs_screenshot.png not found")
    else:
        try:
            reference_lvs_path = os.path.join(reference_dir, config.REFERENCE_LVS_SCREENSHOT)
            reference_lvs_bytes = await session.read_bytes(reference_lvs_path)

            async with EvaluationContext(
                task_tag=config.TASK_TAG,
                mode="custom",
                output_dir=None,
                target_path=lvs_screenshot_path,
                reference_path=reference_lvs_path,
            ) as ctx:
                lvs_eval = await llm_vision_judge(
                    prompt="""The first image is the agent's screenshot. The second image is a reference screenshot.

                    Does the first image show KLayout's Netlist Database Browser displaying LVS 
                    cross-reference results for a Sky130 layout, similar to the reference image?

                    Answer with ONLY "YES" or "NO".""",
                    image_bytes=lvs_screenshot_bytes,
                    reference_image_bytes=reference_lvs_bytes,
                    return_details=True,
                    max_tokens=10,
                    eval_context=ctx,
                    identifier="lvs_screenshot_check",
                )
                vlm_passed = lvs_eval.get("score", 0) == 1.0
                if vlm_passed:
                    score += 0.10
                    logger.info("Checkpoint 5 PASSED: LVS screenshot shows results")
                else:
                    logger.info("Checkpoint 5 FAILED: LVS screenshot does not show valid results")
        except Exception as e:
            logger.info(f"Checkpoint 5 FAILED: {e}")

    # ══════════════════════════════════════════════
    # Checkpoint 6: DRC Clean (0.20)
    # Run on VM via KLayout batch mode
    # ══════════════════════════════════════════════
    try:
        eval_dir = os.path.join(output_dir, "_eval")
        await session.makedirs(eval_dir)

        drc_report_path = os.path.join(eval_dir, "drc_report.txt")

        await session.run_command(
            f'powershell -Command "& \'{config.KLAYOUT_PATH}\' -b '
            f'-r \'{config.DRC_SCRIPT}\' '
            f'-rd input=\'{gds_path}\' '
            f'-rd report=\'{drc_report_path}\' '
            f'-rd feol=true -rd beol=true 2>&1"'
        )

        drc_bytes = await session.read_bytes(drc_report_path)
        if drc_bytes:
            drc_text = drc_bytes.decode('utf-8', errors='replace')
            drc_results = parse_drc_report(drc_text)

            if drc_results["parse_error"]:
                logger.info(f"Checkpoint 6 FAILED: {drc_results['parse_error']}")
            elif not drc_results["report_valid"]:
                logger.info("Checkpoint 6 FAILED: DRC report invalid or empty")
            elif drc_results["violation_count"] == 0:
                score += 0.20
                logger.info("Checkpoint 6 PASSED: DRC clean — zero violations")
            else:
                logger.info(f"Checkpoint 6 FAILED: {drc_results['violation_count']} DRC violations")
        else:
            logger.info("Checkpoint 6 FAILED: DRC report not generated")

    except Exception as e:
        logger.info(f"Checkpoint 6 FAILED: {e}")

    # ══════════════════════════════════════════════
    # Checkpoint 7: LVS Clean (0.20)
    # Run on VM via KLayout batch mode
    # ══════════════════════════════════════════════
    try:
        lvs_report_path = os.path.join(eval_dir, "lvs_report.lvsdb")

        await session.run_command(
            f'powershell -Command "& \'{config.KLAYOUT_PATH}\' -b '
            f'-r \'{config.LVS_SCRIPT}\' '
            f'-rd input=\'{gds_path}\' '
            f'-rd schematic=\'{cdl_path}\' '
            f'-rd report=\'{lvs_report_path}\' '
            f'-rd scale=true 2>&1"'
        )

        lvs_bytes = await session.read_bytes(lvs_report_path)
        if lvs_bytes:
            lvs_text = lvs_bytes.decode('utf-8', errors='replace')
            lvs_results = parse_lvs_report(lvs_text)

            if lvs_results["parse_error"]:
                logger.info(f"Checkpoint 7 FAILED: {lvs_results['parse_error']}")
            elif not lvs_results["report_valid"]:
                logger.info("Checkpoint 7 FAILED: LVS report invalid or empty")
            elif lvs_results["all_matched"]:
                score += 0.20
                logger.info(f"Checkpoint 7 PASSED: LVS clean — "
                            f"{lvs_results['net_matches']} nets, "
                            f"{lvs_results['device_matches']} devices matched")
            else:
                logger.info(f"Checkpoint 7 FAILED: LVS mismatch — "
                            f"net matches={lvs_results['net_matches']}, "
                            f"net mismatches={lvs_results['net_mismatches']}, "
                            f"device matches={lvs_results['device_matches']}, "
                            f"device mismatches={lvs_results['device_mismatches']}")
        else:
            logger.info("Checkpoint 7 FAILED: LVS report not generated")

    except Exception as e:
        logger.info(f"Checkpoint 7 FAILED: {e}")

    # Cleanup
    try:
        await session.remove_file(eval_dir)
    except Exception:
        pass

    logger.info(f"Final score: {score:.2f}")
    return [score]