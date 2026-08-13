"""
Promotes the latest MLflow challenger to Production if it beats the current champion on ROC-AUC.

  make ml-promote

Compares the latest registered version against the Production-staged version (if any).
Promotes if: challenger_roc_auc > champion_roc_auc AND challenger_roc_auc >= MIN_ROC_AUC.
"""
import os
import sys

import mlflow
from mlflow.tracking import MlflowClient

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
MODEL_NAME          = "readiness-classifier"
MIN_ROC_AUC         = float(os.getenv("MIN_ROC_AUC", "0.65"))


def get_metric(client: MlflowClient, run_id: str, key: str) -> float | None:
    try:
        history = client.get_metric_history(run_id, key)
        return history[-1].value if history else None
    except Exception:
        return None


def main() -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()

    try:
        versions = client.get_latest_versions(MODEL_NAME)
    except Exception as exc:
        print(f"Cannot fetch model versions: {exc}", file=sys.stderr)
        sys.exit(1)

    if not versions:
        print("No registered versions found. Run: make ml-train", file=sys.stderr)
        sys.exit(1)

    # Challenger = highest version number
    challenger = max(versions, key=lambda v: int(v.version))
    challenger_roc = get_metric(client, challenger.run_id, "roc_auc")

    if challenger_roc is None:
        print("Challenger has no roc_auc metric — was it trained with the current pipeline?", file=sys.stderr)
        sys.exit(1)

    print(f"Challenger: v{challenger.version}  ROC-AUC={challenger_roc:.3f}  stage={challenger.current_stage}")

    if challenger_roc < MIN_ROC_AUC:
        print(f"FAIL: challenger ROC-AUC {challenger_roc:.3f} < minimum {MIN_ROC_AUC:.3f}. Not promoting.")
        sys.exit(1)

    prod_versions = [v for v in versions if v.current_stage == "Production"]
    if prod_versions:
        champion = max(prod_versions, key=lambda v: int(v.version))
        champion_roc = get_metric(client, champion.run_id, "roc_auc") or 0.0
        print(f"Champion:   v{champion.version}  ROC-AUC={champion_roc:.3f}  stage=Production")

        if challenger_roc <= champion_roc:
            print(
                f"Challenger does not improve on champion "
                f"({challenger_roc:.3f} <= {champion_roc:.3f}). Not promoting."
            )
            sys.exit(0)

        client.transition_model_version_stage(MODEL_NAME, champion.version, "Archived")
        print(f"Archived champion v{champion.version}")
    else:
        print("No Production champion found — first promotion.")

    client.transition_model_version_stage(MODEL_NAME, challenger.version, "Production")
    print(f"Promoted v{challenger.version} to Production  ROC-AUC={challenger_roc:.3f}")


if __name__ == "__main__":
    main()
