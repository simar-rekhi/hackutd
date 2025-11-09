#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-install + Topological Multipersistence Pipeline
"""

# -------------------- AUTO-INSTALL DEPENDENCIES --------------------
import sys
import subprocess

required = [
    "pandas",
    "numpy",
    "networkx",
    "scikit-learn",
    "openpyxl"   # for reading .xlsx files
]

# Try importing and install missing packages
for pkg in required:
    try:
        __import__(pkg)
    except ImportError:
        print(f"Installing missing package: {pkg}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

# -------------------------------------------------------------------

# Then continue with the rest of your pipeline
import pandas as pd
import numpy as np
import itertools
import argparse
import networkx as nx
from collections import defaultdict
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score
from typing import List, Dict, Tuple

# ----------------------------
# Utilities
# ----------------------------

def find_columns(df: pd.DataFrame, candidates: List[str]) -> List[str]:
    """Return list of first-matching columns preserving dataset case."""
    lower = {c.lower(): c for c in df.columns}
    return [lower[c] for c in candidates if c in lower]

def pick_id_column(df: pd.DataFrame) -> str:
    cand = find_columns(df, ["applicant_id", "entity_id", "id", "registration_number"])
    if cand:
        return cand[0]
    df["__row_id__"] = np.arange(len(df))
    return "__row_id__"

def map_label_to_binary(y_raw: pd.Series) -> np.ndarray:
    """
    Map labels to binary Fraud vs Non-Fraud.
    - If numeric -> 1 if > 0.5 else 0
    - If string -> "fraudulent"/"fraud"/"positive"/"hit" => 1 else 0
    """
    if y_raw.dtype.kind in "biufc":
        return (pd.to_numeric(y_raw, errors="coerce").fillna(0) > 0.5).astype(int).to_numpy()
    s = y_raw.astype(str).str.lower().str.strip()
    return s.isin(["fraudulent", "fraud", "positive", "hit"]).astype(int).to_numpy()

# ----------------------------
# Graph building
# ----------------------------

EDGE_FIELD_CANDS = [
    "contact_email","email","primary_email",
    "contact_phone","phone",
    "bank_swift_code","bank_swift",
    "bank_routing_number","routing_number",
    "tax_id_number","tax_id",
    "vat_gst_registration","vat_id","vat",
    "registered_address","operational_address","mailing_address","address",
    "bank_account_number_masked","iban","account_number_masked"
]

def build_graph(df: pd.DataFrame, app_id: str, edge_fields: List[str]) -> Tuple[nx.Graph, Dict[str, Dict]]:
    """
    Build an undirected graph:
      - Nodes: applicants
      - Edges: connect applicants sharing a value in any edge field
      - Weight: rarity-aware (1 / count of applicants sharing that value)
    Returns (G, inv_index per field)
    """
    G = nx.Graph()
    for aid in df[app_id].tolist():
        G.add_node(aid)

    inv = {f: {} for f in edge_fields}
    # Build inverted index: field -> value -> [applicants]
    for _, r in df.iterrows():
        for f in edge_fields:
            val = r.get(f, None)
            if pd.isna(val) or (isinstance(val, str) and val.strip() == ""):
                continue
            key = val.strip().lower() if isinstance(val, str) else val
            inv[f].setdefault(key, []).append(r[app_id])

    # Add rarity-weighted edges
    for f in edge_fields:
        for v, ids in inv[f].items():
            if len(ids) < 2:
                continue
            rarity = 1.0 / len(ids)
            for a, b in itertools.combinations(ids, 2):
                if G.has_edge(a, b):
                    G[a][b]["weight"] = max(G[a][b]["weight"], rarity)
                    G[a][b].setdefault("fields", set()).add(f)
                else:
                    G.add_edge(a, b, weight=rarity, fields={f})
    return G, inv

# ----------------------------
# f1, f2 definitions
# ----------------------------

def compute_f1_node(df: pd.DataFrame, app_id: str, G: nx.Graph, edge_fields: List[str], inv: Dict[str, Dict]) -> Dict:
    """
    f1 node scalar: reuse risk (max count across shared identifiers), normalized to [0,1]
    """
    node_reuse = {}
    for n in G.nodes():
        row = df.loc[df[app_id] == n]
        counts = []
        if len(row) == 1:
            rr = row.iloc[0]
            for f in edge_fields:
                val = rr.get(f, None)
                if pd.isna(val):
                    counts.append(0); continue
                key = val if not isinstance(val, str) else val.strip().lower()
                counts.append(len(inv[f].get(key, [])))
        else:
            counts.append(0)
        node_reuse[n] = max(counts) if counts else 0
    max_reuse = max(node_reuse.values()) if node_reuse else 1
    return {n: (node_reuse[n] / max(1, max_reuse)) for n in G.nodes()}

def pick_f2_column(df: pd.DataFrame) -> str:
    pref = find_columns(df, ["credit_score", "aml_risk_rating", "adverse_media_screen"])
    if pref:
        return pref[0]
    nums = df.select_dtypes(include=[np.number]).columns.tolist()
    if nums:
        return nums[0]
    df["__f2__"] = 0.0
    return "__f2__"

def scale_f2(df: pd.DataFrame, app_id: str, f2_col: str) -> Dict:
    """
    Robust scale f2 to [0,1] using 5th/95th percentiles.
    """
    arr = pd.to_numeric(df[f2_col], errors="coerce")
    if not np.isfinite(arr).any():
        arr = pd.Series(np.zeros(len(df)))
    v = arr.fillna(arr.median() if np.isfinite(arr).any() else 0.0).to_numpy()
    p5, p95 = np.nanpercentile(v, 5), np.nanpercentile(v, 95)
    rng = (p95 - p5) if p95 > p5 else 1.0
    scaled = np.clip((v - p5) / rng, 0, 1)
    return {aid: sc for aid, sc in zip(df[app_id], scaled)}

# ----------------------------
# Betti surfaces on 2-parameter grid
# ----------------------------

def betti_surfaces_for_subgraph(
    SG: nx.Graph,
    alphas: np.ndarray,
    betas: np.ndarray,
    f1_node: Dict,
    f2_node: Dict,
    f1_edge_fn,
    f2_edge_fn
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Approximate Betti-0 and Betti-1 on K x K grid for the 2-skeleton
    (flag/clique complex approximation using triangles to fill 1-cycles):
      beta0 = #connected_components
      beta1 ≈ E - V + beta0 - T
    """
    K = len(alphas)
    beta0 = np.zeros((K, K), dtype=float)
    beta1 = np.zeros((K, K), dtype=float)
    nodes = list(SG.nodes())

    for i, a in enumerate(alphas):
        for j, b in enumerate(betas):
            keep = [n for n in nodes if (f1_node.get(n, 0.0) <= a and f2_node.get(n, 0.0) <= b)]
            H = SG.subgraph(keep).copy()
            # prune edges above thresholds
            badE = [(u, v) for u, v in H.edges() if not (f1_edge_fn(u, v) <= a and f2_edge_fn(u, v) <= b)]
            H.remove_edges_from(badE)

            V = H.number_of_nodes()
            if V == 0:
                beta0[i, j] = 0.0
                beta1[i, j] = 0.0
                continue

            E = H.number_of_edges()
            comp = nx.number_connected_components(H)
            tri = int(sum(nx.triangles(H).values()) / 3)  # total triangles
            b0 = float(comp)
            b1 = float(E - V + comp - tri)
            if b1 < 0:
                b1 = 0.0  # guard for numerical/structural artifacts

            beta0[i, j] = b0
            beta1[i, j] = b1
    return beta0, beta1

def vectorize_surfaces(beta0: np.ndarray, beta1: np.ndarray) -> np.ndarray:
    feats = []
    for surf in (beta0, beta1):
        feats.append(surf.flatten())
        feats.append(np.array([surf.mean(), surf.std(), surf.max(), np.median(surf)]))
    return np.concatenate(feats)

def ego_features_for_applicant(
    G: nx.Graph,
    center,
    alphas: np.ndarray,
    betas: np.ndarray,
    f1_node: Dict,
    f2_node: Dict,
    f1_edge_fn,
    f2_edge_fn
) -> np.ndarray:
    nodes = {center} | set(G.neighbors(center))
    EG = G.subgraph(nodes).copy()
    b0, b1 = betti_surfaces_for_subgraph(EG, alphas, betas, f1_node, f2_node, f1_edge_fn, f2_edge_fn)
    return vectorize_surfaces(b0, b1)

# ----------------------------
# Model training & threshold selection
# ----------------------------

def optimize_thresholds(oof: np.ndarray, y: np.ndarray,
                        review_cap: float = 0.25,
                        fn_cost: float = 5.0, fp_cost: float = 1.0, review_cost: float = 0.5):
    """
    Grid search (theta_I, theta_F) with theta_F > theta_I to minimize cost
    under a review-rate cap. Returns best thresholds and stats.
    """
    best = {"cost": 1e9, "theta_I": 0.4, "theta_F": 0.8, "review_rate": 0.0}
    grid = np.linspace(0.05, 0.95, 37)
    for thI in grid:
        for thF in grid:
            if thF <= thI:
                continue
            tri = np.where(oof >= thF, "Fraud", np.where(oof >= thI, "Iffy", "Clear"))
            rr = np.mean(tri == "Iffy")
            if rr > review_cap:
                continue
            yhat = (oof >= thF).astype(int)
            FP = np.sum((yhat == 1) & (y == 0))
            FN = np.sum((yhat == 0) & (y == 1))
            REV = np.sum(tri == "Iffy")
            cost = fp_cost * FP + fn_cost * FN + review_cost * REV
            if cost < best["cost"]:
                best = {"cost": float(cost), "theta_I": float(thI), "theta_F": float(thF), "review_rate": float(rr)}
    return best

# ----------------------------
# Main
# ----------------------------

def main():
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_data = os.path.join(script_dir, "global_dataset.xlsx")
    default_out = os.path.join(script_dir, "onboarding_topo_pipeline_predictions_labeled.csv")
    
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default=default_data,
                    help="Path to labeled onboarding data (xlsx/csv)")
    ap.add_argument("--out", type=str, default=default_out,
                    help="Path to save predictions CSV")
    ap.add_argument("--grid", type=int, default=6, help="Grid size K for (alpha,beta)")
    ap.add_argument("--review_cap", type=float, default=0.25, help="Max review bucket share")
    ap.add_argument("--fn_cost", type=float, default=5.0)
    ap.add_argument("--fp_cost", type=float, default=1.0)
    ap.add_argument("--review_cost", type=float, default=0.5)
    args = ap.parse_args()

    # Load data
    if args.data.lower().endswith(".csv"):
        df = pd.read_csv(args.data)
    else:
        df = pd.read_excel(args.data)

    # Identify ID and label columns
    app_id = pick_id_column(df)

    # Prefer 'fraud_label' if present, else try common names
    label_col = None
    if "fraud_label" in df.columns:
        label_col = "fraud_label"
    else:
        for k in ["label", "is_fraud", "fraud_flag", "fraudulent", "class", "status", "target"]:
            if k in df.columns:
                label_col = k
                break
    if label_col is None:
        raise RuntimeError("No label column found. Include one of: fraud_label, label, is_fraud, fraud_flag, fraudulent, class, status, target.")

    y = map_label_to_binary(df[label_col])
    if len(np.unique(y)) < 2:
        raise RuntimeError("Label has a single class; need both Fraud and Non-Fraud examples.")

    # Edge fields (shared identifiers)
    edge_fields = [c for c in EDGE_FIELD_CANDS if c in df.columns]
    if not edge_fields:
        # fallback by substring
        edge_fields = [c for c in df.columns if any(k in c.lower() for k in ["email","phone","address","swift","routing","tax","vat","iban","account"])][:6]

    # Build graph
    G, inv = build_graph(df, app_id, edge_fields)

    # f1 (node reuse risk) and f1-edge (rarity weight)
    f1_node = compute_f1_node(df, app_id, G, edge_fields, inv)
    def f1_edge(u, v): return G[u][v].get("weight", 0.0)

    # f2 (identity/doc/credit proxy)
    f2_col = pick_f2_column(df)
    f2_node = scale_f2(df, app_id, f2_col)
    def f2_edge(u, v): return 0.5 * (f2_node.get(u, 0.0) + f2_node.get(v, 0.0))

    # Bi-filtration grid
    K = int(max(3, args.grid))
    alphas = np.linspace(0.0, 1.0, K)
    betas = np.linspace(0.0, 1.0, K)

    # Per-applicant ego features
    app_ids = df[app_id].tolist()
    X = np.vstack([
        ego_features_for_applicant(G, aid, alphas, betas, f1_node, f2_node, f1_edge, f2_edge)
        for aid in app_ids
    ])

    # Model: calibrated logistic regression
    pipe = Pipeline([
        ("imp", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=500))
    ])
    cal = CalibratedClassifierCV(pipe, cv=3, method="isotonic")

    # Out-of-fold probabilities for threshold selection
    n_neg = np.sum(y == 0)
    n_pos = np.sum(y == 1)
    n_splits = min(5, max(2, int(np.min([n_neg, n_pos]))))
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    oof = np.zeros(len(y), dtype=float)
    for tr, va in skf.split(X, y):
        cal.fit(X[tr], y[tr])
        oof[va] = cal.predict_proba(X[va])[:, 1]
    auc = roc_auc_score(y, oof)

    # Optimize thresholds with review cap / cost model
    best = optimize_thresholds(
        oof, y,
        review_cap=args.review_cap,
        fn_cost=args.fn_cost, fp_cost=args.fp_cost, review_cost=args.review_cost
    )
    theta_I, theta_F = best["theta_I"], best["theta_F"]

    # Final fit & predict
    cal.fit(X, y)
    proba = cal.predict_proba(X)[:, 1]

    def triage(p: float) -> str:
        if p >= theta_F: return "Fraud"
        if p >= theta_I: return "Iffy"
        return "Clear"

    tri = [triage(p) for p in proba]

    # Save predictions
    out = df[[app_id]].copy()
    out["risk_score"] = proba
    out["triage"] = tri
    out["label_true"] = df[label_col]
    out.to_csv(args.out, index=False)

    # Print summary
    summary = {
        "records": int(len(df)),
        "graph_nodes": int(G.number_of_nodes()),
        "graph_edges": int(G.number_of_edges()),
        "edge_fields_used": edge_fields,
        "f2_proxy_column": f2_col,
        "cv_auc": float(auc),
        "theta_I": float(theta_I),
        "theta_F": float(theta_F),
        "review_rate_cap": float(args.review_cap),
        "chosen_review_rate": float(best.get("review_rate", 0.0)),
        "cost": float(best.get("cost", np.nan))
    }
    print(pd.Series(summary).to_string())

if __name__ == "__main__":
    main()
