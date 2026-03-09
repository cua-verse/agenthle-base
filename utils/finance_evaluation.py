"""
Expert Note:
This module implements the core scorer for finance subtasks.

What is truly hard in this benchmark:
- Agents frequently miss PDFs, miss qualified rows under filters, or compute
  metrics from rows that do not satisfy the exact conditions.
- Evaluation must distinguish formatting noise from real extraction/filtering
  errors.

Why this matters:
The scorer must reward complete file coverage and condition-consistent
extraction, otherwise leaderboard signals are misleading.

Scale Reality:
- Scoring logic serves tasks ranging from dozens to ~1500 report files per
  task, with the parent corpus at 2993 files.
- This scale amplifies penalties for missed files, missed rows, and condition
  mismatch.
"""

import json
import logging
from io import BytesIO
from pathlib import PureWindowsPath
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


def win_join(*parts: str) -> str:
    return str(PureWindowsPath(*parts))


def _penalty_for_full_task(reference_dir: str) -> int:
    return 5


def _penalty_for_metric_or_challenge_task(reference_dir: str) -> int:
    ref = str(reference_dir).lower().replace("/", "\\")
    if "\\ar_metric_company_" in ref or "\\ar_challenge_filter_" in ref:
        return 20
    return 5


def last_json(stdout: str) -> Dict[str, Any]:
    for ln in reversed([x.strip() for x in str(stdout).splitlines() if x.strip()]):
        try:
            return json.loads(ln)
        except Exception:
            continue
    return {}


async def verify_files_remote(session, output_dir: str, reference_dir: str) -> float:
    """50 points max. Penalty is task-specific per wrong/missing file."""
    manifest = win_join(reference_dir, "file_manifest.json")
    downloads = win_join(output_dir, "downloads")
    ps1_path = win_join(reference_dir, "_verify_files_md5.ps1")

    ps1 = r"""param(
  [Parameter(Mandatory=$true)][string]$ManifestPath,
  [Parameter(Mandatory=$true)][string]$DownloadsDir
)

$max = 20
$throttle = [Math]::Min(8, [Environment]::ProcessorCount)
if ($throttle -lt 1) { $throttle = 1 }

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$m = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

$total = ($m.PSObject.Properties | Measure-Object).Count
$correct = 0
$missing = 0; $size_bad = 0; $hash_bad = 0; $err = 0

$todo = New-Object System.Collections.Generic.List[object]

foreach ($p in $m.PSObject.Properties) {
  $fn = $p.Name
  $exp = $p.Value
  $fp = Join-Path $DownloadsDir $fn

  if (!(Test-Path -LiteralPath $fp)) {
    $missing++
    continue
  }

  try {
    $size = (Get-Item -LiteralPath $fp).Length
    $emin = [double]$exp.size * 0.95
    $emax = [double]$exp.size * 1.05
    if ($size -lt $emin -or $size -gt $emax) {
      $size_bad++
      continue
    }
    $todo.Add([pscustomobject]@{ fn=$fn; fp=$fp; exp_hash=($exp.hash.ToLower()) })
  } catch {
    $err++
    continue
  }
}

$pool = [RunspaceFactory]::CreateRunspacePool(1, $throttle)
$pool.Open()
$tasks = New-Object System.Collections.Generic.List[object]

$scriptBlock = {
  param($path)
  try {
    (Get-FileHash -LiteralPath $path -Algorithm MD5).Hash.ToLower()
  } catch {
    ""
  }
}

foreach ($item in $todo) {
  $ps = [PowerShell]::Create()
  $ps.RunspacePool = $pool
  [void]$ps.AddScript($scriptBlock).AddArgument($item.fp)
  $handle = $ps.BeginInvoke()
  $tasks.Add([pscustomobject]@{
    ps=$ps; handle=$handle; fn=$item.fn; exp_hash=$item.exp_hash
  })
}

foreach ($t in $tasks) {
  try {
    $res = $t.ps.EndInvoke($t.handle)
    $t.ps.Dispose()
    $hash = ""
    if ($res -is [System.Array] -and $res.Length -gt 0) { $hash = [string]$res[0] }
    elseif ($res) { $hash = [string]$res }

    if ([string]::IsNullOrEmpty($hash)) {
      $err++
      continue
    }

    if ($hash -eq $t.exp_hash) { $correct++ } else { $hash_bad++ }
  } catch {
    $err++
    continue
  }
}

$pool.Close()
$pool.Dispose()
$sw.Stop()

@{
  total=$total; correct=$correct; throttle=$throttle; hashed_count=$todo.Count; elapsed_sec=[Math]::Round($sw.Elapsed.TotalSeconds, 3);
  missing_count=$missing; size_mismatch_count=$size_bad; hash_mismatch_count=$hash_bad; error_count=$err
} | ConvertTo-Json -Compress
"""

    try:
        await session.write_file(ps1_path, ps1)
        cmd = (
            f'powershell -NoProfile -ExecutionPolicy Bypass -File "{ps1_path}" '
            f'-ManifestPath "{manifest}" -DownloadsDir "{downloads}"'
        )
        r = await session.run_command(cmd, check=False)
        stats = last_json(r.get("stdout", ""))
        if not stats:
            logger.warning("File MD5 check produced no parsable JSON.")
            return 0.0

        total = int(stats.get("total", 0))
        correct = int(stats.get("correct", 0))
        wrong = max(0, total - correct)
        penalty = _penalty_for_full_task(reference_dir)
        score = float(max(0, 50 - penalty * wrong))
        logger.info(
            "File check: total=%s correct=%s wrong=%s score=%.2f/50",
            total,
            correct,
            wrong,
            score,
        )
        return score
    except Exception as e:
        logger.warning("MD5 verification failed: %s", e)
        return 0.0


def _compare_value(actual: Any, expected: Any) -> bool:
    if pd.isna(actual) and pd.isna(expected):
        return True
    if pd.isna(actual) or pd.isna(expected):
        return False
    try:
        return abs(float(actual) - float(expected)) < 1e-2
    except Exception:
        return str(actual).strip() == str(expected).strip()


async def verify_dataset_samples_remote(session, output_dir: str, reference_dir: str) -> float:
    """50 points max. Penalty is task-specific per wrong sample in final_dataset.xlsx."""
    samples_path = win_join(reference_dir, "data_samples.json")
    table_path = win_join(output_dir, "final_dataset.xlsx")
    try:
        samples = json.loads(await session.read_file(samples_path))
    except Exception as e:
        logger.warning("Failed to read data_samples.json: %s", e)
        return 0.0

    if not await session.exists(table_path):
        logger.warning("final_dataset.xlsx missing: %s", table_path)
        return 0.0

    try:
        df = pd.read_excel(BytesIO(await session.read_bytes(table_path)))
    except Exception as e:
        logger.warning("Failed to read final_dataset.xlsx: %s", e)
        return 0.0

    if "璇嗗埆鐮?" not in df.columns:
        logger.warning("Missing required column: 璇嗗埆鐮?")
        return 0.0

    df_idx = df.set_index("璇嗗埆鐮?", drop=False)
    correct = 0
    total = len(samples)
    for s in samples:
        row_id = s["row_id"]
        col = s["column"]
        exp = s["value"]
        if row_id not in df_idx.index:
            continue
        row = df_idx.loc[row_id]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        act = row[col] if col in row.index else None
        if _compare_value(act, exp):
            correct += 1
    wrong = total - correct
    penalty = _penalty_for_full_task(reference_dir)
    score = float(max(0, 50 - penalty * wrong))
    logger.info("Data check: total=%s correct=%s wrong=%s score=%.2f/50", total, correct, wrong, score)
    return score


async def verify_metrics_table_remote(
    session,
    output_dir: str,
    reference_dir: str,
    output_filename: str = "final_metrics.xlsx",
    expected_filename: str = "expected_metrics.xlsx",
    key_col: str = "璇佸埜浠ｇ爜",
) -> float:
    """
    100 points max (normalized to 0-1 by caller).
    Strict header equality + GT row-key coverage, then cell-level accuracy.
    Extra output rows (keys not in GT) are ignored.
    Deduction is task-specific per mismatched/missing cell.
    """
    out_path = win_join(output_dir, output_filename)
    gt_path = win_join(reference_dir, expected_filename)

    if not await session.exists(out_path):
        logger.warning("Output file missing: %s", out_path)
        return 0.0
    try:
        out_df = pd.read_excel(BytesIO(await session.read_bytes(out_path)))
        gt_df = pd.read_excel(BytesIO(await session.read_bytes(gt_path)))
    except Exception as e:
        logger.warning("Failed reading metric files: %s", e)
        return 0.0

    if list(out_df.columns) != list(gt_df.columns):
        logger.warning("Header mismatch.")
        return 0.0
    if key_col not in out_df.columns:
        logger.warning("Missing key column: %s", key_col)
        return 0.0

    out_idx = out_df.set_index(key_col, drop=False)
    gt_idx = gt_df.set_index(key_col, drop=False)

    total = 0
    correct = 0
    for key, gt_row in gt_idx.iterrows():
        if key not in out_idx.index:
            total += len(gt_df.columns)
            continue
        out_row = out_idx.loc[key]
        if isinstance(out_row, pd.DataFrame):
            best = 0
            for _, cand in out_row.iterrows():
                cur = 0
                for col in gt_df.columns:
                    if _compare_value(cand[col], gt_row[col]):
                        cur += 1
                if cur > best:
                    best = cur
            total += len(gt_df.columns)
            correct += best
        else:
            for col in gt_df.columns:
                total += 1
                if _compare_value(out_row[col], gt_row[col]):
                    correct += 1

    wrong = total - correct
    penalty = _penalty_for_metric_or_challenge_task(reference_dir)
    score_100 = float(max(0, 100 - penalty * wrong))
    logger.info("Metric check: total=%s correct=%s wrong=%s score=%.2f/100", total, correct, wrong, score_100)
    return score_100
