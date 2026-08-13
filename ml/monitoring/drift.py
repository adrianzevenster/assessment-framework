"""
Feature distribution drift detection using two-sample KS tests.
Compares current Postgres data against the saved training reference frame (Parquet).

  make ml-drift

Exits non-zero if drift is detected in any feature (p < DRIFT_P_THRESHOLD).
"""
import os
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import ks_2samp
from sqlalchemy import create_engine

DATABASE_URL      = os.getenv("DATABASE_URL",        "postgresql+psycopg://assessment:assessment@localhost:5432/assessment")
REFERENCE_PATH    = os.getenv("FEATURE_OUTPUT_PATH", "ml/features/feature_frame.parquet")
P_VALUE_THRESHOLD = float(os.getenv("DRIFT_P_THRESHOLD", "0.05"))


def compute_drift_report(reference: pd.DataFrame, current: pd.DataFrame) -> dict:
    from ml.features.extractor import FEATURE_COLS

    results: dict = {}
    for col in FEATURE_COLS:
        if col not in reference.columns or col not in current.columns:
            continue
        ref_vals = reference[col].fillna(0).astype(float).values
        cur_vals = current[col].fillna(0).astype(float).values
        stat, p = ks_2samp(ref_vals, cur_vals)
        results[col] = {
            "ks_stat":        round(float(stat), 4),
            "p_value":        round(float(p), 4),
            "drift_detected": bool(p < P_VALUE_THRESHOLD),
            "ref_mean":       round(float(ref_vals.mean()), 3),
            "cur_mean":       round(float(cur_vals.mean()), 3),
        }

    drifted = [k for k, v in results.items() if v["drift_detected"]]
    return {
        "drift_detected":    bool(drifted),
        "drifted_features":  drifted,
        "n_drifted":         len(drifted),
        "reference_size":    len(reference),
        "current_size":      len(current),
        "p_value_threshold": P_VALUE_THRESHOLD,
        "features":          results,
    }


def main() -> None:
    ref_path = Path(REFERENCE_PATH)
    if not ref_path.exists():
        print(f"Reference frame not found at {ref_path}. Run: make ml-features", file=sys.stderr)
        sys.exit(1)

    reference = pd.read_parquet(ref_path)

    sys.path.insert(0, str(Path(__file__).parents[2]))
    from ml.features.feature_pipeline import build_feature_frame

    engine  = create_engine(DATABASE_URL)
    current = build_feature_frame(engine)

    if current.empty:
        print("No current submissions found.", file=sys.stderr)
        sys.exit(1)

    report = compute_drift_report(reference, current)

    print(f"Reference: {report['reference_size']} rows   Current: {report['current_size']} rows")
    print(f"Threshold: p < {report['p_value_threshold']}\n")

    for feat, stats in report["features"].items():
        flag = "DRIFT" if stats["drift_detected"] else "  OK "
        print(
            f"  [{flag}] {feat:<32} KS={stats['ks_stat']:.4f}  p={stats['p_value']:.4f}"
            f"  ref_mean={stats['ref_mean']:.2f}  cur_mean={stats['cur_mean']:.2f}"
        )

    if report["drift_detected"]:
        print(f"\nDrift detected in {report['n_drifted']} feature(s): {report['drifted_features']}")
        print("Consider retraining: make ml-all")
        sys.exit(1)
    else:
        print("\nNo drift detected.")


if __name__ == "__main__":
    main()
