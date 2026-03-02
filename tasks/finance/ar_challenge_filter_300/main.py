"""Finance subtask: ar_challenge_filter_300 (challenge filter+aggregation)."""

import logging
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from tasks.finance.annual_report.subtask_eval_utils import verify_metrics_table_remote, win_join

logger = logging.getLogger(__name__)


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "ar_challenge_filter_300"
    TASK_CATEGORY: str = "finance"

    @property
    def file_list_url(self) -> str:
        return win_join(self.task_dir, "input", "file_list.txt")

    @property
    def output_url(self) -> str:
        return win_join(self.remote_output_dir, "final_metrics.xlsx")

    @property
    def task_description(self) -> str:
        return f"""
Goal:
Apply advanced personnel filtering and aggregation on annual reports listed in {self.file_list_url}.
Source annual reports should be obtained from East Money (东方财富) using file names in `file_list.txt`.

Input Files:
1) {self.file_list_url}
   - PDF filename list (report scope).

Magic Number Definition (EducationLevelFixed):
- 1 = PhD
- 2 = Master
- 3 = Bachelor
- 4 = Associate
- 5 = Other / Undisclosed

Flag Definition (binary fields used in rules):
- 是否兼任董事: 1 = Yes, 2 = No
- 是否兼任高级管理人员: 1 = Yes, 2 = No

Core Rule Set:
- Group A: EducationLevelFixed <= 2 and 是否兼任董事==1; Group B: EducationLevelFixed == 3 and 是否兼任高级管理人员==1.

Output File:
- Save one Excel file to {self.output_url}
- Required columns (strict order):
  "证券代码", "股票简称", "A Count", "B Count", "A CAGR 2019->2023 (%)", "B Salary Volatility (CV%)", "A Outperformance Years (2019-2023)"

Data Validity Rules:
- Output all required numeric fields as numbers.
- For numeric output values, keep at least 3 decimal places (0.001 precision) when applicable.
- Valid year definition:
  - A year is valid only if that company-year report exists in the task `file_list.txt`.
  - For salary/shareholding, only numeric values > 0 are valid.
- Period-based averages are computed over valid years only (no interpolation / no backfilling).
- For each average metric, validity is checked only on that metric's required year window.

Scoring:
- Full score requires all conditions below to be satisfied:
  1) `final_metrics.xlsx` exists at the required output path.
  2) Header names and order are exactly correct.
  3) One correct row is provided for every target company.
  4) All computed values match hidden ground truth under the specified rules.
"""

    def to_metadata(self) -> dict:
        md = super().to_metadata()
        md.update(
            {
                "file_list_url": self.file_list_url,
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
