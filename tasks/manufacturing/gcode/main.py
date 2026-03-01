"""GCode CAM Task -- PowerMill Toolpath Design (15 workpiece variants).

The agent is given a blank PowerMill project (pre-configured tools, zero toolpaths)
and must design toolpaths to machine a workpiece, achieving a simulated stock model
that closely matches an expert reference.

Variants: 15 workpieces with identical evaluation logic but different geometry.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# All 15 workpiece variants
# Each tuple: (task_tag, pm_project_folder_name)
# ---------------------------------------------------------------------------
VARIANTS = [
    ("125162_319", "125162-319-NCFM-T"),
    ("A125117_301", "A125117-301-NCSM-B"),
    ("A125138_301", "A125138-301-NCFM-T"),
    ("A125138_302", "A125138-302-NCSM-B"),
    ("MDBZDHZJ25_SKC_1_NCSM_T", "MDBZDHZJ25_SKC-1_NCSM_T"),
    ("MR250692C00_M2", "MR250692C00-M2-NCFM-T"),
    ("MR250696C00_F1", "MR250696C00-F1-NCSM-B"),
    ("MR250696C00_S5", "MR250696C00-S5-NCSM-T"),
    ("MR250697C00_M1", "MR250697C00-M1-NCFM-B"),
    ("MR250697C00_S1", "MR250697C00-S1-NCSM-B"),
    ("MR250697C00_S2", "MR250697C00-S2-NCFM-T"),
    ("MR250698C00_F3", "MR250698C00-F3-NCSM-B"),
    ("MR250698C00_P6", "MR250698C00-P6-NCSM-B"),
    ("MR250698C00_U005", "MR250698C00-U005-NCFM-L"),
    ("T29153_050", "T29153-050-NCRM-F"),
]


#################################################################
############################# Config ############################
#################################################################


@dataclass
class GCodeTaskConfig(GeneralTaskConfig):
    """Configuration for a single GCode CAM workpiece task."""

    TASK_CATEGORY: str = r"manufacturing\gcode"
    TASK_TAG: str = ""
    PM_PROJECT_NAME: str = ""

    @property
    def input_dir(self) -> str:
        return rf"{self.task_dir}\input"

    @property
    def input_pm_project(self) -> str:
        """The blank PM project in input/ (source, read-only)."""
        return rf"{self.input_dir}\{self.PM_PROJECT_NAME}"

    @property
    def output_pm_project(self) -> str:
        """The PM project copied to output/ (agent works here)."""
        return rf"{self.remote_output_dir}\{self.PM_PROJECT_NAME}"

    @property
    def reference_stl(self) -> str:
        return rf"{self.reference_dir}\reference_sim.stl"

    @property
    def agent_sim_stl(self) -> str:
        return rf"{self.remote_output_dir}\agent_sim.stl"

    @property
    def task_description(self) -> str:
        return f"""\
You are a CAM (Computer-Aided Manufacturing) engineer using Autodesk PowerMill.

## Your Task
Design toolpaths to machine workpiece **{self.TASK_TAG}** using the provided blank PowerMill project.

## Input Files
- **PowerMill project** (blank, with pre-configured tools, zero toolpaths):
  `{self.output_pm_project}`
  (This project has been copied to your output folder so you can modify it freely.)
- **Ideal workpiece geometry** (.prt format): `{self.input_dir}\\{self.TASK_TAG}.prt`
- **Reference image**: `{self.input_dir}\\{self.TASK_TAG}.jpg`

## What You Must Do
1. Open PowerMill (shortcut in `{self.software_dir}`) and load the project at:
   `{self.output_pm_project}`
2. Study the ideal workpiece geometry (.prt file) to understand the target shape
3. Design toolpaths that will machine the workpiece from raw stock:
   - Use roughing toolpaths to remove bulk material
   - Use finishing toolpaths for surfaces requiring higher precision
   - Use the pre-configured tools already in the project (do NOT create new tools)
4. **Critical**: Ensure each toolpath has NO collisions and NO gouging
5. Run a stock model simulation to confirm the final result
6. **Save** the PowerMill project (Ctrl+S)

## Color Coding on the Workpiece
The .prt file has faces colored by precision requirement:
- Tight tolerance faces (e.g., VDI12/15): require finer finish toolpaths
- Loose tolerance faces (e.g., spray/texture faces): standard finish is acceptable

## Evaluation
Your toolpaths will be automatically evaluated by:
1. Gate check: any collision or gouge → score 0
2. Geometric accuracy: simulated stock model compared against expert reference

## Important
- Work ONLY within the project at `{self.output_pm_project}`
- Do NOT move or rename the project folder
- SAVE your project when finished
"""

    def to_metadata(self) -> dict:
        metadata = super().to_metadata()
        metadata.update(
            {
                "pm_project_name": self.PM_PROJECT_NAME,
                "input_pm_project": self.input_pm_project,
                "output_pm_project": self.output_pm_project,
                "reference_stl": self.reference_stl,
                "agent_sim_stl": self.agent_sim_stl,
            }
        )
        return metadata


# ---------------------------------------------------------------------------
# Local scripts directory — scripts are read from here and uploaded to VM
# as temporary files during evaluation.
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent / "scripts"


def _read_script(name: str) -> str:
    """Read a script file from the local scripts/ directory."""
    return (SCRIPTS_DIR / name).read_text(encoding="utf-8")


#################################################################
###################### Task Registration ########################
#################################################################


@cb.tasks_config(split="train")
def load():
    """Register all 15 GCode CAM task variants."""
    return [
        cb.Task(
            description=GCodeTaskConfig(
                TASK_TAG=tag,
                PM_PROJECT_NAME=pm,
            ).task_description,
            metadata=GCodeTaskConfig(
                TASK_TAG=tag,
                PM_PROJECT_NAME=pm,
            ).to_metadata(),
            computer={
                "provider": "computer",
                "setup_config": {"os_type": "windows"},
            },
        )
        for tag, pm in VARIANTS
    ]


#################################################################
######################## Initialization #########################
#################################################################


@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    """Prepare the environment before the agent starts.

    Steps:
    1. Clean and recreate the output directory
    2. Copy the blank PM project from input/ to output/ (copy-to-output pattern)
    3. Open the copied project in PowerMill so the agent starts ready-to-work
    """
    meta = task_cfg.metadata
    task_tag = meta["task_tag"]
    output_dir = meta["remote_output_dir"]
    input_pm = meta["input_pm_project"]
    output_pm = meta["output_pm_project"]

    logger.info(f"[{task_tag}] Setting up GCode CAM task")

    # 1. Clean and recreate output directory
    try:
        await session.remove_file(output_dir)
    except Exception:
        pass
    await session.makedirs(output_dir)
    logger.info(f"[{task_tag}] Output directory ready: {output_dir}")

    # 2. Copy blank PM project from input/ to output/
    # This way the agent modifies files in output/ and input/ stays pristine
    await session.copy_file(input_pm, output_pm)
    logger.info(f"[{task_tag}] Copied PM project to output: {output_pm}")

    # 3. Open the PM project in PowerMill (via .pmlprj or shortcut)
    # Try to find the .pmlprj file inside the project folder
    try:
        files = await session.list_dir(output_pm)
        pmlprj_files = [f for f in files if f.endswith(".pmlprj")]
        if pmlprj_files:
            pmlprj_path = rf"{output_pm}\{pmlprj_files[0]}"
            await session.run_file(pmlprj_path)
            logger.info(f"[{task_tag}] Opened PM project: {pmlprj_path}")
        else:
            # Fallback: open the project directory itself
            await session.run_file(output_pm)
            logger.info(f"[{task_tag}] Opened PM project directory: {output_pm}")
    except Exception as e:
        logger.warning(f"[{task_tag}] Could not auto-open PM project: {e}")

    # Give PowerMill time to load the project
    await asyncio.sleep(10)
    logger.info(f"[{task_tag}] Setup complete — agent may begin")


#################################################################
########################## Evaluation ###########################
#################################################################


@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the agent's toolpath design.

    Pipeline (full run):
      1. Upload evaluation scripts to a temp location on the VM
      2. Gate check: collision/gouge detection (score=0 if any)
      3. Simulate: export agent's stock model as agent_sim.stl
      4. Score: compare agent_sim.stl vs reference_sim.stl

    Test mode:
      If agent_sim.stl already exists in the output directory (e.g. placed
      by setup_test_dirs.py for pos/neg testing), steps 1-3 are skipped
      and only the STL comparison (step 4) runs. This allows testing the
      evaluation with REMOTE_OUTPUT_DIR=output_test_pos / output_test_neg.
    """
    meta = task_cfg.metadata
    task_tag = meta["task_tag"]
    output_dir = meta["remote_output_dir"]
    output_pm = meta["output_pm_project"]
    ref_stl = meta["reference_stl"]
    agent_stl = meta["agent_sim_stl"]

    logger.info(f"[{task_tag}] Starting evaluation (output_dir={output_dir})")

    # ── 0. Upload evaluation scripts to VM temp folder ───────────────────────
    # Scripts are stored locally in this codebase and uploaded at eval time.
    tmp_scripts = r"C:\Users\User\AppData\Local\Temp\gcode_eval_scripts"
    await session.makedirs(tmp_scripts)

    for script_name in ["simulate_agent.py", "verify_stl.py", "check_collision.py"]:
        script_content = _read_script(script_name)
        remote_path = rf"{tmp_scripts}\{script_name}"
        await session.write_file(remote_path, script_content)

    logger.info(f"[{task_tag}] Evaluation scripts uploaded to {tmp_scripts}")

    # ── Check if agent_sim.stl already exists (test mode) ────────────────────
    # In test mode (output_test_pos / output_test_neg), agent_sim.stl is
    # pre-placed. Skip collision check and simulation — go straight to scoring.
    agent_stl_exists = await session.exists(agent_stl)

    if not agent_stl_exists:
        # Full evaluation: collision gate + simulation + scoring

        # ── 1. Gate: Collision / Gouge check ─────────────────────────────────
        logger.info(f"[{task_tag}] Step 1/3: Checking for collisions and gouges...")
        collision_script = rf"{tmp_scripts}\check_collision.py"
        result = await session.run_command(
            f'python "{collision_script}" --project "{output_pm}"',
        )

        collision_passed = True
        try:
            collision_data = json.loads(result["stdout"])
            collision_passed = collision_data.get("passed", False)
            logger.info(
                f"[{task_tag}] Collision check: passed={collision_passed}, "
                f"collisions={collision_data.get('collision_count', '?')}, "
                f"gouges={collision_data.get('gouge_count', '?')}"
            )
        except Exception as e:
            logger.warning(f"[{task_tag}] Could not parse collision output: {e}")

        if not collision_passed:
            logger.warning(f"[{task_tag}] Gate FAILED: collisions/gouges -> score = 0.0")
            return [0.0]

        # ── 2. Simulate agent toolpath → export agent_sim.stl ────────────────
        logger.info(f"[{task_tag}] Step 2/3: Simulating agent toolpath...")
        simulate_script = rf"{tmp_scripts}\simulate_agent.py"
        result = await session.run_command(
            f'python "{simulate_script}" --project "{output_pm}" --output "{output_dir}"',
        )
        logger.info(f"[{task_tag}] Simulation: {result.get('stdout', '')[:200]}")

        if result.get("return_code", 1) != 0:
            logger.error(f"[{task_tag}] Simulation failed: {result.get('stderr', '')[:200]}")
            return [0.0]

        # Verify agent STL was created
        if not await session.exists(agent_stl):
            logger.error(f"[{task_tag}] agent_sim.stl not found at {agent_stl}")
            return [0.0]
    else:
        logger.info(
            f"[{task_tag}] agent_sim.stl already exists — "
            f"skipping collision check and simulation (test mode)"
        )

    # ── 3. Score: compare agent STL vs reference STL ─────────────────────────
    logger.info(f"[{task_tag}] Scoring: Comparing agent STL to reference STL...")

    if not await session.exists(ref_stl):
        logger.error(f"[{task_tag}] reference_sim.stl not found: {ref_stl}")
        return [0.0]

    verify_script = rf"{tmp_scripts}\verify_stl.py"
    result = await session.run_command(
        f'python "{verify_script}" --agent "{agent_stl}" --reference "{ref_stl}"',
    )

    score = 0.0
    try:
        verify_data = json.loads(result["stdout"])
        score = float(verify_data.get("score", 0.0))
        logger.info(
            f"[{task_tag}] Score={score:.4f}, "
            f"mean_dist={verify_data.get('mean_dist_mm', '?')}mm, "
            f"ratio_perfect={verify_data.get('ratio_perfect', '?')}, "
            f"ratio_acceptable={verify_data.get('ratio_acceptable', '?')}"
        )
    except Exception as e:
        logger.error(f"[{task_tag}] Could not parse verify output: {e}")

    logger.info(f"[{task_tag}] Final score: {score:.4f}")
    return [score]
