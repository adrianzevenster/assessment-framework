"""
Trains a logistic regression readiness classifier and logs to MLflow.

Reads features from the feature pipeline and labels from labeled_outcomes.
Requires: make ml-labels && make ml-train  (or run feature_pipeline.py first).

Model is only registered if ROC-AUC >= MIN_ROC_AUC (default 0.65, override via env).

Run: python -m ml.training.train_readiness_model
"""

import os
import sys

import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine, text

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[2]))

from ml.features.extractor import FEATURE_COLS
from ml.features.feature_pipeline import build_feature_frame

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://assessment:assessment@localhost:5432/assessment",
)
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
EXPERIMENT_NAME     = "readiness-classifier"
MIN_ROC_AUC         = float(os.getenv("MIN_ROC_AUC", "0.65"))


def load_training_data(engine) -> pd.DataFrame:
    frame = build_feature_frame(engine)
    labels = pd.read_sql(
        text("SELECT submission_id, high_readiness FROM labeled_outcomes"),
        engine,
    )
    return frame.merge(labels, on="submission_id", how="inner")


def main():
    engine = create_engine(DATABASE_URL)
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    df = load_training_data(engine)

    if len(df) < 10:
        print(f"Only {len(df)} labeled rows — need at least 10 to train. Run make ml-labels after seeding more submissions.")
        return

    X = df[FEATURE_COLS].fillna(0)
    y = df["high_readiness"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42,
        stratify=y if y.nunique() > 1 else None,
    )

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=500, random_state=42)),
    ])

    with mlflow.start_run():
        mlflow.log_params({
            "model":         "LogisticRegression",
            "features":      FEATURE_COLS,
            "train_size":    len(X_train),
            "test_size":     len(X_test),
            "positive_rate": float(y.mean()),
            "min_roc_auc":   MIN_ROC_AUC,
        })

        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]

        roc = roc_auc_score(y_test, y_prob) if y_test.nunique() > 1 else float("nan")
        report = classification_report(y_test, y_pred, output_dict=True)

        mlflow.log_metrics({
            "roc_auc":        roc,
            "accuracy":       report["accuracy"],
            "precision_high": report.get("1", {}).get("precision", 0),
            "recall_high":    report.get("1", {}).get("recall", 0),
            "f1_high":        report.get("1", {}).get("f1-score", 0),
        })

        print(f"ROC-AUC: {roc:.3f}  Accuracy: {report['accuracy']:.3f}")
        print(classification_report(y_test, y_pred))

        if not (roc >= MIN_ROC_AUC):
            print(f"ROC-AUC {roc:.3f} below minimum {MIN_ROC_AUC:.3f} — skipping model registration.")
        else:
            mlflow.sklearn.log_model(
                model,
                artifact_path="model",
                registered_model_name="readiness-classifier",
            )
            print(f"Model registered: readiness-classifier")


if __name__ == "__main__":
    main()
