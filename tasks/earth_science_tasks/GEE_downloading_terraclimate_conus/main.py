"""
AgentHLE Task Specification: TerraClimate Data Download for CONUS

This task requires downloading TerraClimate dataset for the Continental United States (CONUS)
from 2016-2020, calculating monthly means for all variables required by the task, downloading as TIF images,
and combining them into a NetCDF file using Google Earth Engine.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from utils.evaluation import EvaluationContext
import os
logger = logging.getLogger(__name__)



@dataclass
class TaskConfig(GeneralTaskConfig):
    """Task configuration for TerraClimate data download."""

    TASK_TAG: str = "GEE_downloading_terraclimate_conus"
    TASK_CATEGORY: str = "earth_science_tasks"

    # Task-specific configuration
    # For testing: set GEE_TEST_PERIOD=6 to use 2016-2020 only (6 years, fewer files)
   
    EXPECTED_FILE_PATTERN: str = "terra_"
    EXPECTED_MONTHS: int = 60  # 12 monthly means (same for 1 year or 8 years)

    # Time range and variables for evaluation
    TEMPORAL_START: str = "2016-01-01"
    TEMPORAL_END: str = "2016-12-31"
    required_variables: tuple = ("pr",)

    # Authentication configuration (for benchmark - use service account via env vars)
    GEE_CREDENTIALS_PATH: str = os.environ.get("GEE_CREDENTIALS_PATH", "")
    GEE_SERVICE_ACCOUNT: str = os.environ.get("GEE_SERVICE_ACCOUNT", "")
    GCS_BUCKET: str = os.environ.get("GCS_BUCKET", "")
    GEE_ACCOUNT_EMAIL: str = os.environ.get("GEE_ACCOUNT_EMAIL", "agenthle.sv@gmail.com")

    @property
    def input_dir(self) -> str:
        """Input directory containing a tif image for the target area and instructions for the downloading."""
        return fr"{self.task_dir}\input"

    @property
    def geojson_path(self) -> str:
        """Path to CONUS boundary tif file."""
        return fr"{self.input_dir}\conus.tif"


    @property
    def task_description(self) -> str:
        """Task description shown to the agent."""
        start_yr = self.TEMPORAL_START[:4]
        end_yr = self.TEMPORAL_END[:4]
        return f"""Download TerraClimate dataset for CONUS from 2016-01-01 to 2016-12-31, only have the pr variable, calculate monthly means, download as TIF images, and combine into a NetCDF file using Google Earth Engine.

Goal:
- open visual studio code and write a python script 
- The python script should use Google Earth Engine Python API to access TerraClimate collection (IDAHO_EPSCOR/TERRACLIMATE)
- Filter data for CONUS region using the provided tif file
- choose the variable "pr"
- Calculate monthly means by grouping images by month (1-12) across years 2016-01-01 to 2016-12-31
- Export monthly means and download to local machine, named by yyyy-mm-dd.tif
- Combine all TIF files into a single NetCDF file using Python 
- Save the final NetCDF file to the output directory (preferred filename pattern: terra_pr_2016_2023.nc, but any .nc filename is acceptable)


Authentication:
- **Service Account**: The key file is in the input folder. Use this path in your Python script:
  - Credentials path: {self.input_dir}\\agenthle-data-gee-6d8ace79c103.json
  - Service account: agenthle-benchmark-gee@agenthle-data-gee.iam.gserviceaccount.com
  - In code:
    ```python
    import ee
    credentials = ee.ServiceAccountCredentials(
        "agenthle-benchmark-gee@agenthle-data-gee.iam.gserviceaccount.com",
        r"{self.input_dir}\\agenthle-data-gee-6d8ace79c103.json"
    )
    ee.Initialize(credentials)
    ```
  - No browser interaction needed 

Output:
- TIF files containing the monthly means of the target area
- NC file containing the monthly means of the target area
- Include these variables: pr
- time range: 2016-01-01 to 2016-12-31
- output file: 
    terra_2016-2020_pr.nc
    2016-12-01.tif, ... , 2020-12-01.tif
"""

    def to_metadata(self) -> dict:
        """Convert config to metadata dict for cua_bench Task."""
        metadata = super().to_metadata()
        metadata.update({
            "input_dir": self.input_dir,
            "geojson_path": self.geojson_path,
            "expected_file_pattern": self.EXPECTED_FILE_PATTERN,
            "temporal_start": self.TEMPORAL_START,
            "temporal_end": self.TEMPORAL_END,
            "required_variables": list(self.required_variables),
            "gee_credentials_path": self.GEE_CREDENTIALS_PATH,
            "gee_service_account": self.GEE_SERVICE_ACCOUNT,
            "gee_account_email": self.GEE_ACCOUNT_EMAIL,
            "gcs_bucket": self.GCS_BUCKET,
        })
        return metadata


config = TaskConfig()


# Part 1: load() - Declare the task

@cb.tasks_config(split="train")
def load():
    """Define the data download demo task."""
    return [
        cb.Task(
            description=config.task_description,
            metadata=config.to_metadata(),
            computer={
                "provider": "computer",
                "setup_config": {
                    "os_type": config.OS_TYPE
                }
            }
        )
    ]



# Part 2: start() - Prepare the remote environment

@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    """Prepare the remote environment for the TerraClimate data download coding task."""
    metadata = task_cfg.metadata
    output_dir = metadata["remote_output_dir"]
    input_dir = metadata["input_dir"]
    reference_dir = metadata["reference_dir"]
    geojson_path = metadata.get("geojson_path")

    logger.info(f"Setting up task: {config.TASK_TAG}")

    try:
        # Clean up previous output and recreate directories
        try:
            exists = await session.exists(output_dir)
            if exists:
                await session.remove_file(output_dir)
                logger.info(f"Cleaned previous output directory: {output_dir}")
        except Exception as e:
            logger.warning(f"Could not clean output directory (may not exist): {e}")

        await session.makedirs(output_dir)
        await session.makedirs(input_dir)
        await session.makedirs(reference_dir)

        # Copy local input files to remote
        local_input_dir = Path(__file__).resolve().parent / "input"
        if local_input_dir.exists():
            for f in local_input_dir.iterdir():
                if f.is_file():
                    try:
                        content = f.read_bytes()
                        remote_path = fr"{input_dir}\{f.name}"
                        await session.write_bytes(remote_path, content)
                        logger.info(f"Copied input file to remote: {f.name}")
                    except Exception as e:
                        logger.warning(f"Failed to copy {f.name} to remote: {e}")
        else:
            logger.warning(f"Local input dir not found: {local_input_dir}")

        # Verify input file exists
        if geojson_path:
            try:
                exists = await session.exists(geojson_path)
                if exists:
                    logger.info(f"Input file found: {geojson_path}")
                else:
                    logger.warning(f"Input file not found (agent will need to handle): {geojson_path}")
            except Exception as e:
                logger.warning(f"Could not verify input file: {e}")

        logger.info(f"Environment prepared: output={output_dir}, input={input_dir}")
    except Exception as e:
        logger.warning(f"Failed to setup task {config.TASK_TAG}: {e}")




# Part 3: evaluate() - Score agent outputs

def _evaluate_netcdf_content(
    output_path: str,
    reference_path: str,
    required_vars: list[str],
) -> list[dict]:
    """Run NC file content checks.

    1) Check dimensions: has x, y, time
    2) Check dim lengths same as reference
    3) Check variables match required
    4) output - reference should be zero (data identical)
    """
    import numpy as np
    import xarray as xr

    checks = []

    with xr.open_dataset(reference_path) as ref_ds:
        ref_dims = dict(ref_ds.dims)
        ref_data_vars = list(ref_ds.data_vars)

    with xr.open_dataset(output_path) as out_ds:
        out_dims = dict(out_ds.dims)
        out_data_vars = list(out_ds.data_vars)

    # 1) Check dimensions: has x, y, time
    has_xy_time = "x" in out_dims and "y" in out_dims and "time" in out_dims
    checks.append({
        "check": "nc_dims_xy_time",
        "passed": has_xy_time,
        "message": f"Has x, y, time dims: {dict(out_dims)}" if has_xy_time else f"Expected x,y,time dims, got {dict(out_dims)}",
    })

    if not has_xy_time:
        return checks

    # 2) Check dim lengths same as reference
    dims_match = True
    mismatches = []
    for d in ["x", "y", "time"]:
        out_len = out_dims.get(d, 0)
        ref_len = ref_dims.get(d, 0)
        if out_len != ref_len:
            dims_match = False
            mismatches.append(f"{d}: {out_len} vs ref {ref_len}")
    dim_match_msg = "All dim lengths match reference" if dims_match else "; ".join(mismatches)
    checks.append({
        "check": "nc_dim_lengths_match_reference",
        "passed": dims_match,
        "message": dim_match_msg,
    })

    if not dims_match:
        return checks

    # 3) Check variables match required
    required_set = set(required_vars)
    has_required = required_set.issubset(set(out_data_vars))
    only_required = set(out_data_vars) <= required_set
    var_match = has_required and only_required
    checks.append({
        "check": "nc_variables_match_required",
        "passed": var_match,
        "message": f"Variables {out_data_vars} match required {required_vars}" if var_match else f"Expected {required_vars}, got {out_data_vars}",
    })

    if not var_match:
        return checks

    # 4) output - reference should be zero (data identical)
    with xr.open_dataset(output_path) as out_ds, xr.open_dataset(reference_path) as ref_ds:
        max_diff = 0.0
        diff_zero = True
        for var in required_vars:
            if var not in out_ds.data_vars or var not in ref_ds.data_vars:
                diff_zero = False
                break
            diff_da = out_ds[var] - ref_ds[var]  # xarray aligns by dim names
            diff_vals = np.abs(diff_da.values.astype(float))
            max_diff = max(max_diff, float(np.nanmax(diff_vals)))
            if max_diff > 1e-9:
                diff_zero = False

    checks.append({
        "check": "nc_output_minus_reference_zero",
        "passed": diff_zero,
        "message": "output - reference is zero" if diff_zero else f"output - reference max diff = {max_diff}",
    })

    return checks


@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Evaluate agent outputs against reference.

    Strategy:
    1) TIF files: same length, same filenames as reference
    2) NC file exists
    3) NC content: dims (x,y,time), dim lengths match reference, variables match required, output-ref=0
    """
    import tempfile

    metadata = task_cfg.metadata
    output_dir = metadata["remote_output_dir"]
    reference_dir = metadata["reference_dir"]
    required_vars = metadata.get("required_variables", ["pr"])
    task_tag = metadata["task_tag"]

    async with EvaluationContext(
        task_tag=task_tag,
        mode="custom",
        split="train",
    ) as ctx:
        checks = []

        try:
            output_files = await session.list_dir(output_dir)
            reference_files = await session.list_dir(reference_dir)
        except Exception as e:
            print(f"✗ Error listing directories: {e}")
            ctx.add_score(0.0)
            ctx.add_score(0.0)
            return [0.0]

        output_tif = sorted([f for f in output_files if f.lower().endswith(".tif")])
        reference_tif = sorted([f for f in reference_files if f.lower().endswith(".tif")])

        # 1) TIF check: same length, same filenames
        tif_same_length = len(output_tif) == len(reference_tif)
        tif_same_names = set(output_tif) == set(reference_tif)
        tif_passed = tif_same_length and tif_same_names
        checks.append({
            "check": "tif_files_match",
            "passed": tif_passed,
            "message": f"TIF count {len(output_tif)} vs ref {len(reference_tif)}, names match: {tif_same_names}",
        })
        ctx.add_score(1.0 if tif_passed else 0.0)

        # 2) NC file exists
        nc_files = [f for f in output_files if f.lower().endswith(".nc")]
        nc_exists = len(nc_files) > 0
        checks.append({
            "check": "nc_file_exists",
            "passed": nc_exists,
            "message": f"Found {len(nc_files)} NC file(s)" if nc_exists else "No .nc file in output",
        })
        ctx.add_score(1.0 if nc_exists else 0.0)

        if not nc_exists:
            print("\nEvaluation Results:")
            for c in checks:
                status = "✓" if c["passed"] else "✗"
                print(f"  {status} {c['check']}: {c['message']}")
            return [ctx.get_final_score(num_items=len(checks))]

        # 3) NC content checks
        output_nc = nc_files[0]
        ref_nc_files = [f for f in reference_files if f.lower().endswith(".nc")]
        if not ref_nc_files:
            print("✗ No reference NC file found")
            return [ctx.get_final_score(num_items=len(checks))]

        output_path_remote = fr"{output_dir}\{output_nc}"
        reference_path_remote = fr"{reference_dir}\{ref_nc_files[0]}"

        try:
            output_bytes = await session.read_bytes(output_path_remote)
            reference_bytes = await session.read_bytes(reference_path_remote)
        except Exception as e:
            print(f"✗ Error reading NC files: {e}")
            return [ctx.get_final_score(num_items=len(checks))]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_out = os.path.join(tmpdir, "output.nc")
            tmp_ref = os.path.join(tmpdir, "reference.nc")
            with open(tmp_out, "wb") as f:
                f.write(output_bytes)
            with open(tmp_ref, "wb") as f:
                f.write(reference_bytes)

            nc_checks = _evaluate_netcdf_content(tmp_out, tmp_ref, required_vars)
            checks.extend(nc_checks)
            for c in nc_checks:
                ctx.add_score(1.0 if c["passed"] else 0.0)

        print("\nEvaluation Results:")
        for c in checks:
            status = "✓" if c["passed"] else "✗"
            print(f"  {status} {c['check']}: {c['message']}")

        # Return 1.0 only if NC exists and all NC content checks pass (and TIF matches)
        all_passed = all(c["passed"] for c in checks)
        return [1.0 if all_passed else 0.0]



if __name__ == "__main__":
    print("Task Configuration:")
    print(f"  TASK_TAG: {config.TASK_TAG}")
    print(f"  Task Description: {config.task_description[:100]}...")
    print(f"\nMetadata:")
    import json
    print(json.dumps(config.to_metadata(), indent=2))
