"""Evaluation helpers for Single-cell RNA-seq Analysis benchmark."""

import re
import csv
import io
import logging
import pandas as pd
import anndata
from sklearn.metrics import adjusted_rand_score
import tempfile
import os

logger = logging.getLogger(__name__)


# ── L1: Parsing checkpoint files ──

def parse_qc_stats(qc_text: str) -> dict | None:
    """Parse qc_stats.txt to extract cell/gene counts before and after filtering.

    Expected format:
        Before filtering: 2700 cells, 32738 genes
        After filtering: 2638 cells, 13656 genes
    """
    result = {}
    for line in qc_text.strip().split("\n"):
        before_match = re.match(r'Before filtering:\s*(\d+)\s*cells?,\s*(\d+)\s*genes?', line, re.IGNORECASE)
        after_match = re.match(r'After filtering:\s*(\d+)\s*cells?,\s*(\d+)\s*genes?', line, re.IGNORECASE)

        if before_match:
            result["before_cells"] = int(before_match.group(1))
            result["before_genes"] = int(before_match.group(2))
        elif after_match:
            result["after_cells"] = int(after_match.group(1))
            result["after_genes"] = int(after_match.group(2))

    return result if len(result) == 4 else None


def parse_cell_clusters(clusters_text: str) -> dict | None:
    """Parse cell_clusters.csv. Expected columns: barcode, cluster."""
    try:
        reader = csv.DictReader(io.StringIO(clusters_text))
        if not reader.fieldnames or not {"barcode", "cluster"}.issubset(set(reader.fieldnames)):
            return None

        rows = list(reader)
        if not rows:
            return None

        df = pd.DataFrame(rows)
        return {
            "num_cells": len(df),
            "num_clusters": df["cluster"].nunique(),
            "data": df,
        }
    except Exception:
        return None


def parse_marker_genes(marker_text: str) -> dict | None:
    """Parse marker_genes.csv. Expected columns: cluster, gene, score, pval_adj."""
    try:
        reader = csv.DictReader(io.StringIO(marker_text))
        if not reader.fieldnames or not {"cluster", "gene"}.issubset(set(reader.fieldnames)):
            return None

        rows = list(reader)
        if not rows:
            return None

        clusters = set(r["cluster"] for r in rows)
        genes_per_cluster = len(rows) / max(len(clusters), 1)

        return {
            "num_rows": len(rows),
            "num_clusters": len(clusters),
            "genes_per_cluster": genes_per_cluster,
            "data": rows,
        }
    except Exception:
        return None


def validate_h5ad(h5ad_bytes: bytes) -> dict | None:
    """Validate results.h5ad by loading and checking expected keys."""

    tmp_path = None
    
    try:
        with tempfile.NamedTemporaryFile(suffix=".h5ad", delete=False) as f:
            f.write(h5ad_bytes)
            tmp_path = f.name

        adata = anndata.read_h5ad(tmp_path)

        return {
            "num_cells": adata.shape[0],
            "num_genes": adata.shape[1],
            "has_pca": "X_pca" in adata.obsm,
            "has_umap": "X_umap" in adata.obsm,
            "has_clustering": "leiden" in adata.obs or any("leiden" in k for k in adata.obs.columns),
        }
    except Exception as e:
        logger.info(f"Failed to validate h5ad: {e}")
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# ── L2: ARI evaluation ──

def compute_ari(agent_clusters: pd.DataFrame, ref_bytes: bytes) -> dict:
    """Compute ARI between agent's clustering and reference labels."""
    result = {
        "ari": None,
        "matched_cells": 0,
        "total_agent_cells": len(agent_clusters),
        "total_ref_cells": 0,
    }

    try:
        ref = pd.read_csv(io.BytesIO(ref_bytes), index_col=0)
        result["total_ref_cells"] = len(ref)

        agent = agent_clusters.set_index("barcode") if "barcode" in agent_clusters.columns else agent_clusters
        common = ref.index.intersection(agent.index)
        result["matched_cells"] = len(common)

        if len(common) < 100:
            logger.info(f"ARI: Only {len(common)} matched barcodes — insufficient")
            return result

        ref_labels = ref.loc[common, "leiden"].astype(str).values
        agent_labels = agent.loc[common, "cluster"].astype(str).values
        result["ari"] = adjusted_rand_score(ref_labels, agent_labels)

    except Exception as e:
        logger.info(f"ARI computation failed: {e}")

    return result