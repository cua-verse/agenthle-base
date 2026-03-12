"""RNA-seq Differential Expression Task - Bioinformatics Benchmark."""

import os
import logging
from dataclasses import dataclass, field

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from tasks.bioinformatics.Differential_Expression.eval import (
    parse_star_log,
    parse_featurecounts_summary,
    parse_gene_counts,
    parse_deseq2_results,
    parse_taqman_truth,
    run_l2_evaluation,
)

logger = logging.getLogger(__name__)


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "Differential_Expression"
    TASK_CATEGORY: str = "bioinformatics"
    OS_TYPE: str = "windows"
    CONDA_ENV: str = "wf2-env"

    # Sample configuration
    SAMPLES: dict = field(default_factory=lambda: {
        "UHRR_rep1": "UHRR",
        "UHRR_rep2": "UHRR",
        "UHRR_rep3": "UHRR",
        "HBRR_rep1": "HBRR",
        "HBRR_rep2": "HBRR",
        "HBRR_rep3": "HBRR",
    })

    # L1 thresholds
    MIN_UNIQUE_MAPPING_RATE: float = 40.0
    MIN_ASSIGNMENT_RATE: float = 50.0
    MIN_GENES_WITH_COUNTS: int = 800
    MIN_GENES_WITH_PADJ: int = 300

    # L2 thresholds
    SPEARMAN_FULL_CREDIT: float = 0.90
    SPEARMAN_PARTIAL_CREDIT: float = 0.80
    MIN_DIRECTION_CONSISTENCY: float = 0.80
    MIN_AUC: float = 0.85
    QPCR_LOG2FC_THRESHOLD: float = 1.0

    # Output filenames
    MULTIQC_FILE: str = "multiqc_report.html"
    STAR_LOGS_DIR: str = "star_logs"
    GENE_COUNTS_FILE: str = "gene_counts.txt"
    GENE_COUNTS_SUMMARY_FILE: str = "gene_counts.txt.summary"
    DESEQ2_RESULTS_FILE: str = "deseq2_results.csv"

    # Evaluation data (not given to agent)
    TAQMAN_TRUTH_FILE: str = "taqman_truth.csv"

    @property
    def wsl_root(self) -> str:
        path = self.REMOTE_ROOT_DIR.replace("\\", "/")
        if len(path) >= 2 and path[1] == ":":
            drive = path[0].lower()
            path = f"/mnt/{drive}{path[2:]}"
        return path

    @property
    def wsl_task_dir(self) -> str:
        return f"{self.wsl_root}/{self.TASK_CATEGORY}/{self.TASK_TAG}"

    @property
    def wsl_output_dir(self) -> str:
        return f"{self.wsl_task_dir}/output"

    @property
    def wsl_input_dir(self) -> str:
        return f"{self.wsl_task_dir}/input"

    @property
    def wsl_eval_dir(self) -> str:
        return f"{self.wsl_task_dir}/eval_data"

    @property
    def task_description(self) -> str:
        return f"""You are given paired-end FASTQ files from 6 RNA-seq samples (3 replicates of UHRR and 3 replicates \
        of HBRR), along with a GRCh38 chromosome 17 reference genome and GENCODE gene annotation.

        Your task is to execute a standard RNA-seq differential expression analysis pipeline following community best practices \
        (STAR + featureCounts + DESeq2), producing a table of differentially expressed genes.

        Existing File Structure:
        {self.wsl_task_dir}/
        ├── input/
        │   ├── UHRR_rep1_R1.fastq.gz         # UHRR replicate 1, Read 1
        │   ├── UHRR_rep1_R2.fastq.gz         # UHRR replicate 1, Read 2
        │   ├── UHRR_rep2_R1.fastq.gz         # UHRR replicate 2, Read 1
        │   ├── UHRR_rep2_R2.fastq.gz         # UHRR replicate 2, Read 2
        │   ├── UHRR_rep3_R1.fastq.gz         # UHRR replicate 3, Read 1
        │   ├── UHRR_rep3_R2.fastq.gz         # UHRR replicate 3, Read 2
        │   ├── HBRR_rep1_R1.fastq.gz         # HBRR replicate 1, Read 1
        │   ├── HBRR_rep1_R2.fastq.gz         # HBRR replicate 1, Read 2
        │   ├── HBRR_rep2_R1.fastq.gz         # HBRR replicate 2, Read 1
        │   ├── HBRR_rep2_R2.fastq.gz         # HBRR replicate 2, Read 2
        │   ├── HBRR_rep3_R1.fastq.gz         # HBRR replicate 3, Read 1
        │   ├── HBRR_rep3_R2.fastq.gz         # HBRR replicate 3, Read 2
        │   ├── chr17.fa                       # Reference genome (GRCh38 chr17)
        │   ├── chr17.gtf                      # GENCODE v44 annotation (chr17 only)
        │   └── sample_info.csv                # Sample grouping file
        └── output/
            └── {self.DESEQ2_RESULTS_FILE}     # Save DESeq2 results here (header pre-created)

        Environment:
        - An Ubuntu (WSL) terminal is already open at {self.wsl_task_dir}
        - Conda environment `{self.CONDA_ENV}` is pre-activated with: STAR, subread (featureCounts), fastqc, multiqc, samtools, R with DESeq2
        - R is available via `Rscript`

        Requirements:
        Execute a standard RNA-seq differential expression pipeline (STAR + featureCounts + DESeq2), from raw reads to a \
        differential expression results table. Save the following files to the output directory:
        - {self.wsl_output_dir}/{self.MULTIQC_FILE} — Combined MultiQC report for all samples
        - {self.wsl_output_dir}/{self.STAR_LOGS_DIR}/ — Directory containing STAR Log.final.out for each sample
        - {self.wsl_output_dir}/{self.GENE_COUNTS_FILE} — featureCounts gene count matrix
        - {self.wsl_output_dir}/{self.GENE_COUNTS_SUMMARY_FILE} — featureCounts assignment summary
        - {self.wsl_output_dir}/{self.DESEQ2_RESULTS_FILE} — Append DESeq2 results to the pre-existing CSV. Don't modify the header of this file.

        Do not ask for confirmation. Execute each step directly.
        """

    def to_metadata(self) -> dict:
        metadata = super().to_metadata()
        metadata.update({
            "wsl_task_dir": self.wsl_task_dir,
            "wsl_output_dir": self.wsl_output_dir,
            "wsl_input_dir": self.wsl_input_dir,
            "wsl_eval_dir": self.wsl_eval_dir,
            "samples": self.SAMPLES,
            "min_unique_mapping_rate": self.MIN_UNIQUE_MAPPING_RATE,
            "min_assignment_rate": self.MIN_ASSIGNMENT_RATE,
            "min_genes_with_counts": self.MIN_GENES_WITH_COUNTS,
            "min_genes_with_padj": self.MIN_GENES_WITH_PADJ,
            "spearman_full_credit": self.SPEARMAN_FULL_CREDIT,
            "spearman_partial_credit": self.SPEARMAN_PARTIAL_CREDIT,
            "min_direction_consistency": self.MIN_DIRECTION_CONSISTENCY,
            "min_auc": self.MIN_AUC,
            "qpcr_log2fc_threshold": self.QPCR_LOG2FC_THRESHOLD,
        })
        return metadata


config = TaskConfig()


@cb.tasks_config(split="train")
def load():
    """Define the RNA-seq differential expression task."""
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
    """Initialize the environment."""
    logger.info(f"Setting up task: {config.TASK_TAG}")

    try:
        output_dir = task_cfg.metadata["remote_output_dir"]

        # Clean and create output directory
        await session.remove_file(output_dir)
        await session.makedirs(output_dir)

        # Pre-create deseq2_results.csv with header
        deseq2_path = os.path.join(output_dir, config.DESEQ2_RESULTS_FILE)
        await session.run_command(
            f'powershell -Command "Set-Content -Path \'{deseq2_path}\' '
            f'-Value \'gene_id,baseMean,log2FoldChange,lfcSE,stat,pvalue,padj\'"'
        )

        # Create star_logs directory
        star_logs_path = os.path.join(output_dir, config.STAR_LOGS_DIR)
        await session.run_command(
            f'powershell -Command "New-Item -ItemType Directory -Force -Path \'{star_logs_path}\'"'
        )

        # Ensure conda auto-activates wf2-env in WSL
        await session.run_command(
            f'wsl bash -c "sed -i \'/conda activate/d\' ~/.bashrc && echo \'conda activate {config.CONDA_ENV}\' >> ~/.bashrc"'
        )

        # Open WSL terminal at the task directory
        await session.run_command(
            f'powershell -Command "Start-Process wsl.exe -ArgumentList \'--cd {config.wsl_task_dir}\'"'
        )

    except Exception as e:
        logger.warning(f"Failed to setup task {config.TASK_TAG}: {e}")


# ── Evaluation ──

@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the task based on checkpoint files (L1) and qPCR evaluation (L2)."""

    output_dir = task_cfg.metadata["remote_output_dir"]
    base_dir = os.path.dirname(output_dir)
    input_dir = os.path.join(base_dir, "input")
    eval_dir = os.path.join(base_dir, "eval_data")
    score = 0.0

    # ══════════════════════════════════════════════
    # L1: Automated Rule Checks (weight: 0.65)
    # ══════════════════════════════════════════════

    # ── Checkpoint 0: MultiQC Report (weight: 0.10) ──
    try:
        multiqc_path = os.path.join(output_dir, config.MULTIQC_FILE)
        multiqc_bytes = await session.read_bytes(multiqc_path)
        if multiqc_bytes and len(multiqc_bytes) > 100:
            score += 0.10
            logger.info("Checkpoint 0 PASSED: MultiQC report exists")
        else:
            logger.info("Checkpoint 0 FAILED: MultiQC report missing or empty")
    except Exception as e:
        logger.info(f"Checkpoint 0 FAILED: {e}")

    # ── Checkpoint 1: STAR Alignment Logs (weight: 0.15) ──
    try:
        star_logs_dir = os.path.join(output_dir, config.STAR_LOGS_DIR)
        
        # Find all Log.final.out files in star_logs/
        log_files = await session.run_command(
            f'powershell -Command "Get-ChildItem -Path \'{star_logs_dir}\' -Filter \'*Log.final.out\' -Name"'
        )

        raw_output = log_files["stdout"]
        log_names = [f.strip() for f in raw_output.strip().split("\n") if f.strip() and "Log.final.out" in f]

        expected_count = len(task_cfg.metadata["samples"])
        
        if len(log_names) < expected_count:
            logger.info(f"Checkpoint 1 FAILED: found {len(log_names)} log files, expected {expected_count}")
        else:
            all_logs_valid = True
            mapping_rates = {}

            for log_name in log_names:
                log_path = os.path.join(star_logs_dir, log_name)
                log_bytes = await session.read_bytes(log_path)

                if not log_bytes:
                    logger.info(f"Checkpoint 1: could not read {log_name}")
                    all_logs_valid = False
                    break

                rate = parse_star_log(log_bytes.decode())

                if rate is None:
                    logger.info(f"Checkpoint 1: could not parse mapping rate from {log_name}")
                    all_logs_valid = False
                    break

                if rate < task_cfg.metadata["min_unique_mapping_rate"]:
                    logger.info(f"Checkpoint 1: {log_name} mapping rate {rate:.1f}% below threshold")
                    all_logs_valid = False
                    break

                mapping_rates[log_name] = rate

            if all_logs_valid and len(mapping_rates) >= expected_count:
                score += 0.15
                rates_str = ", ".join(f"{k}: {v:.1f}%" for k, v in mapping_rates.items())
                logger.info(f"Checkpoint 1 PASSED: {len(mapping_rates)} STAR logs valid ({rates_str})")
            else:
                logger.info("Checkpoint 1 FAILED: logs missing, invalid, or below threshold")

    except Exception as e:
        logger.info(f"Checkpoint 1 FAILED: {e}")

    # ── Checkpoint 2: featureCounts Summary (weight: 0.10) ──
    try:
        summary_path = os.path.join(output_dir, config.GENE_COUNTS_SUMMARY_FILE)
        summary_bytes = await session.read_bytes(summary_path)
        if summary_bytes:
            summary_text = summary_bytes.decode()
            summary_parsed = parse_featurecounts_summary(summary_text)

            if summary_parsed:
                min_rate = summary_parsed["min_rate"]
                if min_rate >= task_cfg.metadata["min_assignment_rate"]:
                    score += 0.10
                    logger.info(f"Checkpoint 2 PASSED: featureCounts min assignment rate {min_rate:.1f}%")
                else:
                    logger.info(
                        f"Checkpoint 2 FAILED: min assignment rate {min_rate:.1f}% "
                        f"(threshold: >{task_cfg.metadata['min_assignment_rate']}%)"
                    )
            else:
                logger.info("Checkpoint 2 FAILED: could not parse featureCounts summary")
        else:
            logger.info("Checkpoint 2 FAILED: featureCounts summary not found")

    except Exception as e:
        logger.info(f"Checkpoint 2 FAILED: {e}")

    # ── Checkpoint 3: Gene Count Matrix (weight: 0.15) ──
    try:
        counts_path = os.path.join(output_dir, config.GENE_COUNTS_FILE)
        counts_bytes = await session.read_bytes(counts_path)
        if counts_bytes:
            counts_text = counts_bytes.decode()
            counts_parsed = parse_gene_counts(counts_text)

            if counts_parsed:
                n_samples = counts_parsed["num_samples"]
                n_genes_with_counts = counts_parsed["genes_with_counts"]

                sample_ok = n_samples == len(task_cfg.metadata["samples"])
                genes_ok = n_genes_with_counts >= task_cfg.metadata["min_genes_with_counts"]

                if sample_ok and genes_ok:
                    score += 0.15
                    logger.info(f"Checkpoint 3 PASSED: {n_samples} samples, {n_genes_with_counts} genes with counts")
                else:
                    logger.info(
                        f"Checkpoint 3 FAILED: samples={n_samples} (expected {len(task_cfg.metadata['samples'])}), "
                        f"genes_with_counts={n_genes_with_counts} (threshold: >{task_cfg.metadata['min_genes_with_counts']})"
                    )
            else:
                logger.info("Checkpoint 3 FAILED: could not parse gene count matrix")
        else:
            logger.info("Checkpoint 3 FAILED: gene count matrix not found")

    except Exception as e:
        logger.info(f"Checkpoint 3 FAILED: {e}")

    # ── Checkpoint 4: DESeq2 Results (weight: 0.15) ──
    deseq2_data = None
    try:
        deseq2_path = os.path.join(output_dir, config.DESEQ2_RESULTS_FILE)
        deseq2_bytes = await session.read_bytes(deseq2_path)
        if deseq2_bytes:
            deseq2_text = deseq2_bytes.decode()
            deseq2_parsed = parse_deseq2_results(deseq2_text)

            if deseq2_parsed and deseq2_parsed["has_required_columns"]:
                rows_with_padj = deseq2_parsed["rows_with_padj"]

                if rows_with_padj >= task_cfg.metadata["min_genes_with_padj"]:
                    score += 0.15
                    deseq2_data = deseq2_parsed["data"]
                    logger.info(
                        f"Checkpoint 4 PASSED: DESeq2 results valid, "
                        f"{deseq2_parsed['num_rows']} rows, {rows_with_padj} with padj"
                    )
                else:
                    logger.info(
                        f"Checkpoint 4 FAILED: rows_with_padj={rows_with_padj} "
                        f"(threshold: >{task_cfg.metadata['min_genes_with_padj']})"
                    )
            else:
                logger.info("Checkpoint 4 FAILED: DESeq2 results missing required columns")
        else:
            logger.info("Checkpoint 4 FAILED: DESeq2 results file not found")

    except Exception as e:
        logger.info(f"Checkpoint 4 FAILED: {e}")

    # ══════════════════════════════════════════════
    # L2: External qPCR Evaluation (weight: 0.35)
    # ══════════════════════════════════════════════

    if deseq2_data is not None:
        try:
            gtf_path = os.path.join(input_dir, "chr17.gtf")
            taqman_path = os.path.join(eval_dir, config.TAQMAN_TRUTH_FILE)

            gtf_bytes = await session.read_bytes(gtf_path)
            taqman_bytes = await session.read_bytes(taqman_path)

            if gtf_bytes and taqman_bytes:
                taqman_truth = parse_taqman_truth(taqman_bytes.decode())

                l2_results = run_l2_evaluation(
                    deseq2_data=deseq2_data,
                    gtf_text=gtf_bytes.decode(),
                    taqman_truth=taqman_truth,
                    qpcr_log2fc_threshold=task_cfg.metadata["qpcr_log2fc_threshold"],
                )

                matched = l2_results["matched_genes"]
                rho = l2_results["spearman_rho"]
                dir_cons = l2_results["direction_consistency"]
                auc = l2_results["auc"]

                logger.info(f"L2 results: matched={matched}, rho={rho}, direction={dir_cons}, auc={auc}")

                # Spearman rho (weight: 0.15 full, 0.05 partial)
                if rho is not None and rho >= task_cfg.metadata["spearman_full_credit"]:
                    score += 0.15
                    logger.info(f"L2a PASSED: Spearman rho = {rho:.4f}")
                elif rho is not None and rho >= task_cfg.metadata["spearman_partial_credit"]:
                    score += 0.05
                    logger.info(f"L2a PARTIAL: Spearman rho = {rho:.4f}")
                else:
                    logger.info(f"L2a FAILED: Spearman rho = {rho}")

                # Direction consistency (weight: 0.10)
                if dir_cons is not None and dir_cons >= task_cfg.metadata["min_direction_consistency"]:
                    score += 0.10
                    logger.info(f"L2b PASSED: Direction consistency = {dir_cons:.4f}")
                else:
                    logger.info(f"L2b FAILED: Direction consistency = {dir_cons}")

                # AUC (weight: 0.10)
                if auc is not None and auc >= task_cfg.metadata["min_auc"]:
                    score += 0.10
                    logger.info(f"L2c PASSED: AUC = {auc:.4f}")
                else:
                    logger.info(f"L2c FAILED: AUC = {auc}")

            else:
                gtf_status = "found" if gtf_bytes else "missing"
                taqman_status = "found" if taqman_bytes else "missing"
                logger.info(f"L2 SKIPPED: GTF {gtf_status}, taqman truth {taqman_status}")

        except Exception as e:
            logger.info(f"L2 FAILED: {e}")

    else:
        logger.info("L2 SKIPPED: DESeq2 results not available")

    logger.info(f"Final score: {score:.2f}")
    return [score]