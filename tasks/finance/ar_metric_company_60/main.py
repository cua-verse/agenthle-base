"""Finance subtask: ar_metric_company_60 (metric aggregation task)."""

import logging
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from tasks.finance.annual_report.subtask_eval_utils import verify_metrics_table_remote, win_join

logger = logging.getLogger(__name__)


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "ar_metric_company_60"
    TASK_CATEGORY: str = "finance"

    @property
    def file_list_url(self) -> str:
        return win_join(self.task_dir, "input", "file_list.txt")

    @property
    def target_companies_url(self) -> str:
        return win_join(self.task_dir, "input", "target_companies.json")

    @property
    def output_url(self) -> str:
        return win_join(self.remote_output_dir, "final_metrics.xlsx")

    @property
    def task_description(self) -> str:
        return f"""
Task Type:
- Metric aggregation task with strict table output requirements.

Goal:
- For each target company, compute required personnel statistics from annual-report-derived data.
- Source annual reports should be obtained from East Money (东方财富) using file names in `file_list.txt`.

Input Files:
1) {self.file_list_url}
   - PDF filename list (context of report scope).
2) {self.target_companies_url}
   - JSON array, one object per company.
   - Required keys: `证券代码`, `股票简称`.

Output File:
1) {self.output_url}
   - Excel, one sheet.
   - One row per target company.
   - Required columns in exact order:
     "证券代码", "股票简称", "Core Technical Staff Count", "2019-2023 Avg Salary"


Aggregation Rules:
- Use numeric aggregation only (no text placeholders).
- Use 2019-2023 columns exactly where requested.
- For numeric output values, keep at least 3 decimal places (0.001 precision) when applicable.
- Valid year definition:
  - A year is valid only if that company-year report exists in the task `file_list.txt`.
  - For salary/shareholding, only numeric values > 0 are valid.
- Period-based averages are computed over valid years only (no interpolation / no backfilling).
- For each average metric, validity is checked only on that metric's required year window.
- `2019-2023 Salary Std` (if required by this task) uses population standard deviation (ddof=0).

Scoring:
- Full score requires all conditions below to be satisfied:
  1) `final_metrics.xlsx` exists at the required output path.
  2) Header names and order are exactly correct.
  3) One correct row is provided for every target company.
  4) All metric values match hidden ground truth.
"""

    def to_metadata(self) -> dict:
        md = super().to_metadata()
        md.update(
            {
                "file_list_url": self.file_list_url,
                "target_companies_url": self.target_companies_url,
                "output_url": self.output_url,
            }
        )
        return md


config = TaskConfig()


@cb.tasks_config(split="train")
def load():
    return [
        cb.Task(
            description=config.task_description,
            metadata=config.to_metadata(),
            computer={"provider": "computer", "setup_config": {"os_type": config.OS_TYPE}},
        )
    ]


@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    outdir = task_cfg.metadata["remote_output_dir"]
    try:
        await session.remove_file(outdir)
        await session.makedirs(outdir)
        await session.makedirs(win_join(outdir, "downloads"))
    except Exception as e:
        logger.warning("Setup failed for %s: %s", config.TASK_TAG, e)


@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    outdir = task_cfg.metadata["remote_output_dir"]
    refdir = task_cfg.metadata["reference_dir"]
    try:
        score_100 = await verify_metrics_table_remote(session, outdir, refdir)
        return [score_100 / 100.0]
    except Exception as e:
        logger.warning("Evaluation error: %s", e)
        return [0.0]
