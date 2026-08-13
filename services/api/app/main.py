import logging
import os

import httpx
import numpy as np
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.labeler import label_submission
from app.schemas import OutcomeCreate, SubmissionCreate, TemplateCreate
from app.scoring import get_analytics_summary, get_submission_score
from app.services import create_template, submit_assessment
from app.telemetry import configure_telemetry

try:
    from ml.features.extractor import (
        FEATURE_COLS,
        build_full_feature_dict,
        extract_features_from_dict,
        features_to_vector,
    )
    _EXTRACTOR_AVAILABLE = True
except ImportError:
    FEATURE_COLS = [
        "has_ml_strategy", "has_ci_cd", "serving_pattern_count",
        "monitoring_count", "experiment_tracking_score", "prod_scale_score",
        "answered_question_count", "respondent_submission_count", "days_since_first_submission",
    ]
    _EXTRACTOR_AVAILABLE = False

logger = logging.getLogger(__name__)

app = FastAPI(title="Assessment Framework API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
configure_telemetry(app)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/templates")
def post_template(payload: TemplateCreate, db: Session = Depends(get_db)):
    template = create_template(db, payload)
    return {"template_id": template.template_id, "status": template.status}


@app.post("/submissions")
def post_submission(
    payload: SubmissionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    submission = submit_assessment(db, payload)
    background_tasks.add_task(label_submission, submission.submission_id)
    return {"submission_id": submission.submission_id, "status": submission.status}


@app.get("/submissions/{submission_id}/score")
def get_score(submission_id: str, db: Session = Depends(get_db)):
    result = get_submission_score(db, submission_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return result


@app.post("/submissions/{submission_id}/outcome")
def record_outcome(submission_id: str, payload: OutcomeCreate, db: Session = Depends(get_db)):
    """Record a verified ground-truth readiness outcome; overrides heuristic labels at next ml-labels run."""
    from app.models import Submission
    from sqlalchemy import text as _sqlt
    if not db.query(Submission).filter(Submission.submission_id == submission_id).first():
        raise HTTPException(status_code=404, detail="Submission not found")
    db.execute(_sqlt("""
        CREATE TABLE IF NOT EXISTS ground_truth_outcomes (
            submission_id  VARCHAR(26) PRIMARY KEY,
            high_readiness SMALLINT    NOT NULL,
            collected_at   TIMESTAMP   NOT NULL DEFAULT now(),
            collected_by   TEXT,
            notes          TEXT
        )
    """))
    db.execute(
        _sqlt("""
            INSERT INTO ground_truth_outcomes (submission_id, high_readiness, collected_by, notes)
            VALUES (:sid, :label, :by, :notes)
            ON CONFLICT (submission_id) DO UPDATE
                SET high_readiness = EXCLUDED.high_readiness,
                    collected_at   = now(),
                    collected_by   = EXCLUDED.collected_by,
                    notes          = EXCLUDED.notes
        """),
        {"sid": submission_id, "label": payload.high_readiness, "by": payload.collected_by, "notes": payload.notes},
    )
    db.commit()
    return {"submission_id": submission_id, "high_readiness": payload.high_readiness, "status": "recorded"}


@app.get("/analytics/summary")
def analytics_summary(db: Session = Depends(get_db)):
    return get_analytics_summary(db)


@app.get("/analytics/submissions")
def all_submissions(db: Session = Depends(get_db)):
    from app.scoring import get_all_submissions_with_scores
    return get_all_submissions_with_scores(db)


@app.get("/analytics/responses/distribution")
def response_distributions(db: Session = Depends(get_db)):
    from app.scoring import get_response_distributions
    return get_response_distributions(db)


@app.get("/submissions/{submission_id}/predict")
def predict_readiness(submission_id: str, db: Session = Depends(get_db)):
    from app.models import Response, Submission
    if not db.query(Submission).filter(Submission.submission_id == submission_id).first():
        raise HTTPException(status_code=404, detail="Submission not found")

    responses = db.query(Response).filter(Response.submission_id == submission_id).all()

    if not _EXTRACTOR_AVAILABLE:
        return {"probability": None, "prediction": None, "contributions": [],
                "available": False, "error": "ml.features.extractor not available"}

    response_dicts = [
        {"question_key": r.question_key, "answer_text": r.answer_text, "answer_json": r.answer_json}
        for r in responses
    ]
    resp_feats = extract_features_from_dict(response_dicts)

    from sqlalchemy import text as _sqlt
    sub_record = db.query(Submission).filter(Submission.submission_id == submission_id).first()
    stats_row = db.execute(
        _sqlt("""
            SELECT COUNT(*), MIN(submitted_at)
            FROM submissions
            WHERE respondent_id = (SELECT respondent_id FROM submissions WHERE submission_id = :sid)
        """),
        {"sid": submission_id},
    ).fetchone()
    sub_count  = int(stats_row[0]) if stats_row else 1
    days_delta = 0
    if stats_row and stats_row[1] and sub_record and sub_record.submitted_at:
        first_at = stats_row[1]
        curr     = sub_record.submitted_at
        if hasattr(first_at, "tzinfo") and first_at.tzinfo:
            first_at = first_at.replace(tzinfo=None)
        if hasattr(curr, "tzinfo") and curr.tzinfo:
            curr = curr.replace(tzinfo=None)
        days_delta = max(0, (curr - first_at).days)

    feat = build_full_feature_dict(resp_feats, sub_count, days_delta)
    vec  = features_to_vector(feat)

    try:
        model = _load_model()
        X = np.array([vec])
        prob = float(model.predict_proba(X)[0][1])
        clf = model.named_steps["clf"]
        coef = clf.coef_[0].tolist()
        contributions = sorted(
            [
                {"feature": FEATURE_COLS[i], "value": vec[i], "weight": round(coef[i], 3)}
                for i in range(len(FEATURE_COLS))
            ],
            key=lambda x: abs(x["weight"]),
            reverse=True,
        )
        return {
            "probability":    round(prob, 3),
            "prediction":     prob >= 0.5,
            "contributions":  contributions,
            "available":      True,
        }
    except Exception as exc:
        return {
            "probability":   None,
            "prediction":    None,
            "contributions": [],
            "available":     False,
            "error":         str(exc),
        }


_MLFLOW_URL = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
_model_cache = None


def _load_model():
    global _model_cache
    if _model_cache is None:
        import mlflow
        import mlflow.sklearn
        mlflow.set_tracking_uri(_MLFLOW_URL)
        _model_cache = mlflow.sklearn.load_model("models:/readiness-classifier/latest")
    return _model_cache


@app.get("/analytics/ml-runs")
async def ml_runs():
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(
                f"{_MLFLOW_URL}/api/2.0/mlflow/runs/search",
                json={"max_results": 20, "order_by": ["attribute.start_time DESC"]},
            )
            resp.raise_for_status()
            runs = resp.json().get("runs", [])
            return [
                {
                    "run_id":     r["info"]["run_id"][:8],
                    "experiment": r["info"].get("experiment_id", "—"),
                    "status":     r["info"]["status"],
                    "started":    r["info"].get("start_time"),
                    "metrics":    {k: round(v, 4) for k, v in (r.get("data", {}).get("metrics") or {}).items()},
                    "params":     r.get("data", {}).get("params") or {},
                }
                for r in runs
            ]
        except Exception:
            return []


@app.get("/analytics/ml-experiments")
async def ml_experiments():
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{_MLFLOW_URL}/api/2.0/mlflow/experiments/search?max_results=20")
            resp.raise_for_status()
            exps = resp.json().get("experiments", [])
            return [
                {
                    "experiment_id":   e["experiment_id"],
                    "name":            e["name"],
                    "lifecycle_stage": e["lifecycle_stage"],
                }
                for e in exps
                if e["name"] != "Default"
            ]
        except Exception:
            return []


@app.get("/analytics/ml-model-versions")
async def ml_model_versions():
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            ver_resp = await client.get(
                f"{_MLFLOW_URL}/api/2.0/mlflow/registered-models/get-latest-versions",
                params={"name": "readiness-classifier"},
            )
            versions = ver_resp.json().get("model_versions", [])
            result = []
            for v in versions:
                run_id = v.get("run_id", "")
                metrics, params = {}, {}
                if run_id:
                    run_resp = await client.get(
                        f"{_MLFLOW_URL}/api/2.0/mlflow/runs/get",
                        params={"run_id": run_id},
                    )
                    run_data = run_resp.json().get("run", {}).get("data", {})
                    metrics = {m["key"]: round(m["value"], 4) for m in (run_data.get("metrics") or [])}
                    params  = {p["key"]: p["value"]           for p in (run_data.get("params")  or [])}
                result.append({
                    "name":    v["name"],
                    "version": v["version"],
                    "stage":   v.get("current_stage", "None"),
                    "status":  v.get("status", ""),
                    "created": v.get("creation_timestamp"),
                    "run_id":  run_id[:8] if run_id else "—",
                    "source":  v.get("source", ""),
                    "metrics": metrics,
                    "params":  params,
                })
            return result
        except Exception:
            return []


@app.get("/analytics/drift")
def feature_drift(db: Session = Depends(get_db)):
    """Compare current feature distributions against the saved training reference frame (KS test)."""
    from pathlib import Path
    ref_path = Path("ml/features/feature_frame.parquet")
    if not ref_path.exists():
        return {"available": False, "reason": "Reference frame not found. Run: make ml-features"}
    try:
        import pandas as pd
        from scipy.stats import ks_2samp
        from ml.features.feature_pipeline import build_feature_frame
        from sqlalchemy import create_engine as _ce
        reference = pd.read_parquet(ref_path)
        cur_engine = _ce(os.getenv("DATABASE_URL", "postgresql+psycopg://assessment:assessment@postgres:5432/assessment"))
        current = build_feature_frame(cur_engine)
        if current.empty:
            return {"available": False, "reason": "No current submissions"}
        results = {}
        for col in FEATURE_COLS:
            if col in reference.columns and col in current.columns:
                stat, p = ks_2samp(reference[col].fillna(0), current[col].fillna(0))
                results[col] = {
                    "ks_stat":        round(float(stat), 4),
                    "p_value":        round(float(p), 4),
                    "drift_detected": bool(p < 0.05),
                }
        drifted = [k for k, v in results.items() if v["drift_detected"]]
        return {
            "available":        True,
            "drift_detected":   bool(drifted),
            "drifted_features": drifted,
            "reference_size":   len(reference),
            "current_size":     len(current),
            "features":         results,
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


@app.get("/analytics/feature-stats")
def feature_stats(db: Session = Depends(get_db)):
    from app.models import Response, Submission
    from sqlalchemy import text as sqlt

    total = db.query(func.count(Submission.submission_id)).scalar() or 0

    def bool_stat(key: str) -> dict:
        rows = db.query(Response).filter(Response.question_key == key).all()
        yes = sum(1 for r in rows if isinstance(r.answer_json, dict) and r.answer_json.get("value") is True)
        return {"mean": round(yes / len(rows), 3) if rows else 0, "type": "binary", "n": len(rows)}

    def multi_stat(key: str) -> dict:
        rows = db.query(Response).filter(Response.question_key == key).all()
        counts = [
            len(r.answer_json["value"])
            for r in rows
            if isinstance(r.answer_json, dict) and isinstance(r.answer_json.get("value"), list)
        ]
        if not counts:
            return {"mean": 0, "min": 0, "max": 0, "type": "count", "n": 0}
        return {"mean": round(sum(counts) / len(counts), 2), "min": min(counts), "max": max(counts), "type": "count", "n": len(counts)}

    def cat_stat(key: str, score_map: dict) -> dict:
        rows = db.query(Response).filter(Response.question_key == key).all()
        scores = [score_map.get(r.answer_text or "", 0) for r in rows]
        dist = {}
        for r in rows:
            label = r.answer_text or "—"
            dist[label] = dist.get(label, 0) + 1
        return {
            "mean": round(sum(scores) / len(scores), 2) if scores else 0,
            "type": "categorical",
            "n":    len(rows),
            "distribution": dist,
        }

    try:
        row = db.execute(sqlt("SELECT COUNT(*), COALESCE(SUM(high_readiness),0) FROM labeled_outcomes")).fetchone()
        labeled_n, high_n = int(row[0]), int(row[1])
    except Exception:
        labeled_n, high_n = 0, 0

    try:
        from ml.features.extractor import PROD_SCALE_SCORE, TRACKING_SCORE  # type: ignore[import]
    except ImportError:
        TRACKING_SCORE = {"MLflow + model registry": 3, "Weights & Biases / Neptune": 2, "Custom solution": 1, "Notebooks / ad-hoc": 0}  # type: ignore[assignment]
        PROD_SCALE_SCORE = {"10+ models in production": 3, "1–9 models in production": 2, "Proof of concept / pilot": 1, "Not yet deployed": 0}  # type: ignore[assignment]

    return {
        "total_submissions":   total,
        "labeled_submissions": labeled_n,
        "high_readiness_n":    high_n,
        "low_readiness_n":     labeled_n - high_n,
        "high_readiness_rate": round(high_n / labeled_n, 3) if labeled_n else 0,
        "features": {
            "has_ml_strategy":           bool_stat("ml_strategy"),
            "has_ci_cd":                 bool_stat("ci_cd_ml"),
            "serving_pattern_count":     multi_stat("serving_patterns"),
            "monitoring_count":          multi_stat("model_monitoring"),
            "experiment_tracking_score": cat_stat("experiment_tracking", TRACKING_SCORE),
            "prod_scale_score":          cat_stat("prod_scale", PROD_SCALE_SCORE),
        },
    }
