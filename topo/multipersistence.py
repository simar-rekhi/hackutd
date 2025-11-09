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
from typing import List, Dict, Tuple, Optional, Any, Union
import pickle
import os
import json
import uuid

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
# Model persistence & inference
# ----------------------------

def save_model_artifacts(
    model: CalibratedClassifierCV,
    G: nx.Graph,
    inv: Dict[str, Dict],
    f1_node: Dict,
    f2_node: Dict,
    edge_fields: List[str],
    f2_col: str,
    alphas: np.ndarray,
    betas: np.ndarray,
    theta_I: float,
    theta_F: float,
    app_id: str,
    save_path: str
):
    """
    Save all artifacts needed for inference on new clients.
    Note: f1_edge_fn and f2_edge_fn are not saved as they can be reconstructed from G and f2_node.
    """
    artifacts = {
        "model": model,
        "graph": G,
        "inv_index": inv,
        "f1_node": f1_node,
        "f2_node": f2_node,
        "edge_fields": edge_fields,
        "f2_col": f2_col,
        "alphas": alphas,
        "betas": betas,
        "theta_I": theta_I,
        "theta_F": theta_F,
        "app_id": app_id,
        "f2_scaler_params": None  # Will store scaling params for f2
    }
    
    # Extract f2 scaling parameters if available
    if hasattr(f2_node, 'get') and len(f2_node) > 0:
        f2_values = list(f2_node.values())
        if len(f2_values) > 0:
            arr = np.array(f2_values)
            p5, p95 = np.nanpercentile(arr, 5), np.nanpercentile(arr, 95)
            artifacts["f2_scaler_params"] = {"p5": float(p5), "p95": float(p95)}
    
    os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
    with open(save_path, "wb") as f:
        pickle.dump(artifacts, f)
    print(f"Model artifacts saved to {save_path}")

def load_model_artifacts(load_path: str) -> Dict[str, Any]:
    """
    Load saved model artifacts for inference.
    """
    with open(load_path, "rb") as f:
        artifacts = pickle.load(f)
    return artifacts

def add_client_to_graph(
    G: nx.Graph,
    inv: Dict[str, Dict],
    client_id: str,
    client_data: Dict[str, Any],
    edge_fields: List[str]
) -> Tuple[nx.Graph, Dict[str, Dict]]:
    """
    Add a new client to the existing graph and update inverted index.
    Returns updated (G, inv).
    """
    G_new = G.copy()
    inv_new = {f: {k: v.copy() for k, v in inv[f].items()} for f in inv}
    
    # Add node
    G_new.add_node(client_id)
    
    # Update inverted index and add edges
    for f in edge_fields:
        val = client_data.get(f, None)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            continue
        if pd.isna(val):
            continue
            
        key = val.strip().lower() if isinstance(val, str) else val
        
        # Add to inverted index
        if key not in inv_new[f]:
            inv_new[f][key] = []
        inv_new[f][key].append(client_id)
        
        # Add edges to existing nodes sharing this value
        existing_ids = inv.get(f, {}).get(key, [])
        for existing_id in existing_ids:
            if existing_id != client_id:
                rarity = 1.0 / len(inv_new[f][key])
                if G_new.has_edge(client_id, existing_id):
                    G_new[client_id][existing_id]["weight"] = max(
                        G_new[client_id][existing_id]["weight"], rarity
                    )
                    G_new[client_id][existing_id].setdefault("fields", set()).add(f)
                else:
                    G_new.add_edge(client_id, existing_id, weight=rarity, fields={f})
    
    return G_new, inv_new

def compute_f1_for_new_client(
    client_id: str,
    client_data: Dict[str, Any],
    edge_fields: List[str],
    inv: Dict[str, Dict],
    max_reuse: float = 1.0
) -> float:
    """
    Compute f1 (reuse risk) for a new client.
    """
    counts = []
    for f in edge_fields:
        val = client_data.get(f, None)
        if val is None or pd.isna(val):
            counts.append(0)
            continue
        key = val.strip().lower() if isinstance(val, str) else val
        count = len(inv.get(f, {}).get(key, []))
        counts.append(count)
    
    max_count = max(counts) if counts else 0
    return (max_count / max(1.0, max_reuse)) if max_reuse > 0 else 0.0

def scale_f2_for_new_client(
    client_data: Dict[str, Any],
    f2_col: str,
    scaler_params: Optional[Dict[str, float]] = None
) -> float:
    """
    Scale f2 value for a new client using saved scaling parameters.
    """
    val = client_data.get(f2_col, 0.0)
    arr = pd.to_numeric([val], errors="coerce")[0]
    
    if not np.isfinite(arr):
        arr = 0.0
    
    if scaler_params:
        p5 = scaler_params.get("p5", 0.0)
        p95 = scaler_params.get("p95", 1.0)
        rng = (p95 - p5) if p95 > p5 else 1.0
        scaled = np.clip((arr - p5) / rng, 0, 1)
    else:
        scaled = float(np.clip(arr, 0, 1))
    
    return scaled

class ClientValidator:
    """
    Class to validate/flag new clients using trained model and graph.
    """
    
    def __init__(self, artifacts_path: str):
        """
        Load model artifacts from file.
        """
        self.artifacts = load_model_artifacts(artifacts_path)
        self.model = self.artifacts["model"]
        self.G = self.artifacts["graph"]
        self.inv = self.artifacts["inv_index"]
        self.f1_node = self.artifacts["f1_node"]
        self.f2_node = self.artifacts["f2_node"]
        # Reconstruct edge functions from graph and f2_node
        def f1_edge_recon(u, v):
            if self.G.has_edge(u, v):
                return self.G[u][v].get("weight", 0.0)
            return 0.0
        def f2_edge_recon(u, v):
            f2_u = self.f2_node.get(u, 0.0)
            f2_v = self.f2_node.get(v, 0.0)
            return 0.5 * (f2_u + f2_v)
        self.f1_edge_fn = f1_edge_recon
        self.f2_edge_fn = f2_edge_recon
        self.edge_fields = self.artifacts["edge_fields"]
        self.f2_col = self.artifacts["f2_col"]
        self.alphas = self.artifacts["alphas"]
        self.betas = self.artifacts["betas"]
        self.theta_I = self.artifacts["theta_I"]
        self.theta_F = self.artifacts["theta_F"]
        self.app_id = self.artifacts.get("app_id", "applicant_id")
        self.f2_scaler_params = self.artifacts.get("f2_scaler_params")
        
        # Compute max_reuse for f1 normalization
        if self.f1_node:
            self.max_reuse = max(self.f1_node.values()) if self.f1_node.values() else 1.0
        else:
            self.max_reuse = 1.0
    
    def validate_client(
        self,
        client_id: str,
        client_data: Dict[str, Any],
        return_details: bool = False
    ) -> Dict[str, Any]:
        """
        Validate a new client using limited parameters.
        
        Args:
            client_id: Unique identifier for the client
            client_data: Dictionary with client parameters (email, phone, address, etc.)
            return_details: If True, return detailed risk information
        
        Returns:
            Dictionary with:
                - status: "Validated" or "Flagged"
                - risk_score: Probability of fraud (0-1)
                - triage: "Clear", "Iffy", or "Fraud"
                - connections: Number of connections in graph (if return_details)
        """
        # Add client to graph temporarily
        G_temp, inv_temp = add_client_to_graph(
            self.G, self.inv, client_id, client_data, self.edge_fields
        )
        
        # Compute f1 and f2 for new client
        f1_new = compute_f1_for_new_client(
            client_id, client_data, self.edge_fields, inv_temp, self.max_reuse
        )
        f2_new = scale_f2_for_new_client(
            client_data, self.f2_col, self.f2_scaler_params
        )
        
        # Update f1_node and f2_node temporarily
        f1_node_temp = self.f1_node.copy()
        f1_node_temp[client_id] = f1_new
        f2_node_temp = self.f2_node.copy()
        f2_node_temp[client_id] = f2_new
        
        # Create edge functions that handle new client
        def f1_edge_temp(u, v):
            if u == client_id or v == client_id:
                # For edges involving new client, compute weight on the fly
                if G_temp.has_edge(u, v):
                    return G_temp[u][v].get("weight", 0.0)
                return 0.0
            return self.f1_edge_fn(u, v)
        
        def f2_edge_temp(u, v):
            f2_u = f2_node_temp.get(u, 0.0)
            f2_v = f2_node_temp.get(v, 0.0)
            return 0.5 * (f2_u + f2_v)
        
        # Extract topological features
        try:
            features = ego_features_for_applicant(
                G_temp, client_id, self.alphas, self.betas,
                f1_node_temp, f2_node_temp, f1_edge_temp, f2_edge_temp
            )
        except Exception as e:
            # If feature extraction fails, use zero features
            print(f"Warning: Feature extraction failed for {client_id}: {e}")
            features = np.zeros(self.alphas.shape[0] * self.betas.shape[0] * 2 + 8)
        
        # Predict
        features_2d = features.reshape(1, -1)
        proba = self.model.predict_proba(features_2d)[0, 1]
        
        # Triage
        if proba >= self.theta_F:
            triage = "Fraud"
            status = "Flagged"
        elif proba >= self.theta_I:
            triage = "Iffy"
            status = "Flagged"
        else:
            triage = "Clear"
            status = "Validated"
        
        result = {
            "status": status,
            "risk_score": float(proba),
            "triage": triage
        }
        
        if return_details:
            connections = G_temp.degree(client_id)
            result["connections"] = int(connections)
            result["f1_reuse_risk"] = float(f1_new)
            result["f2_proxy"] = float(f2_new)
        
        return result

# ----------------------------
# JSON-based validation functions
# ----------------------------

def validate_client_from_json(
    json_input: Union[str, Dict[str, Any]],
    model_path: Optional[str] = None,
    validator: Optional[ClientValidator] = None,
    return_details: bool = True
) -> Dict[str, Any]:
    """
    Validate a client from JSON input.
    
    Args:
        json_input: Can be:
            - Path to a JSON file (str)
            - JSON string (str)
            - Dictionary/JSON object (dict)
        model_path: Path to model artifacts file (required if validator not provided)
        validator: Pre-initialized ClientValidator instance (optional, overrides model_path)
        return_details: If True, return detailed risk information
    
    Returns:
        Dictionary with validation results:
            - status: "Validated" or "Flagged"
            - risk_score: Probability of fraud (0-1)
            - triage: "Clear", "Iffy", or "Fraud"
            - client_id: The client identifier used
            - connections: Number of connections in graph (if return_details)
            - f1_reuse_risk: Reuse risk score (if return_details)
            - f2_proxy: F2 proxy value (if return_details)
    
    Example JSON format:
        {
            "client_data_id": "unique-id",
            "structured_data": {
                "contact_email": "email@example.com",
                "contact_phone": "555-1234",
                "registered_address": "123 Main St",
                ...
            }
        }
    """
    # Parse JSON input
    if isinstance(json_input, dict):
        json_data = json_input
    elif isinstance(json_input, str):
        # Check if it's a file path
        if os.path.isfile(json_input):
            with open(json_input, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        else:
            # Assume it's a JSON string
            json_data = json.loads(json_input)
    else:
        raise ValueError(f"json_input must be a dict, file path (str), or JSON string (str), got {type(json_input)}")
    
    # Extract client_id and structured_data
    client_id = json_data.get("client_data_id") or json_data.get("client_id") or json_data.get("id")
    if not client_id:
        # Generate a unique ID if not provided
        client_id = str(uuid.uuid4())
    
    structured_data = json_data.get("structured_data", {})
    if not structured_data:
        # If structured_data is not present, use the entire json_data as client_data
        # (excluding metadata fields)
        structured_data = {k: v for k, v in json_data.items() 
                          if k not in ["client_data_id", "client_id", "id", "created_at", "updated_at", "filename"]}
    
    # Filter out None values from structured_data
    client_data = {k: v for k, v in structured_data.items() if v is not None}
    
    # Initialize validator if not provided
    if validator is None:
        if model_path is None:
            # Try default model path
            script_dir = os.path.dirname(os.path.abspath(__file__))
            model_path = os.path.join(script_dir, "model_artifacts.pkl")
            if not os.path.exists(model_path):
                raise ValueError(
                    f"Model artifacts not found at {model_path}. "
                    "Please provide model_path or train the model first."
                )
        validator = ClientValidator(model_path)
    
    # Validate client
    result = validator.validate_client(
        client_id=str(client_id),
        client_data=client_data,
        return_details=return_details
    )
    
    # Add client_id to result
    result["client_id"] = str(client_id)
    
    return result

def validate_clients_from_json_batch(
    json_inputs: List[Union[str, Dict[str, Any]]],
    model_path: Optional[str] = None,
    validator: Optional[ClientValidator] = None,
    return_details: bool = True
) -> List[Dict[str, Any]]:
    """
    Validate multiple clients from a list of JSON inputs.
    
    Args:
        json_inputs: List of JSON inputs (file paths, JSON strings, or dicts)
        model_path: Path to model artifacts file (required if validator not provided)
        validator: Pre-initialized ClientValidator instance (optional, overrides model_path)
        return_details: If True, return detailed risk information
    
    Returns:
        List of validation result dictionaries
    """
    # Initialize validator once if not provided
    if validator is None:
        if model_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            model_path = os.path.join(script_dir, "model_artifacts.pkl")
        validator = ClientValidator(model_path)
    
    results = []
    for json_input in json_inputs:
        try:
            result = validate_client_from_json(
                json_input=json_input,
                validator=validator,
                return_details=return_details
            )
            results.append(result)
        except Exception as e:
            # Add error result
            results.append({
                "client_id": "unknown",
                "status": "Error",
                "risk_score": None,
                "triage": "Error",
                "error": str(e)
            })
    
    return results

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
    ap.add_argument("--save_model", type=str, default=None,
                    help="Path to save model artifacts for inference (optional)")
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

    # Save model artifacts for inference if requested
    if args.save_model:
        save_model_artifacts(
            cal, G, inv, f1_node, f2_node, edge_fields, f2_col,
            alphas, betas, theta_I, theta_F, app_id, args.save_model
        )
    else:
        # Default: save to same directory as script
        default_model_path = os.path.join(script_dir, "model_artifacts.pkl")
        save_model_artifacts(
            cal, G, inv, f1_node, f2_node, edge_fields, f2_col,
            alphas, betas, theta_I, theta_F, app_id, default_model_path
        )

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

# ----------------------------
# Example usage for inference
# ----------------------------

def example_validate_from_json():
    """
    Example of how to validate clients from JSON input using real JSON files from client_data folder.
    """
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "model_artifacts.pkl")
    
    if not os.path.exists(model_path):
        print(f"Error: Model artifacts not found at {model_path}")
        print("Please run main() first to train and save the model.")
        print("\nTo train: python multipersistence.py")
        return
    
    # Get client_data directory
    parent_dir = os.path.dirname(script_dir)
    client_data_dir = os.path.join(parent_dir, "client_data")
    
    if not os.path.exists(client_data_dir):
        print(f"Error: client_data directory not found at {client_data_dir}")
        return
    
    # Find all JSON files in client_data directory
    json_files = [f for f in os.listdir(client_data_dir) if f.endswith('.json')]
    
    if not json_files:
        print(f"Error: No JSON files found in {client_data_dir}")
        return
    
    print(f"Found {len(json_files)} JSON file(s) in client_data directory")
    print("=" * 60)
    print()
    
    results = []
    
    # Validate each JSON file
    for i, json_file in enumerate(json_files, 1):
        json_path = os.path.join(client_data_dir, json_file)
        print("=" * 60)
        print(f"Example {i}: Validating client from {json_file}")
        print("=" * 60)
        print(f"File path: {json_path}")
        
        try:
            result = validate_client_from_json(json_path, model_path=model_path, return_details=True)
            print("\nValidation Result:")
            print(json.dumps(result, indent=2))
            results.append(result)
        except Exception as e:
            print(f"\nError validating {json_file}: {e}")
            results.append({
                "client_id": json_file,
                "status": "Error",
                "error": str(e)
            })
        
        print()
    
    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for i, result in enumerate(results, 1):
        if "error" in result:
            print(f"Client {i} ({result.get('client_id', 'unknown')}): Error - {result.get('error', 'Unknown error')}")
        else:
            print(f"Client {i} ({result.get('client_id', 'unknown')}): {result.get('status', 'Unknown')} ({result.get('triage', 'Unknown')}) - Risk Score: {result.get('risk_score', 'N/A')}")
    
    return results

def example_validate_client():
    """
    Example of how to use ClientValidator to validate new clients from JSON files in client_data folder.
    """
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "model_artifacts.pkl")
    
    if not os.path.exists(model_path):
        print(f"Error: Model artifacts not found at {model_path}")
        print("Please run main() first to train and save the model.")
        print("\nTo train: python multipersistence.py")
        return
    
    # Get client_data directory
    parent_dir = os.path.dirname(script_dir)
    client_data_dir = os.path.join(parent_dir, "client_data")
    
    if not os.path.exists(client_data_dir):
        print(f"Error: client_data directory not found at {client_data_dir}")
        return
    
    # Find all JSON files in client_data directory
    json_files = [f for f in os.listdir(client_data_dir) if f.endswith('.json')]
    
    if not json_files:
        print(f"Error: No JSON files found in {client_data_dir}")
        return
    
    # Initialize validator
    print("Loading model artifacts...")
    validator = ClientValidator(model_path)
    print("Model loaded successfully!\n")
    
    print(f"Found {len(json_files)} JSON file(s) in client_data directory")
    print("=" * 60)
    print()
    
    results = []
    
    # Validate each JSON file using the validator directly
    for i, json_file in enumerate(json_files, 1):
        json_path = os.path.join(client_data_dir, json_file)
        print("=" * 60)
        print(f"Example {i}: Validating client from {json_file}")
        print("=" * 60)
        print(f"File path: {json_path}")
        
        try:
            # Load JSON file
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # Extract client_id and structured_data
            client_id = json_data.get("client_data_id") or json_data.get("client_id") or json_data.get("id")
            if not client_id:
                client_id = os.path.splitext(json_file)[0]  # Use filename without extension
            
            structured_data = json_data.get("structured_data", {})
            if not structured_data:
                structured_data = {k: v for k, v in json_data.items() 
                                if k not in ["client_data_id", "client_id", "id", "created_at", "updated_at", "filename"]}
            
            # Filter out None values
            client_data = {k: v for k, v in structured_data.items() if v is not None}
            
            print(f"Client ID: {client_id}")
            print(f"Fields with data: {len(client_data)} out of {len(structured_data)}")
            
            # Validate client
            result = validator.validate_client(
                client_id=str(client_id),
                client_data=client_data,
                return_details=True
            )
            
            print(f"\nStatus: {result['status']}")
            print(f"Risk Score: {result['risk_score']:.4f}")
            print(f"Triage: {result['triage']}")
            if 'connections' in result:
                print(f"Graph Connections: {result['connections']}")
                print(f"F1 Reuse Risk: {result['f1_reuse_risk']:.4f}")
                print(f"F2 Proxy: {result['f2_proxy']:.4f}")
            
            result["client_id"] = str(client_id)
            results.append(result)
            
        except Exception as e:
            print(f"\nError validating {json_file}: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "client_id": json_file,
                "status": "Error",
                "error": str(e)
            })
        
        print()
    
    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for i, result in enumerate(results, 1):
        if "error" in result:
            print(f"Client {i} ({result.get('client_id', 'unknown')}): Error - {result.get('error', 'Unknown error')}")
        else:
            print(f"Client {i} ({result.get('client_id', 'unknown')}): {result.get('status', 'Unknown')} ({result.get('triage', 'Unknown')}) - Risk Score: {result.get('risk_score', 'N/A'):.4f}")
    
    return results

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        # Run validation example
        example_validate_client()
    elif len(sys.argv) > 1 and sys.argv[1] == "validate-json-example":
        # Run JSON validation example
        example_validate_from_json()
    elif len(sys.argv) > 1 and sys.argv[1] == "validate-json":
        # Validate from JSON file
        ap = argparse.ArgumentParser(description="Validate client from JSON input")
        ap.add_argument("--json", type=str, required=True,
                       help="Path to JSON file or JSON string")
        ap.add_argument("--model", type=str, default=None,
                       help="Path to model artifacts (default: model_artifacts.pkl in script directory)")
        ap.add_argument("--output", type=str, default=None,
                       help="Path to save JSON output (optional)")
        ap.add_argument("--details", action="store_true", default=True,
                       help="Include detailed risk information")
        
        # Parse arguments (skip first argument which is "validate-json")
        args = ap.parse_args(sys.argv[2:])
        
        try:
            result = validate_client_from_json(
                json_input=args.json,
                model_path=args.model,
                return_details=args.details
            )
            
            # Print result
            print("=" * 60)
            print("Validation Result")
            print("=" * 60)
            print(json.dumps(result, indent=2))
            
            # Save to file if requested
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2)
                print(f"\nResult saved to {args.output}")
            
            # Return result as exit code (0 = Validated, 1 = Flagged)
            sys.exit(0 if result["status"] == "Validated" else 1)
            
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Run training
        main()
