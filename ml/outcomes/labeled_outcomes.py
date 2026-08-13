"""
Seeds the labeled_outcomes table in Postgres.

Label rule: high_readiness = 1 when has_ci_cd AND monitoring_count >= 2 AND prod_scale_score >= 2.
Keep this rule in sync with ml/features/extractor.py::compute_label.

Ground truth from POST /submissions/{id}/outcome takes precedence over heuristic labels
when available in the ground_truth_outcomes table.

  make ml-labels                           # relabel all submissions
  make ml-relabel                          # only label new submissions
  make ml-relabel-and-retrain              # incremental + auto-retrain if threshold met
"""
import argparse
import os
import subprocess
import sys

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[2]))

from ml.features.feature_pipeline import build_feature_frame

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://assessment:assessment@localhost:5432/assessment",
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS labeled_outcomes (
    submission_id   VARCHAR(26) PRIMARY KEY,
    respondent_id   TEXT        NOT NULL,
    template_id     VARCHAR(26) NOT NULL,
    high_readiness  SMALLINT    NOT NULL,
    labeled_at      TIMESTAMP   NOT NULL DEFAULT now()
);
"""


def generate_labels(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["high_readiness"] = (
        (frame["has_ci_cd"] == 1)
        & (frame["monitoring_count"] >= 2)
        & (frame["prod_scale_score"] >= 2)
    ).astype(int)
    return frame[["submission_id", "respondent_id", "template_id", "high_readiness"]]


def apply_ground_truth_overrides(engine, labels: pd.DataFrame) -> pd.DataFrame:
    """Replace heuristic labels with ground truth where available."""
    try:
        gt = pd.read_sql(
            text("SELECT submission_id, high_readiness FROM ground_truth_outcomes"),
            engine,
        )
        if gt.empty:
            return labels
        labels = labels.merge(gt, on="submission_id", how="left", suffixes=("", "_gt"))
        # Where ground truth exists, it wins
        mask = labels["high_readiness_gt"].notna()
        labels.loc[mask, "high_readiness"] = labels.loc[mask, "high_readiness_gt"].astype(int)
        labels = labels.drop(columns=["high_readiness_gt"])
        print(f"  Applied {int(mask.sum())} ground truth override(s)")
    except Exception as exc:
        print(f"  Warning: could not load ground truth ({exc}), using heuristic only")
    return labels


def upsert_labels(engine, labels: pd.DataFrame) -> None:
    with engine.begin() as conn:
        for _, row in labels.iterrows():
            conn.execute(
                text("""
                    INSERT INTO labeled_outcomes (submission_id, respondent_id, template_id, high_readiness)
                    VALUES (:sid, :rid, :tid, :label)
                    ON CONFLICT (submission_id)
                    DO UPDATE SET high_readiness = EXCLUDED.high_readiness, labeled_at = now()
                """),
                {
                    "sid":   row.submission_id,
                    "rid":   row.respondent_id,
                    "tid":   row.template_id,
                    "label": int(row.high_readiness),
                },
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only label submissions not yet in labeled_outcomes",
    )
    parser.add_argument(
        "--retrain-threshold",
        type=int,
        default=0,
        metavar="N",
        help="Trigger ml-train automatically if N or more new submissions were labeled (0 = disabled)",
    )
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))

    frame = build_feature_frame(engine)

    if args.incremental:
        with engine.connect() as conn:
            existing = {
                row[0]
                for row in conn.execute(text("SELECT submission_id FROM labeled_outcomes"))
            }
        frame = frame[~frame["submission_id"].isin(existing)].copy()
        if frame.empty:
            print("No new submissions to label.")
            return

    labels = generate_labels(frame)
    labels = apply_ground_truth_overrides(engine, labels)
    upsert_labels(engine, labels)

    pos = int(labels["high_readiness"].sum())
    mode = "incremental" if args.incremental else "full"
    print(f"[{mode}] Labeled {len(labels)} submissions — {pos} high readiness, {len(labels) - pos} low readiness")

    if args.incremental and args.retrain_threshold > 0 and len(labels) >= args.retrain_threshold:
        print(f"New label count {len(labels)} >= threshold {args.retrain_threshold} — triggering retrain...")
        result = subprocess.run(
            [sys.executable, "-m", "ml.training.train_readiness_model"],
            env={**os.environ},
        )
        if result.returncode != 0:
            print("Warning: retrain exited with non-zero status", file=sys.stderr)


if __name__ == "__main__":
    main()
