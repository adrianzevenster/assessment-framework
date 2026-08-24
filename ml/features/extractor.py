"""
Canonical feature extraction for the readiness classifier.

Single source of truth for feature names, encoding maps, label rule.
Imported by:
  - ml/features/feature_pipeline.py  (batch training, both Postgres and Trino paths)
  - ml/training/train_readiness_model.py
  - services/api/app/labeler.py      (real-time auto-labelling via volume mount)
  - services/api/app/main.py         (real-time inference via volume mount)
"""
from __future__ import annotations

FEATURE_COLS: list[str] = [
    "has_ml_strategy",
    "has_ci_cd",
    "serving_pattern_count",
    "monitoring_count",
    "experiment_tracking_score",
    "prod_scale_score",
    "answered_question_count",
    "respondent_submission_count",
    "days_since_first_submission",
]

TRACKING_SCORE: dict[str, int] = {
    "MLflow + model registry":    3,
    "Weights & Biases / Neptune": 2,
    "Custom solution":             1,
    "Notebooks / ad-hoc":          0,
}

PROD_SCALE_SCORE: dict[str, int] = {
    "10+ models in production":  3,
    "1–9 models in production":  2,
    "Proof of concept / pilot":  1,
    "Not yet deployed":           0,
}


def extract_features_from_dict(responses: list[dict]) -> dict[str, int]:
    """
    Build a feature dict from a list of response dicts.
    Each dict must have keys: question_key, answer_text (str|None), answer_json (dict|None).
    Returns the 7 response-level features. Call build_full_feature_dict to add submission-level features.
    """
    by_key: dict[str, dict] = {r["question_key"]: r for r in responses}

    def bool_f(key: str) -> int:
        r = by_key.get(key)
        if not r:
            return 0
        val = r.get("answer_json")
        return 1 if isinstance(val, dict) and val.get("value") is True else 0

    def multi_f(key: str) -> int:
        r = by_key.get(key)
        if not r:
            return 0
        val = r.get("answer_json")
        if isinstance(val, dict):
            v = val.get("value", [])
            return len(v) if isinstance(v, list) else 0
        return 0

    def cat_f(key: str, score_map: dict[str, int]) -> int:
        r = by_key.get(key)
        if not r:
            return 0
        return score_map.get(r.get("answer_text") or "", 0)

    return {
        "has_ml_strategy":           bool_f("ml_strategy"),
        "has_ci_cd":                 bool_f("ci_cd_ml"),
        "serving_pattern_count":     multi_f("serving_patterns"),
        "monitoring_count":          multi_f("model_monitoring"),
        "experiment_tracking_score": cat_f("experiment_tracking", TRACKING_SCORE),
        "prod_scale_score":          cat_f("prod_scale", PROD_SCALE_SCORE),
        "answered_question_count":   len(responses),
    }


def build_full_feature_dict(
    response_feats: dict[str, int],
    respondent_submission_count: int = 1,
    days_since_first_submission: int = 0,
) -> dict[str, int]:
    """Merge response-level features with submission-level metadata features."""
    return {
        **response_feats,
        "respondent_submission_count": respondent_submission_count,
        "days_since_first_submission":  days_since_first_submission,
    }


def features_to_vector(feat: dict[str, int]) -> list[int]:
    """Return feature values in FEATURE_COLS order. Missing keys default to 0."""
    return [feat.get(c, 0) for c in FEATURE_COLS]


def compute_label(feat: dict[str, int]) -> int:
    """
    Heuristic readiness label.
    high_readiness = 1 when CI/CD is in place, monitoring covers ≥2 areas, and ≥1-9 models are in prod.
    Keep this in sync with ml/outcomes/labeled_outcomes.py::generate_labels.
    """
    return int(
        feat["has_ci_cd"] == 1
        and feat["monitoring_count"] >= 2
        and feat["prod_scale_score"] >= 2
    )
