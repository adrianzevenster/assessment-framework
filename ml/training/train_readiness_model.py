"""
Trains a logistic regression readiness classifier and logs to MLflow.

Reads features from the feature pipeline and labels from labeled_outcomes.
Requires: make ml-labels && make ml-train  (or run feature_pipeline.py first).

Model is only registered if ROC-AUC >= MIN_ROC_AUC (default 0.65, override via env).
Cross-validation is used when n >= 20; a single stratified holdout is used otherwise.

Run: python -m ml.training.train_readiness_model
"""

import os
import sys
from pathlib import Path

import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, classification_report, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parents[2]))

from ml.features.extractor import FEATURE_COLS
from ml.features.feature_pipeline import build_feature_frame

DATABASE_URL      = os.getenv("DATABASE_URL", "postgresql+psycopg://assessment:assessment@localhost:5432/assessment")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
FEATURE_OUTPUT_PATH = os.getenv("FEATURE_OUTPUT_PATH", "ml/features/feature_frame.parquet")
EXPERIMENT_NAME   = "readiness-classifier"
MIN_ROC_AUC       = float(os.getenv("MIN_ROC_AUC", "0.65"))
CV_MIN_SAMPLES    = 20   # minimum labeled rows before running k-fold CV


def load_training_data(engine) -> pd.DataFrame:
    frame = build_feature_frame(engine)
    labels = pd.read_sql(
        text("SELECT submission_id, high_readiness FROM labeled_outcomes"),
        engine,
    )
    return frame.merge(labels, on="submission_id", how="inner")


def main() -> None:
    engine = create_engine(DATABASE_URL)
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    df = load_training_data(engine)

    if len(df) < 10:
        print(
            f"Only {len(df)} labeled rows — need at least 10 to train. "
            "Run make ml-labels after seeding more submissions."
        )
        return

    X = df[FEATURE_COLS].fillna(0)
    y = df["high_readiness"]

    positive_rate = float(y.mean())
    print(f"Dataset: {len(df)} rows  positives={y.sum()}  rate={positive_rate:.1%}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42,
        stratify=y if y.nunique() > 1 else None,
    )

    # class_weight='balanced' compensates for class imbalance automatically
    base_lr = LogisticRegression(max_iter=500, random_state=42, class_weight="balanced")
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf",    base_lr),
    ])

    with mlflow.start_run() as run:
        run_id = run.info.run_id

        # ── Cross-validation metrics (reliable estimates on small data) ──────
        cv_roc_auc: float | None = None
        cv_f1:      float | None = None
        if len(df) >= CV_MIN_SAMPLES and y.nunique() > 1:
            n_splits = min(5, int(y.sum()), int((y == 0).sum()))
            if n_splits >= 2:
                cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
                cv_roc_auc = float(cross_val_score(model, X, y, cv=cv, scoring="roc_auc").mean())
                cv_f1      = float(cross_val_score(model, X, y, cv=cv, scoring="f1").mean())
                mlflow.log_metrics({
                    "cv_roc_auc": round(cv_roc_auc, 4),
                    "cv_f1":      round(cv_f1, 4),
                    "cv_n_splits": n_splits,
                })
                print(f"CV ({n_splits}-fold)  ROC-AUC={cv_roc_auc:.3f}  F1={cv_f1:.3f}")

        # ── Fit on train split, evaluate on holdout ───────────────────────────
        model.fit(X_train, y_train)

        # Calibrate probabilities with Platt scaling on the holdout set
        calibrated = CalibratedClassifierCV(model, method="sigmoid", cv="prefit")
        if len(y_test) >= 4 and y_test.nunique() > 1:
            calibrated.fit(X_test, y_test)
            final_model = calibrated
        else:
            final_model = model

        y_pred = final_model.predict(X_test)
        y_prob = final_model.predict_proba(X_test)[:, 1]

        roc    = roc_auc_score(y_test, y_prob) if y_test.nunique() > 1 else float("nan")
        brier  = brier_score_loss(y_test, y_prob) if len(y_test) > 0 else float("nan")
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

        mlflow.log_params({
            "model":         "LogisticRegression+CalibratedCV",
            "class_weight":  "balanced",
            "features":      FEATURE_COLS,
            "train_size":    len(X_train),
            "test_size":     len(X_test),
            "positive_rate": round(positive_rate, 4),
            "min_roc_auc":   MIN_ROC_AUC,
        })
        mlflow.log_metrics({
            "roc_auc":        round(roc, 4),
            "brier_score":    round(brier, 4),
            "accuracy":       round(report["accuracy"], 4),
            "precision_high": round(report.get("1", {}).get("precision", 0), 4),
            "recall_high":    round(report.get("1", {}).get("recall", 0), 4),
            "f1_high":        round(report.get("1", {}).get("f1-score", 0), 4),
        })

        print(f"Holdout  ROC-AUC={roc:.3f}  Brier={brier:.3f}  Accuracy={report['accuracy']:.3f}")
        print(classification_report(y_test, y_pred, zero_division=0))

        # ── Save training reference frame as a versioned MLflow artifact ─────
        ref_path = Path(FEATURE_OUTPUT_PATH)
        if ref_path.exists():
            mlflow.log_artifact(str(ref_path), artifact_path="reference_frame")
            # Sidecar so drift.py and the API can trace which run owns the reference
            sidecar = ref_path.parent / "reference_run_id.txt"
            sidecar.write_text(run_id)
            print(f"Reference frame logged as artifact (run {run_id[:8]})")
        else:
            print(
                f"Warning: {ref_path} not found — skipping artifact log. "
                "Run make ml-features first to generate the reference frame."
            )

        if not (roc >= MIN_ROC_AUC):
            print(f"ROC-AUC {roc:.3f} below minimum {MIN_ROC_AUC:.3f} — skipping model registration.")
            return

        mlflow.sklearn.log_model(
            final_model,
            artifact_path="model",
            registered_model_name="readiness-classifier",
        )
        print("Model registered: readiness-classifier")


if __name__ == "__main__":
    main()
