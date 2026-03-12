"""Evaluation helpers for RNA-seq Differential Expression benchmark."""

import re
import csv
import io
import math
import logging
import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

logger = logging.getLogger(__name__)


# ── L1: Parsing checkpoint files ──

def parse_star_log(log_text: str) -> float | None:
    """Extract uniquely mapped reads % from STAR Log.final.out."""
    for line in log_text.split("\n"):
        if "Uniquely mapped reads %" in line:
            match = re.search(r'([\d.]+)%', line)
            if match:
                return float(match.group(1))
    return None


def parse_featurecounts_summary(summary_text: str) -> dict | None:
    """Parse featureCounts summary file to extract assignment rates."""
    lines = summary_text.strip().split("\n")
    if len(lines) < 2:
        return None

    num_samples = len(lines[0].split("\t")) - 1
    assigned = [0] * num_samples
    total = [0] * num_samples

    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < num_samples + 1:
            continue
        for i, p in enumerate(parts[1:]):
            try:
                count = int(p)
            except ValueError:
                count = 0
            total[i] += count
            if parts[0] == "Assigned":
                assigned[i] = count

    if not any(t > 0 for t in total):
        return None

    rates = [(a / t * 100) if t > 0 else 0.0 for a, t in zip(assigned, total)]
    return {"assignment_rates": rates, "min_rate": min(rates) if rates else 0.0}


def parse_gene_counts(counts_text: str) -> dict | None:
    """Parse featureCounts gene count matrix."""
    lines = counts_text.strip().split("\n")
    if len(lines) < 3:
        return None

    header_idx = next(i for i, line in enumerate(lines) if not line.startswith("#"))
    headers = lines[header_idx].split("\t")
    num_samples = len(headers) - 6
    if num_samples < 1:
        return None

    genes_with_counts = 0
    num_genes = 0

    for line in lines[header_idx + 1:]:
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        num_genes += 1
        try:
            if sum(int(p) for p in parts[6:]) > 0:
                genes_with_counts += 1
        except ValueError:
            continue

    return {"num_genes": num_genes, "num_samples": num_samples, "genes_with_counts": genes_with_counts}


def parse_deseq2_results(results_text: str) -> dict | None:
    """Parse DESeq2 results CSV."""
    try:
        reader = csv.DictReader(io.StringIO(results_text))
        required_cols = {"gene_id", "log2FoldChange", "pvalue", "padj"}
        has_required = required_cols.issubset(set(reader.fieldnames)) if reader.fieldnames else False

        rows = []
        rows_with_padj = 0
        for row in reader:
            rows.append(row)
            padj = row.get("padj", "NA")
            if padj and padj not in ("NA", ""):
                try:
                    float(padj)
                    rows_with_padj += 1
                except ValueError:
                    pass

        return {"num_rows": len(rows), "rows_with_padj": rows_with_padj,
                "has_required_columns": has_required, "data": rows}
    except Exception:
        return None


# ── L2: qPCR evaluation ──

def build_ensembl_to_symbol_map(gtf_text: str) -> dict:
    """Parse GTF to build Ensembl gene ID -> gene symbol mapping."""
    id_map = {}
    for line in gtf_text.split("\n"):
        if line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 9 or parts[2] != "gene":
            continue
        gene_id = re.search(r'gene_id "([^"]+)"', parts[8])
        gene_name = re.search(r'gene_name "([^"]+)"', parts[8])
        if gene_id and gene_name:
            id_map[gene_id.group(1)] = gene_name.group(1)
    return id_map


def parse_taqman_truth(truth_text: str) -> dict:
    """Parse taqman_truth.csv into dict of symbol -> log2FC."""
    truth = {}
    for row in csv.DictReader(io.StringIO(truth_text)):
        symbol = row.get("Symbol", "").strip()
        try:
            truth[symbol] = float(row.get("log2FC", ""))
        except (ValueError, TypeError):
            continue
    return truth


def run_l2_evaluation(
    deseq2_data: list[dict],
    gtf_text: str,
    taqman_truth: dict,
    qpcr_log2fc_threshold: float = 1.0,
) -> dict:
    """Run L2 evaluation: match DESeq2 results to qPCR truth, compute metrics."""
    id_map = build_ensembl_to_symbol_map(gtf_text)

    rnaseq_fc, qpcr_fc, padj_scores, qpcr_truly_de = [], [], [], []

    for row in deseq2_data:
        gene_id = row.get("gene_id", "")
        log2fc_str = row.get("log2FoldChange", "")
        padj_str = row.get("padj", "")

        if not log2fc_str or log2fc_str == "NA" or not padj_str or padj_str == "NA":
            continue
        try:
            rnaseq_log2fc = float(log2fc_str)
            padj = float(padj_str)
        except ValueError:
            continue

        symbol = id_map.get(gene_id, "")
        if not symbol or symbol not in taqman_truth:
            continue

        qpcr_log2fc = taqman_truth[symbol]
        rnaseq_fc.append(rnaseq_log2fc)
        qpcr_fc.append(qpcr_log2fc)
        padj_scores.append(-math.log10(padj) if padj > 0 else 300)
        qpcr_truly_de.append(abs(qpcr_log2fc) > qpcr_log2fc_threshold)

    results = {"matched_genes": len(rnaseq_fc), "spearman_rho": None,
               "direction_consistency": None, "auc": None}

    if len(rnaseq_fc) < 3:
        logger.info(f"L2: Only {len(rnaseq_fc)} matched genes — insufficient")
        return results

    # Spearman correlation
    rho, _ = spearmanr(rnaseq_fc, qpcr_fc)
    results["spearman_rho"] = rho

    # Direction consistency
    r = np.array(rnaseq_fc)
    q = np.array(qpcr_fc)
    mask = (r != 0) & (q != 0)
    if mask.any():
        results["direction_consistency"] = float(np.mean(np.sign(r[mask]) == np.sign(q[mask])))

    # AUC
    if len(set(qpcr_truly_de)) == 2:  # Need both classes
        results["auc"] = roc_auc_score(qpcr_truly_de, padj_scores)

    return results