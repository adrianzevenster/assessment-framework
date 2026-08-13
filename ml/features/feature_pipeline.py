"""
Builds a flat feature frame from Postgres (default) or Trino/Iceberg.

  make ml-features               # Postgres source
  make ml-features-trino         # Iceberg Gold via Trino (requires Spark Gold jobs to have run)
"""
import argparse
import hashlib
import os

import pandas as pd
from sqlalchemy import create_engine, text

from ml.features.extractor import FEATURE_COLS, build_full_feature_dict, extract_features_from_dict

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://assessment:assessment@localhost:5432/assessment",
)
TRINO_URL = os.getenv("TRINO_URL", "trino://trino@localhost:8080/demo")
OUTPUT_PATH = os.getenv("FEATURE_OUTPUT_PATH", "ml/features/feature_frame.parquet")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def build_feature_frame(engine) -> pd.DataFrame:
    """Build feature frame from Postgres operational data."""
    submissions = pd.read_sql(
        text("SELECT submission_id, respondent_id, template_id, submitted_at FROM submissions"),
        engine,
    )
    responses_df = pd.read_sql(
        text("SELECT submission_id, question_key, answer_text, answer_json FROM responses"),
        engine,
    )
    respondent_stats = pd.read_sql(
        text("""
            SELECT
                respondent_id,
                COUNT(*)        AS respondent_submission_count,
                MIN(submitted_at) AS first_submission_at
            FROM submissions
            GROUP BY respondent_id
        """),
        engine,
    )

    submissions["respondent_id_hashed"] = submissions["respondent_id"].apply(_hash)
    grouped = responses_df.groupby("submission_id")

    rows = []
    for _, sub in submissions.iterrows():
        sid = sub["submission_id"]
        rid = sub["respondent_id"]

        try:
            sub_responses = grouped.get_group(sid)
        except KeyError:
            sub_responses = pd.DataFrame()

        response_dicts = [
            {
                "question_key": r["question_key"],
                "answer_text":  r["answer_text"],
                "answer_json":  r["answer_json"] if isinstance(r["answer_json"], dict) else None,
            }
            for _, r in sub_responses.iterrows()
        ]
        resp_feats = extract_features_from_dict(response_dicts)

        stats_row = respondent_stats[respondent_stats["respondent_id"] == rid]
        sub_count = int(stats_row["respondent_submission_count"].iloc[0]) if not stats_row.empty else 1
        first_at  = stats_row["first_submission_at"].iloc[0] if not stats_row.empty else sub["submitted_at"]
        days_delta = 0
        if pd.notna(first_at) and pd.notna(sub["submitted_at"]):
            days_delta = max(0, (pd.Timestamp(sub["submitted_at"]) - pd.Timestamp(first_at)).days)

        feat = build_full_feature_dict(resp_feats, sub_count, days_delta)
        feat["submission_id"] = sid
        feat["respondent_id"] = sub["respondent_id_hashed"]
        feat["template_id"]   = sub["template_id"]
        rows.append(feat)

    if not rows:
        return pd.DataFrame(columns=["submission_id", "respondent_id", "template_id"] + FEATURE_COLS)

    frame = pd.DataFrame(rows)
    for col in FEATURE_COLS:
        frame[col] = frame[col].fillna(0).astype(int)
    return frame


def build_feature_frame_from_trino(trino_engine) -> pd.DataFrame:
    """
    Read pre-computed features from demo.gold.ml_features via Trino.
    Requires Spark Gold jobs to have run (build_gold_views.sql).
    """
    cols = ", ".join(
        ["submission_id", "respondent_id", "template_id", "submitted_at"] + FEATURE_COLS
    )
    df = pd.read_sql(f"SELECT {cols} FROM demo.gold.ml_features", trino_engine)  # noqa: S608
    for col in FEATURE_COLS:
        df[col] = df[col].fillna(0).astype(int)
    return df


def main(source: str = "postgres") -> None:
    if source == "trino":
        engine = create_engine(TRINO_URL)
        frame = build_feature_frame_from_trino(engine)
    else:
        engine = create_engine(DATABASE_URL)
        frame = build_feature_frame(engine)

    frame.to_parquet(OUTPUT_PATH, index=False)
    print(f"Feature frame: {OUTPUT_PATH}  shape={frame.shape}  source={source}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["postgres", "trino"], default="postgres")
    args = parser.parse_args()
    main(source=args.source)
