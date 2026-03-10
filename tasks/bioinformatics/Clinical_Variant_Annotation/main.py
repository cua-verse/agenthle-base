"""Clinical Variant Annotation Task - Bioinformatics Benchmark."""

import logging
import re
import os
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from utils.evaluation import llm_vision_judge, EvaluationContext

logger = logging.getLogger(__name__)


WSL_ROOT = "/mnt/c/Users/User/Desktop/tasks"


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "Clinical_Variant_Annotation"
    TASK_CATEGORY: str = "bioinformatics"
    OS_TYPE: str = "windows"
    REMOTE_ROOT_DIR: str = r"C:\Users\User\Desktop\tasks"

    # Ground truth
    PATHOGENIC_POS: str = "43106487"
    EXPECTED_VARIANT_COUNT: int = 200

    @property
    def wsl_task_dir(self) -> str:
        return f"{WSL_ROOT}/{self.TASK_CATEGORY}/{self.TASK_TAG}"

    @property
    def wsl_output_dir(self) -> str:
        return f"{self.wsl_task_dir}/output"

    @property
    def vcf_path(self) -> str:
        return f"{self.task_dir}\\input\\patient_variants.vcf"

    @property
    def task_description(self) -> str:
        return f"""You are given a VCF file containing variants from a patient's genome (GRCh38).
        Your task is to identify a single pathogenic variant using a standard clinical variant interpretation workflow. 

        Clinical Indication: early-onset breast cancer.

        File Structure:
        ├── input/
            ├── patient_variants.vcf
            ├── patient.bam
            ├── patient.bam.bai
        └── output/
            ├── vep_results.csv
            ├── gnomad_results.csv
            ├── clinvar_results.csv
            └── final_candidates.csv

        Environment:
        - An Ubuntu (WSL) terminal is already open at {self.wsl_task_dir}
        - python3, curl, and jq are available
        - IGV desktop application is already installed and available

        Available external resources:
        1. gnomAD GraphQL API (https://gnomad.broadinstitute.org/api)
        2. Ensembl VEP REST API (https://rest.ensembl.org/vep/human/region/)
        3. NCBI E-utilities / ClinVar (https://eutils.ncbi.nlm.nih.gov/entrez/eutils/)
        4. IGV desktop application

        Requirements:
        - Read the VCF file and count the total number of variants. Save the variant count as a single integer to: {self.wsl_output_dir}/variant_count.txt
        - Save intermediate results to the pre-existing CSV files in the output directory. Each file already has a header row defining the schema. Append rows to each file without modifying the header.
        - It is fine if some fields are NA in the CSV since some data may be unavailable from the API.
        - Output your final candidate pathogenic variant with justification in final_candidates.csv.
        - Navigate to the final candidate variant in IGV and save a screenshot using save_milestone_screenshot(path="{self.task_dir}\\output\\igv_screenshot.png")

        Do not ask for confirmation. Execute each step directly.
        """

    def to_metadata(self) -> dict:
        metadata = super().to_metadata()
        metadata.update({
            "vcf_path": self.vcf_path,
            "pathogenic_pos": self.PATHOGENIC_POS,
            "expected_variant_count": self.EXPECTED_VARIANT_COUNT,
        })
        return metadata

config = TaskConfig()

@cb.tasks_config(split="train")
def load():
    """Define the clinical variant annotation task."""
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
        # Clean output directory
        await session.remove_file(task_cfg.metadata["remote_output_dir"])
        await session.makedirs(task_cfg.metadata["remote_output_dir"])

        await session.run_command(
            f'powershell -Command "Set-Content -Path \'{task_cfg.metadata["remote_output_dir"]}\\vep_results.csv\' -Value \'CHROM,POS,REF,ALT,GENE,CONSEQUENCE,IMPACT,SIFT,POLYPHEN\'"'
        )

        await session.run_command(
            f'powershell -Command "Set-Content -Path \'{task_cfg.metadata["remote_output_dir"]}\\gnomad_results.csv\' -Value \'CHROM,POS,REF,ALT,ALLELE_FREQ\'"'
        )
        await session.run_command(
            f'powershell -Command "Set-Content -Path \'{task_cfg.metadata["remote_output_dir"]}\\clinvar_results.csv\' -Value \'CHROM,POS,REF,ALT,CLINVAR_RESULT\'"'
        )
    
        await session.run_command(
            f'powershell -Command "Set-Content -Path \'{task_cfg.metadata["remote_output_dir"]}\\final_candidates.csv\' -Value \'CHROM,POS,REF,ALT,JUSTIFICATION\'"'
        )

        await session.run_command(
            f'powershell -Command "Start-Process wsl.exe -ArgumentList \'--cd {config.wsl_task_dir}\'"'
        )
        

    except Exception as e:
        logger.warning(f"Failed to setup task {config.TASK_TAG}: {e}")

@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the task based on checkpoint files."""

    output_dir = task_cfg.metadata["remote_output_dir"]
    score = 0.0

    # ── Checkpoint 0: Variant Count (weight: 0.1) ──
    try:
       
        variant_count_bytes = await session.read_bytes(f"{output_dir}\\variant_count.txt")
        if variant_count_bytes:
            text = variant_count_bytes.decode().strip()
            numbers = re.findall(r'\d+', text)
            if numbers and int(numbers[0]) == task_cfg.metadata["expected_variant_count"]:
                score += 0.1
                logger.info("Checkpoint 0 PASSED: correct variant count")
            else:
                logger.info(f"Checkpoint 0 FAILED: expected {task_cfg.metadata['expected_variant_count']}, got {text}")
        else:
            logger.info("Checkpoint 0 FAILED: variant_count.txt not found")
    except Exception as e:
        logger.info(f"Checkpoint 0 FAILED: {e}")

    # ── Checkpoint 1: gnomAD Results (weight: 0.2) ──
    try:
        gnomad_bytes = await session.read_bytes(f"{output_dir}\\gnomad_results.csv")
        if gnomad_bytes:
            gnomad_text = gnomad_bytes.decode()
            lines = [l.strip() for l in gnomad_text.strip().split("\n") if l.strip()]
            data_lines = [l for l in lines if not l.upper().startswith("CHROM")]

            has_multiple_rows = len(data_lines) >= 2

            # BRCA1 variant should have no frequency or very low frequency
            brca1_line = next((l for l in data_lines if "43106487" in l), None)
            brca1_rare = False
            if brca1_line:
                fields = [f.strip() for f in brca1_line.split(",")]
                if len(fields) >= 5:
                    af = fields[-1].lower()
                    if af in ("", "null", "none", "not found", "n/a", "na", "."):
                        brca1_rare = True
                    else:
                        try:
                            brca1_rare = float(af) < 0.01
                        except ValueError:
                            brca1_rare = True

            # At least one variant should have a real numeric frequency
            has_numeric_freq = False
            for line in data_lines:
                fields = [f.strip() for f in line.split(",")]
                if len(fields) >= 5:
                    try:
                        float(fields[-1])
                        has_numeric_freq = True
                        break
                    except ValueError:
                        continue

            if has_multiple_rows and brca1_rare and has_numeric_freq:
                score += 0.2
                logger.info("Checkpoint 1 PASSED: gnomAD results correct")
            else:
                logger.info(
                    f"Checkpoint 1 FAILED: multiple_rows={has_multiple_rows}, "
                    f"brca1_rare={brca1_rare}, has_numeric_freq={has_numeric_freq}"
                )
        else:
            logger.info("Checkpoint 1 FAILED: gnomad_results.csv not found")
    
    except Exception as e:
        logger.info(f"Checkpoint 1 FAILED: {e}")

    # ── Checkpoint 2: VEP Results (weight: 0.2) ──
    try:
        vep_bytes = await session.read_bytes(f"{output_dir}\\vep_results.csv")
        if vep_bytes:
            vep_text = vep_bytes.decode()
            lines = [l.strip() for l in vep_text.strip().split("\n") if l.strip()]
            data_lines = [l for l in lines if not l.upper().startswith("CHROM")]

            has_rows = len(data_lines) >= 2
            brca1_annotated = any("43106487" in l and "BRCA1" in l.upper() for l in data_lines)
            has_consequence = any("missense" in l.lower() for l in data_lines)

            if has_rows and brca1_annotated and has_consequence:
                score += 0.2
                logger.info("Checkpoint 2 PASSED: VEP annotation correct")
            else:
                logger.info(
                    f"Checkpoint 2 FAILED: multiple_rows={has_rows}, "
                    f"brca1_annotated={brca1_annotated}, has_consequence={has_consequence}"
                )
        else:
            logger.info("Checkpoint 2 FAILED: vep_results.csv not found or empty")
    except Exception as e:
        logger.info(f"Checkpoint 2 FAILED: {e}")

    # ── Checkpoint 3: ClinVar Results (weight: 0.1) ──
    try:
        clinvar_bytes = await session.read_bytes(f"{output_dir}\\clinvar_results.csv")
        if clinvar_bytes:
            clinvar_text = clinvar_bytes.decode()
            lines = [l.strip() for l in clinvar_text.strip().split("\n") if l.strip()]
            data_lines = [l for l in lines if not l.upper().startswith("CHROM")]

            has_rows = len(data_lines) >= 1

            brca1_line = next((l for l in data_lines if "43106487" in l), None)
            brca1_pathogenic = False
            if brca1_line:
                brca1_pathogenic = "pathogenic" in brca1_line.lower()

            if has_rows and brca1_pathogenic:
                score += 0.1
                logger.info("Checkpoint 3 PASSED: ClinVar results correct")
            else:
                logger.info(
                    f"Checkpoint 3 FAILED: has_rows={has_rows}, "
                    f"brca1_pathogenic={brca1_pathogenic}"
                )
        else:
            logger.info("Checkpoint 3 FAILED: clinvar_results.csv not found")
    except Exception as e:
        logger.info(f"Checkpoint 3 FAILED: {e}")

    # ── Checkpoint 4: Final Candidates (weight: 0.2) ──
    try:
        candidates_bytes = await session.read_bytes(f"{output_dir}\\final_candidates.csv")

        if candidates_bytes:
            candidates_text = candidates_bytes.decode()
            lines = [l.strip() for l in candidates_text.strip().split("\n") if l.strip()]
            data_lines = [l for l in lines if not l.upper().startswith("CHROM")]

            variant_line = next((l for l in data_lines if "43106487" in l), None)
            variant_identified = False
            has_justification = False
            if variant_line:
                # Split only first 4 commas to preserve justification text
                fields = variant_line.split(",", 4)
                variant_identified = len(fields) >= 4 and "T" in fields[2].strip() and "G" in fields[3].strip()
                if len(fields) >= 5:
                    has_justification = 'pathogenic' in fields[4].strip().lower()

            if variant_identified and has_justification:
                score += 0.2
                logger.info("Checkpoint 4 PASSED: Final candidate correct with justification")
            else:
                logger.info(
                    f"Checkpoint 4 FAILED: variant_identified={variant_identified}, "
                    f"has_justification={has_justification}"
                )
        else:
            logger.info("Checkpoint 4 FAILED: final_candidates.csv not found")
    
    except Exception as e:
        logger.info(f"Checkpoint 4 FAILED: {e}")

    # ── Checkpoint 5: IGV Screenshot (weight: 0.2) ──
    try:
        file_name = "igv_screenshot"
        target_file_path = f"{output_dir}\\igv_screenshot.png"
        target_image_bytes = await session.read_bytes(target_file_path)

        prompt_with_question = lambda question: f"""You are evaluating an IGV screenshot for a clinical genomics task.

        1. First image: Screenshot generated by the agent

        Question: {question}

        Answer with ONLY "YES" or "NO".
        """

        if not target_image_bytes:
            logger.info("Checkpoint 5 FAILED: igv_screenshot.png not found")
        else:
            async with EvaluationContext(
                task_tag=config.TASK_TAG,
                mode="custom",
                output_dir=None,
                target_path=target_file_path,
                reference_path=None
            ) as ctx:
                # 1) Verify this is IGV desktop (icon should be visible)
                igv_eval = await llm_vision_judge(
                    prompt=prompt_with_question(
                        "Does the first image clearly show the IGV desktop application is open?"
                    ),
                    image_bytes=target_image_bytes,
                    return_details=True,
                    max_tokens=10,
                    eval_context=ctx,
                    identifier=f"{file_name}_igv_app"
                )
                ctx.add_score(igv_eval["score"] * 0.1)

                # 2) Verify exact chromosome locus only if IGV desktop check passed
                if igv_eval["score"] >= 1.0:
                    locus_eval = await llm_vision_judge(
                        prompt=prompt_with_question(
                            "Is the chromosome position in the IGV app set near chr17:43,106,467-43,106,506? This can be seen near the top middle of the IGV application"
                        ),
                        image_bytes=target_image_bytes,
                        return_details=True,
                        max_tokens=10,
                        eval_context=ctx,
                        identifier=f"{file_name}_locus_check"
                    )
                    ctx.add_score(locus_eval["score"] * 0.1)
                else:
                    logger.info("Checkpoint 5 FAILED: IGV desktop app not detected; skipping locus check")

                ctx.finalize(file=f"{file_name}.png")
                score += ctx.total_score
                if ctx.total_score >= 0.2:
                    logger.info("Checkpoint 5 PASSED: IGV screenshot validated")
                else:
                    logger.info(f"Checkpoint 5 FAILED: partial IGV screenshot score={ctx.total_score:.2f}")

    except Exception as e:
        logger.error(f"Evaluation error: {e}")

    return [score]
