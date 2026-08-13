"""
Roll back Production to the most-recently Archived model version.

  make ml-rollback

Safe to run at any time. If no Archived version exists the command
exits non-zero. The previously Production-staged version is demoted
to Archived before the rollback target is promoted.
"""
import os
import sys

import mlflow
from mlflow.tracking import MlflowClient

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
MODEL_NAME          = "readiness-classifier"


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

    prod_versions = [v for v in versions if v.current_stage == "Production"]
    archived_versions = sorted(
        [v for v in versions if v.current_stage == "Archived"],
        key=lambda v: int(v.version),
        reverse=True,
    )

    if not archived_versions:
        print(
            "No Archived versions available to roll back to. "
            "Promote at least one version before attempting a rollback.",
            file=sys.stderr,
        )
        sys.exit(1)

    rollback_target = archived_versions[0]
    print(f"Rollback target: v{rollback_target.version} (most-recent Archived)")

    for v in prod_versions:
        client.transition_model_version_stage(MODEL_NAME, v.version, "Archived")
        print(f"Demoted v{v.version}: Production → Archived")

    client.transition_model_version_stage(MODEL_NAME, rollback_target.version, "Production")
    print(f"Restored v{rollback_target.version} → Production")


if __name__ == "__main__":
    main()
