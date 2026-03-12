"""Single-cell RNA-seq Analysis Task - Bioinformatics Benchmark."""

import os
import logging
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from tasks.bioinformatics.Single_Cell_Analysis.eval import (
    parse_qc_stats,
    parse_cell_clusters,
    parse_marker_genes,
    validate_h5ad,
    compute_ari,
)
from utils.evaluation import llm_vision_judge, EvaluationContext

logger = logging.getLogger(__name__)


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "Single_Cell_Analysis"
    TASK_CATEGORY: str = "bioinformatics"
    OS_TYPE: str = "windows"
    CONDA_ENV: str = "wf3-env"

    # L1 thresholds
    MIN_CELLS_AFTER_QC: int = 2000
    MAX_CELLS_AFTER_QC: int = 2700
    MIN_CLUSTERS: int = 6
    MAX_CLUSTERS: int = 10
    MIN_MARKER_GENES_PER_CLUSTER: int = 6

    # L2 thresholds
    ARI_FULL_CREDIT: float = 0.75
    ARI_PARTIAL_CREDIT: float = 0.60

    # Output filenames
    QC_STATS_FILE: str = "qc_stats.txt"
    CELL_CLUSTERS_FILE: str = "cell_clusters.csv"
    MARKER_GENES_FILE: str = "marker_genes.csv"
    UMAP_PLOT_FILE: str = "umap_plot.png"
    H5AD_FILE: str = "results.h5ad"

    # Eval data (not given to agent)
    REFERENCE_LABELS_FILE: str = "reference_labels.csv"

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
        return f"""You are given a single-cell RNA-seq count matrix from 10x Genomics (PBMC dataset) in standard 10x \
        matrix market format.

        Your task is to perform a complete single-cell RNA-seq analysis, producing cell cluster assignments, marker genes \
        for each cluster, and a UMAP visualization.

        Existing File Structure:
        {self.wsl_task_dir}/
        ├── input/
        │   ├── barcodes.tsv                   # Cell barcodes
        │   ├── genes.tsv                      # Gene names and IDs
        │   └── matrix.mtx                     # Sparse count matrix (cells × genes)
        └── output/
            ├── {self.CELL_CLUSTERS_FILE}      # Save cluster assignments here (header pre-created)
            └── {self.MARKER_GENES_FILE}       # Save marker genes here (header pre-created)

        Environment:
        - An Ubuntu (WSL) terminal is already open at {self.wsl_task_dir}
        - Conda environment `{self.CONDA_ENV}` is pre-activated with: Python3, scanpy, leidenalg, pandas, numpy, matplotlib installed

        Save the following files to the output directory:
        - {self.wsl_output_dir}/{self.QC_STATS_FILE} — Two lines in exact format:
        Before filtering: <N> cells, <N> genes
        After filtering: <N> cells, <N> genes
        - {self.wsl_output_dir}/{self.CELL_CLUSTERS_FILE} — Append cluster assignments to the pre-existing CSV. \
        Don't modify the header.
        - {self.wsl_output_dir}/{self.MARKER_GENES_FILE} — Append top marker genes per cluster to the pre-existing CSV. \
        Don't modify the header.
        - {self.wsl_output_dir}/{self.UMAP_PLOT_FILE} — UMAP plot colored by cluster labels
        - {self.wsl_output_dir}/{self.H5AD_FILE} — Full AnnData object with all results

        Do not ask for confirmation. Execute each step directly.
        """

    def to_metadata(self) -> dict:
        metadata = super().to_metadata()
        metadata.update({
            "wsl_task_dir": self.wsl_task_dir,
            "wsl_output_dir": self.wsl_output_dir,
            "wsl_input_dir": self.wsl_input_dir,
            "wsl_eval_dir": self.wsl_eval_dir,
            "min_cells_after_qc": self.MIN_CELLS_AFTER_QC,
            "max_cells_after_qc": self.MAX_CELLS_AFTER_QC,
            "min_clusters": self.MIN_CLUSTERS,
            "max_clusters": self.MAX_CLUSTERS,
            "min_marker_genes_per_cluster": self.MIN_MARKER_GENES_PER_CLUSTER,
            "ari_full_credit": self.ARI_FULL_CREDIT,
            "ari_partial_credit": self.ARI_PARTIAL_CREDIT,
        })
        return metadata


config = TaskConfig()


@cb.tasks_config(split="train")
def load():
    """Define the single-cell RNA-seq analysis task."""
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

        # Pre-create cell_clusters.csv with header
        clusters_path = os.path.join(output_dir, config.CELL_CLUSTERS_FILE)
        await session.run_command(
            f'powershell -Command "Set-Content -Path \'{clusters_path}\' -Value \'barcode,cluster\'"'
        )

        # Pre-create marker_genes.csv with header
        markers_path = os.path.join(output_dir, config.MARKER_GENES_FILE)
        await session.run_command(
            f'powershell -Command "Set-Content -Path \'{markers_path}\' -Value \'cluster,gene,score,pval_adj\'"'
        )

        # Ensure conda auto-activates in WSL
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
    """Score the task based on checkpoint files (L1), ARI (L2a), and VLM (L2b)."""

    output_dir = task_cfg.metadata["remote_output_dir"]
    base_dir = os.path.dirname(output_dir)
    eval_dir = os.path.join(base_dir, "eval_data")
    score = 0.0

    # ══════════════════════════════════════════════
    # L1: Automated Rule Checks (weight: 0.50)
    # ══════════════════════════════════════════════

    # ── Checkpoint 0: QC Stats (weight: 0.10) ──
    try:
        qc_path = os.path.join(output_dir, config.QC_STATS_FILE)
        qc_bytes = await session.read_bytes(qc_path)
        if qc_bytes:
            qc_parsed = parse_qc_stats(qc_bytes.decode())
            if qc_parsed:
                after_cells = qc_parsed["after_cells"]
                filtering_happened = qc_parsed["after_cells"] < qc_parsed["before_cells"]
                cells_reasonable = (
                    task_cfg.metadata["min_cells_after_qc"]
                    <= after_cells
                    <= task_cfg.metadata["max_cells_after_qc"]
                )

                if filtering_happened and cells_reasonable:
                    score += 0.10
                    logger.info(
                        f"Checkpoint 0 PASSED: QC stats valid "
                        f"({qc_parsed['before_cells']} -> {after_cells} cells)"
                    )
                else:
                    logger.info(
                        f"Checkpoint 0 FAILED: filtering={filtering_happened}, "
                        f"cells_reasonable={cells_reasonable} ({after_cells} cells)"
                    )
            else:
                logger.info("Checkpoint 0 FAILED: could not parse qc_stats.txt")
        else:
            logger.info("Checkpoint 0 FAILED: qc_stats.txt not found")
    except Exception as e:
        logger.info(f"Checkpoint 0 FAILED: {e}")

    # ── Checkpoint 1: Cell Clusters (weight: 0.10) ──
    agent_clusters = None
    try:
        clusters_path = os.path.join(output_dir, config.CELL_CLUSTERS_FILE)
        clusters_bytes = await session.read_bytes(clusters_path)
        if clusters_bytes:
            clusters_parsed = parse_cell_clusters(clusters_bytes.decode())
            if clusters_parsed:
                n_cells = clusters_parsed["num_cells"]
                n_clusters = clusters_parsed["num_clusters"]

                cells_ok = task_cfg.metadata["min_cells_after_qc"] <= n_cells <= task_cfg.metadata["max_cells_after_qc"]
                clusters_ok = task_cfg.metadata["min_clusters"] <= n_clusters <= task_cfg.metadata["max_clusters"]

                if cells_ok and clusters_ok:
                    score += 0.10
                    agent_clusters = clusters_parsed["data"]
                    logger.info(f"Checkpoint 1 PASSED: {n_cells} cells, {n_clusters} clusters")
                else:
                    logger.info(
                        f"Checkpoint 1 FAILED: cells_ok={cells_ok} ({n_cells}), "
                        f"clusters_ok={clusters_ok} ({n_clusters})"
                    )
            else:
                logger.info("Checkpoint 1 FAILED: could not parse cell_clusters.csv")
        else:
            logger.info("Checkpoint 1 FAILED: cell_clusters.csv not found")
    except Exception as e:
        logger.info(f"Checkpoint 1 FAILED: {e}")

    # ── Checkpoint 2: Marker Genes (weight: 0.10) ──
    try:
        markers_path = os.path.join(output_dir, config.MARKER_GENES_FILE)
        markers_bytes = await session.read_bytes(markers_path)
        if markers_bytes:
            markers_parsed = parse_marker_genes(markers_bytes.decode())
            if markers_parsed:
                n_clusters = markers_parsed["num_clusters"]
                genes_per = markers_parsed["genes_per_cluster"]

                clusters_ok = task_cfg.metadata["min_clusters"] <= n_clusters <= task_cfg.metadata["max_clusters"]
                genes_ok = genes_per >= task_cfg.metadata["min_marker_genes_per_cluster"]

                if clusters_ok and genes_ok:
                    score += 0.10
                    logger.info(
                        f"Checkpoint 2 PASSED: {markers_parsed['num_rows']} markers "
                        f"across {n_clusters} clusters ({genes_per:.1f} per cluster)"
                    )
                else:
                    logger.info(
                        f"Checkpoint 2 FAILED: clusters_ok={clusters_ok} ({n_clusters}), "
                        f"genes_ok={genes_ok} ({genes_per:.1f} per cluster)"
                    )
            else:
                logger.info("Checkpoint 2 FAILED: could not parse marker_genes.csv")
        else:
            logger.info("Checkpoint 2 FAILED: marker_genes.csv not found")
    except Exception as e:
        logger.info(f"Checkpoint 2 FAILED: {e}")

    # ── Checkpoint 3: H5AD File (weight: 0.20) ──
    try:
        h5ad_path = os.path.join(output_dir, config.H5AD_FILE)
        h5ad_bytes = await session.read_bytes(h5ad_path)
        if h5ad_bytes:
            h5ad_parsed = validate_h5ad(h5ad_bytes)
            if h5ad_parsed:
                has_all = h5ad_parsed["has_pca"] and h5ad_parsed["has_umap"] and h5ad_parsed["has_clustering"]
                cells_ok = h5ad_parsed["num_cells"] >= task_cfg.metadata["min_cells_after_qc"]

                if has_all and cells_ok:
                    score += 0.20
                    logger.info(
                        f"Checkpoint 3 PASSED: h5ad valid "
                        f"({h5ad_parsed['num_cells']} cells, "
                        f"pca={h5ad_parsed['has_pca']}, umap={h5ad_parsed['has_umap']}, "
                        f"clustering={h5ad_parsed['has_clustering']})"
                    )
                else:
                    logger.info(
                        f"Checkpoint 3 FAILED: cells={h5ad_parsed['num_cells']}, "
                        f"pca={h5ad_parsed['has_pca']}, umap={h5ad_parsed['has_umap']}, "
                        f"clustering={h5ad_parsed['has_clustering']}"
                    )
            else:
                logger.info("Checkpoint 3 FAILED: could not load h5ad")
        else:
            logger.info("Checkpoint 3 FAILED: results.h5ad not found")
    except Exception as e:
        logger.info(f"Checkpoint 3 FAILED: {e}")

    # ══════════════════════════════════════════════
    # L2a: ARI Evaluation (weight: 0.30)
    # ══════════════════════════════════════════════

    if agent_clusters is not None:
        try:
            ref_path = os.path.join(eval_dir, config.REFERENCE_LABELS_FILE)
            ref_bytes = await session.read_bytes(ref_path)

            if ref_bytes:

                ari_results = compute_ari(agent_clusters, ref_bytes)
                ari = ari_results["ari"]
                matched = ari_results["matched_cells"]

                logger.info(
                    f"L2a results: ARI={ari}, matched_cells={matched}, "
                    f"agent_cells={ari_results['total_agent_cells']}, "
                    f"ref_cells={ari_results['total_ref_cells']}"
                )

                if ari is not None and ari >= task_cfg.metadata["ari_full_credit"]:
                    score += 0.30
                    logger.info(f"L2a PASSED: ARI = {ari:.4f}")
                elif ari is not None and ari >= task_cfg.metadata["ari_partial_credit"]:
                    score += 0.15
                    logger.info(f"L2a PARTIAL: ARI = {ari:.4f}")
                else:
                    logger.info(f"L2a FAILED: ARI = {ari}")
            else:
                logger.info("L2a SKIPPED: reference_labels.csv not found")

        except Exception as e:
            logger.info(f"L2a FAILED: {e}")
    else:
        logger.info("L2a SKIPPED: cell_clusters.csv not available")

    # ══════════════════════════════════════════════
    # L2b: VLM UMAP Evaluation (weight: 0.20)
    # ══════════════════════════════════════════════

    umap_bytes = None
    try:
        umap_path = os.path.join(output_dir, config.UMAP_PLOT_FILE)
        umap_bytes = await session.read_bytes(umap_path)
    except Exception:
        pass

    if umap_bytes and len(umap_bytes) > 1000:
        try:
            async with EvaluationContext(
                task_tag=config.TASK_TAG,
                mode="custom",
                output_dir=None,
                target_path=os.path.join(output_dir, config.UMAP_PLOT_FILE),
                reference_path=None,
            ) as ctx:
                separation_eval = await llm_vision_judge(
                    prompt="""You are evaluating a UMAP plot from a single-cell RNA-seq analysis.

                    1. First image: UMAP plot generated by the agent

                    Question: Does this UMAP plot use multiple different colors to distinguish cell clusters, 
                    and do the colored clusters appear seperated. It's ok if clusters appear to be touching each other, as long as they don't intermix.

                    Answer with ONLY "YES" or "NO".""",

                    image_bytes=umap_bytes,
                    return_details=True,
                    max_tokens=10,
                    eval_context=ctx,
                    identifier="umap_separation",
                )
                ctx.add_score(separation_eval["score"] * 0.20)
                ctx.finalize(file="umap_plot.png")
                score += ctx.total_score

                if ctx.total_score >= 0.15:
                    logger.info(f"L2b PASSED: UMAP separation score={ctx.total_score:.2f}")
                else:
                    logger.info(f"L2b FAILED: UMAP separation score={ctx.total_score:.2f}")

        except Exception as e:
            logger.info(f"L2b FAILED: {e}")
    else:
        logger.info("L2b SKIPPED: UMAP plot not available")

    logger.info(f"Final score: {score:.2f}")
    return [score]