"""WGS Variant Calling Task - Bioinformatics Benchmark."""

import logging
import re
import csv
import io
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig

logger = logging.getLogger(__name__)


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "WGS_Variant_Calling"
    TASK_CATEGORY: str = "bioinformatics"
    OS_TYPE: str = "windows"

    # Evaluation thresholds
    MIN_MAPPING_RATE: float = 95.0
    MAX_DUPLICATION_RATE: float = 20.0
    MIN_SNP_F1: float = 0.99
    MIN_SNP_PRECISION: float = 0.99
    MIN_SNP_RECALL: float = 0.99
    MIN_INDEL_F1: float = 0.94
    MIN_INDEL_PRECISION: float = 0.97
    MIN_INDEL_RECALL: float = 0.91

    # Output filenames
    FASTQC_R1_FILE: str = "region_R1_fastqc.html"
    FASTQC_R2_FILE: str = "region_R2_fastqc.html"
    MULTIQC_FILE: str = "multiqc_report.html"
    FLAGSTAT_FILE: str = "flagstat.txt"
    DUPLICATION_FILE: str = "duplication_metrics.txt"
    VCF_FILE: str = "variants.filtered.vcf.gz"
    VCF_INDEX_FILE: str = "variants.filtered.vcf.gz.tbi"
    RTG_SUMMARY_FILE: str = "rtg_summary.csv"

    @property
    def wsl_root(self) -> str:
        """Convert Windows REMOTE_ROOT_DIR to its WSL /mnt/... equivalent."""
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
    def task_description(self) -> str:
        return f"""You are given paired-end FASTQ files containing sequencing reads from a human sample, \
        along with a GRCh38 chromosome 17 reference genome. You are also given a GIAB truth set VCF and high-confidence BED \
        file for benchmarking your results.

        Your task is to execute a standard germline variant calling pipeline following GATK Best Practices, producing a \
        filtered VCF file containing SNVs and indels, and then evaluate your variant calls against the provided truth set \
        using RTG vcfeval.

        Existing File Structure:
        {self.wsl_task_dir}/
        ├── input/
        │   ├── region_R1.fastq.gz            # Paired-end Read 1
        │   ├── region_R2.fastq.gz            # Paired-end Read 2
        │   ├── chr17.fa                      # Reference genome (GRCh38 chr17)
        │   ├── chr17.fa.fai                  # Reference index
        │   ├── chr17.dict                    # Reference dictionary
        │   ├── truth_chr17.vcf.gz            # GIAB HG002 truth set (chr17)
        │   ├── truth_chr17.vcf.gz.tbi        # Truth set index
        │   └── eval_region_confident.bed     # High-confidence evaluation regions
        └── output/                           # Save all results here
            └── {self.RTG_SUMMARY_FILE}       # Save RTG vcfeval results here

        Environment:
        - An Ubuntu (WSL) terminal is already open at {self.wsl_task_dir}
        - Conda environment `bio-benchmark` is pre-activated with: bwa, samtools, gatk, bcftools, fastqc, multiqc, tabix, rtg-tools

        Requirements:
        Execute a standard germline variant calling pipeline following GATK Best Practices, from raw reads to a filtered \
        VCF, and evaluate your results against the provided truth set. Save the following files to the output directory:
        - {self.wsl_output_dir}/{self.FASTQC_R1_FILE} — FastQC report for Read 1
        - {self.wsl_output_dir}/{self.FASTQC_R2_FILE} — FastQC report for Read 2
        - {self.wsl_output_dir}/{self.MULTIQC_FILE} — Combined MultiQC report
        - {self.wsl_output_dir}/{self.FLAGSTAT_FILE} — samtools flagstat output showing alignment statistics (alignment rate must be >95%)
        - {self.wsl_output_dir}/{self.DUPLICATION_FILE} — GATK MarkDuplicates metrics file (duplication rate must be <20%)
        - {self.wsl_output_dir}/{self.VCF_FILE} — Final filtered VCF containing called SNVs and indels
        - {self.wsl_output_dir}/{self.VCF_INDEX_FILE} — Tabix index for the filtered VCF
        - {self.wsl_output_dir}/{self.RTG_SUMMARY_FILE} — Append SNP and INDEL rows to the pre-existing CSV using RTG vcfeval results. Don't modify the header of this file.

        Do not ask for confirmation. Execute each step directly.
        """

    def to_metadata(self) -> dict:
        metadata = super().to_metadata()
        metadata.update({
            "wsl_task_dir": self.wsl_task_dir,
            "wsl_output_dir": self.wsl_output_dir,
            "wsl_input_dir": self.wsl_input_dir,
            "min_mapping_rate": self.MIN_MAPPING_RATE,
            "max_duplication_rate": self.MAX_DUPLICATION_RATE,
            "min_snp_f1": self.MIN_SNP_F1,
            "min_snp_precision": self.MIN_SNP_PRECISION,
            "min_snp_recall": self.MIN_SNP_RECALL,
            "min_indel_f1": self.MIN_INDEL_F1,
            "min_indel_precision": self.MIN_INDEL_PRECISION,
            "min_indel_recall": self.MIN_INDEL_RECALL,
        })
        return metadata


config = TaskConfig()


@cb.tasks_config(split="train")
def load():
    """Define the WGS variant calling task."""
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
        # Clean and create output directory
        await session.remove_file(task_cfg.metadata["remote_output_dir"])
        await session.makedirs(task_cfg.metadata["remote_output_dir"])

        await session.run_command(
            f'powershell -Command "Set-Content -Path \'{task_cfg.metadata["remote_output_dir"]}\\{config.RTG_SUMMARY_FILE}\' -Value \'Type,Precision,Sensitivity,F_measure\'"'
        )

        # Ensure conda auto-activates bio-benchmark in WSL
        await session.run_command(
            'wsl bash -c "echo \'conda activate bio-benchmark\' >> ~/.bashrc"'
        )

        # Open WSL terminal at the task directory
        await session.run_command(
            f'powershell -Command "Start-Process wsl.exe -ArgumentList \'--cd {config.wsl_task_dir}\'"'
        )

    except Exception as e:
        logger.warning(f"Failed to setup task {config.TASK_TAG}: {e}")


# ── Helper functions ──

def parse_mapping_rate(flagstat_text: str) -> float | None:
    """Extract mapping rate from samtools flagstat output.

    Looks for a line like: '281428 + 0 mapped (99.93% : N/A)'
    Returns the percentage as a float, or None if not found.
    """
    for line in flagstat_text.split("\n"):
        if "mapped (" in line and "primary" not in line:
            match = re.search(r'\(([\d.]+)%', line)
            if match:
                return float(match.group(1))
    return None


def parse_duplication_rate(metrics_text: str) -> float | None:
    """Extract duplication rate from GATK MarkDuplicates metrics.

    The metrics file has a header line starting with 'LIBRARY' followed
    by a data line. The PERCENT_DUPLICATION column contains the rate as
    a decimal (e.g., 0.026 for 2.6%).
    Returns the percentage (e.g., 2.6), or None if not found.
    """
    lines = metrics_text.strip().split("\n")
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("LIBRARY"):
            header_idx = i
            break

    if header_idx is None or header_idx + 1 >= len(lines):
        return None

    headers = lines[header_idx].split("\t")
    values = lines[header_idx + 1].split("\t")

    try:
        dup_col = headers.index("PERCENT_DUPLICATION")
        return float(values[dup_col]) * 100  # Convert to percentage
    except (ValueError, IndexError):
        return None


def parse_rtg_summary(summary_text: str) -> dict | None:
    """Parse RTG vcfeval summary CSV and extract metrics.

    Expects a CSV with columns: Type, Precision, Sensitivity, F_measure
    with rows for SNP and INDEL.

    Returns a dict with keys: snp_f1, snp_precision, snp_recall,
    indel_f1, indel_precision, indel_recall. Values are floats.
    Returns None if parsing fails.
    """
    results = {}
    reader = csv.DictReader(io.StringIO(summary_text))

    for row in reader:
        row = {k.strip(): v.strip() for k, v in row.items()}
        variant_type = row.get("Type", "").upper()

        try:
            precision = float(row.get("Precision", 0))
            sensitivity = float(row.get("Sensitivity", 0))
            f_measure = float(row.get("F_measure", 0))
        except (ValueError, TypeError):
            continue

        if variant_type == "SNP":
            results["snp_f1"] = f_measure
            results["snp_precision"] = precision
            results["snp_recall"] = sensitivity
        elif variant_type == "INDEL":
            results["indel_f1"] = f_measure
            results["indel_precision"] = precision
            results["indel_recall"] = sensitivity

    return results if results else None


# ── Evaluation ──

@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the task based on checkpoint files."""

    output_dir = task_cfg.metadata["remote_output_dir"]
    score = 0.0

    # ── Checkpoint 0: QC Reports (weight: 0.1) ──
    try:
        qc_files = [
            f"{output_dir}\\{config.FASTQC_R1_FILE}",
            f"{output_dir}\\{config.FASTQC_R2_FILE}",
            f"{output_dir}\\{config.MULTIQC_FILE}",
        ]
        all_exist = True
        for qc_file in qc_files:
            file_bytes = await session.read_bytes(qc_file)
            if not file_bytes or len(file_bytes) < 100:
                all_exist = False
                logger.info(f"Checkpoint 0: missing or empty file {qc_file}")
                break

        if all_exist:
            score += 0.1
            logger.info("Checkpoint 0 PASSED: QC reports exist")
        else:
            logger.info("Checkpoint 0 FAILED: one or more QC reports missing")

    except Exception as e:
        logger.info(f"Checkpoint 0 FAILED: {e}")

    # ── Checkpoint 1: Flagstat (weight: 0.1) ──
    try:
        flagstat_bytes = await session.read_bytes(f"{output_dir}\\{config.FLAGSTAT_FILE}")
        if flagstat_bytes:
            flagstat_text = flagstat_bytes.decode()
            mapping_rate = parse_mapping_rate(flagstat_text)

            if mapping_rate is not None and mapping_rate > task_cfg.metadata["min_mapping_rate"]:
                score += 0.1
                logger.info(f"Checkpoint 1 PASSED: mapping rate {mapping_rate:.2f}%")
            else:
                logger.info(
                    f"Checkpoint 1 FAILED: mapping rate {mapping_rate} "
                    f"(threshold: >{task_cfg.metadata['min_mapping_rate']}%)"
                )
        else:
            logger.info("Checkpoint 1 FAILED: flagstat.txt not found")

    except Exception as e:
        logger.info(f"Checkpoint 1 FAILED: {e}")

    # ── Checkpoint 2: MarkDuplicates Metrics (weight: 0.1) ──
    try:
        dup_bytes = await session.read_bytes(f"{output_dir}\\{config.DUPLICATION_FILE}")
        if dup_bytes:
            dup_text = dup_bytes.decode()
            dup_rate = parse_duplication_rate(dup_text)

            if dup_rate is not None and dup_rate < task_cfg.metadata["max_duplication_rate"]:
                score += 0.1
                logger.info(f"Checkpoint 2 PASSED: duplication rate {dup_rate:.2f}%")
            else:
                logger.info(
                    f"Checkpoint 2 FAILED: duplication rate {dup_rate} "
                    f"(threshold: <{task_cfg.metadata['max_duplication_rate']}%)"
                )
        else:
            logger.info("Checkpoint 2 FAILED: duplication_metrics.txt not found")

    except Exception as e:
        logger.info(f"Checkpoint 2 FAILED: {e}")

    # ── Checkpoint 3: VCF Validity (weight: 0.1) ──
    try:
        vcf_bytes = await session.read_bytes(f"{output_dir}\\{config.VCF_FILE}")
        tbi_bytes = await session.read_bytes(f"{output_dir}\\{config.VCF_INDEX_FILE}")

        vcf_has_variants = vcf_bytes is not None and len(vcf_bytes) > 10000
        tbi_exists = tbi_bytes is not None and len(tbi_bytes) > 0

        if vcf_has_variants and tbi_exists:
            score += 0.1
            logger.info(f"Checkpoint 3 PASSED: VCF valid ({len(vcf_bytes)} bytes)")
        else:
            logger.info(
                f"Checkpoint 3 FAILED: vcf_has_variants={vcf_has_variants}, tbi_exists={tbi_exists}"
            )

    except Exception as e:
        logger.info(f"Checkpoint 3 FAILED: {e}")

    # ── Checkpoint 4: RTG vcfeval Metrics (weight: 0.6, six sub-checks at 0.1 each) ──
    try:
        rtg_bytes = await session.read_bytes(f"{output_dir}\\{config.RTG_SUMMARY_FILE}")
        if rtg_bytes:
            rtg_text = rtg_bytes.decode()
            metrics = parse_rtg_summary(rtg_text)

            if metrics:
                # SNP F1
                snp_f1 = metrics.get("snp_f1", 0)
                if snp_f1 > task_cfg.metadata["min_snp_f1"]:
                    score += 0.1
                    logger.info(f"Checkpoint 4a PASSED: SNP F1 = {snp_f1:.4f}")
                else:
                    logger.info(f"Checkpoint 4a FAILED: SNP F1 = {snp_f1:.4f} (threshold: >{task_cfg.metadata['min_snp_f1']})")

                # SNP Precision
                snp_precision = metrics.get("snp_precision", 0)
                if snp_precision > task_cfg.metadata["min_snp_precision"]:
                    score += 0.1
                    logger.info(f"Checkpoint 4b PASSED: SNP Precision = {snp_precision:.4f}")
                else:
                    logger.info(f"Checkpoint 4b FAILED: SNP Precision = {snp_precision:.4f} (threshold: >{task_cfg.metadata['min_snp_precision']})")

                # SNP Recall
                snp_recall = metrics.get("snp_recall", 0)
                if snp_recall > task_cfg.metadata["min_snp_recall"]:
                    score += 0.1
                    logger.info(f"Checkpoint 4c PASSED: SNP Recall = {snp_recall:.4f}")
                else:
                    logger.info(f"Checkpoint 4c FAILED: SNP Recall = {snp_recall:.4f} (threshold: >{task_cfg.metadata['min_snp_recall']})")

                # INDEL F1
                indel_f1 = metrics.get("indel_f1", 0)
                if indel_f1 > task_cfg.metadata["min_indel_f1"]:
                    score += 0.1
                    logger.info(f"Checkpoint 4d PASSED: INDEL F1 = {indel_f1:.4f}")
                else:
                    logger.info(f"Checkpoint 4d FAILED: INDEL F1 = {indel_f1:.4f} (threshold: >{task_cfg.metadata['min_indel_f1']})")

                # INDEL Precision
                indel_precision = metrics.get("indel_precision", 0)
                if indel_precision > task_cfg.metadata["min_indel_precision"]:
                    score += 0.1
                    logger.info(f"Checkpoint 4e PASSED: INDEL Precision = {indel_precision:.4f}")
                else:
                    logger.info(f"Checkpoint 4e FAILED: INDEL Precision = {indel_precision:.4f} (threshold: >{task_cfg.metadata['min_indel_precision']})")

                # INDEL Recall
                indel_recall = metrics.get("indel_recall", 0)
                if indel_recall > task_cfg.metadata["min_indel_recall"]:
                    score += 0.1
                    logger.info(f"Checkpoint 4f PASSED: INDEL Recall = {indel_recall:.4f}")
                else:
                    logger.info(f"Checkpoint 4f FAILED: INDEL Recall = {indel_recall:.4f} (threshold: >{task_cfg.metadata['min_indel_recall']})")
            else:
                logger.info("Checkpoint 4 FAILED: could not parse RTG summary")
        else:
            logger.info(f"Checkpoint 4 FAILED: {config.RTG_SUMMARY_FILE} not found")

    except Exception as e:
        logger.info(f"Checkpoint 4 FAILED: {e}")

    logger.info(f"Final score: {score:.2f}")
    return [score]