from app.models import Response, Submission
from sqlalchemy import func
from sqlalchemy.orm import Session

_WEIGHTS: dict[str, dict] = {
    "ml_strategy":         {"type": "boolean",          "max": 15},
    "prod_scale":          {"type": "categorical",       "max": 10, "map": {
                                "10+ models in production": 10,
                                "1–9 models in production": 7,
                                "Proof of concept / pilot": 3,
                                "Not yet deployed":          0,
                            }},
    "experiment_tracking": {"type": "categorical",       "max": 15, "map": {
                                "MLflow + model registry":   15,
                                "Weights & Biases / Neptune": 12,
                                "Custom solution":            8,
                                "Notebooks / ad-hoc":         2,
                            }},
    "ci_cd_ml":            {"type": "boolean",          "max": 10},
    "serving_patterns":    {"type": "multiselect_count", "max": 25, "per_item": 5},
    "model_monitoring":    {"type": "multiselect_count", "max": 25, "per_item": 5},
}

_SECTIONS: dict[str, list[str]] = {
    "Strategy":      ["ml_strategy"],
    "Production":    ["prod_scale", "serving_patterns"],
    "MLOps":         ["experiment_tracking", "ci_cd_ml"],
    "Observability": ["model_monitoring"],
}


def _score_response(r: Response, cfg: dict) -> int:
    t = cfg["type"]
    if t == "boolean":
        val = r.answer_json.get("value", False) if isinstance(r.answer_json, dict) else False
        return cfg["max"] if val is True else 0
    if t == "numeric":
        val = r.answer_numeric or 0
        return min(int(val * cfg["scale"]), cfg["max"])
    if t == "multiselect_count":
        val = r.answer_json.get("value", []) if isinstance(r.answer_json, dict) else []
        count = len(val) if isinstance(val, list) else 0
        return min(count * cfg["per_item"], cfg["max"])
    if t == "categorical":
        return cfg["map"].get(r.answer_text or "", 0)
    return 0


def compute_score(responses: list[Response]) -> dict:
    by_key = {r.question_key: r for r in responses}
    raw: dict[str, int] = {}
    for key, cfg in _WEIGHTS.items():
        r = by_key.get(key)
        raw[key] = _score_response(r, cfg) if r else 0

    total = sum(raw.values())
    max_total = sum(cfg["max"] for cfg in _WEIGHTS.values())

    sections = {}
    for section, keys in _SECTIONS.items():
        sec_max = sum(_WEIGHTS[k]["max"] for k in keys)
        sec_actual = sum(raw.get(k, 0) for k in keys)
        sections[section] = {
            "score": sec_actual,
            "max": sec_max,
            "pct": round(sec_actual / sec_max * 100) if sec_max else 0,
        }

    band = "Emerging" if total < 40 else "Developing" if total < 70 else "Advanced"
    return {"total": total, "max": max_total, "pct": round(total / max_total * 100), "band": band, "sections": sections}


def get_submission_score(db: Session, submission_id: str) -> dict | None:
    if not db.query(Submission).filter(Submission.submission_id == submission_id).first():
        return None
    responses = db.query(Response).filter(Response.submission_id == submission_id).all()
    result = compute_score(responses)
    all_subs = db.query(Submission).all()
    all_pcts = []
    for sub in all_subs:
        r = db.query(Response).filter(Response.submission_id == sub.submission_id).all()
        all_pcts.append(compute_score(r)["pct"])
    n = len(all_pcts)
    below = sum(1 for p in all_pcts if p < result["pct"])
    result["percentile"] = round(below / n * 100) if n else 50
    result["population_size"] = n
    return result


def get_analytics_summary(db: Session) -> dict:
    total = db.query(func.count(Submission.submission_id)).scalar() or 0

    strategy_rows = db.query(Response).filter(Response.question_key == "ml_strategy").all()
    strategy_yes = sum(
        1 for r in strategy_rows
        if isinstance(r.answer_json, dict) and r.answer_json.get("value") is True
    )
    strategy_pct = round(strategy_yes / len(strategy_rows) * 100) if strategy_rows else 0

    ci_cd_rows = db.query(Response).filter(Response.question_key == "ci_cd_ml").all()
    ci_cd_yes = sum(
        1 for r in ci_cd_rows
        if isinstance(r.answer_json, dict) and r.answer_json.get("value") is True
    )
    ci_cd_pct = round(ci_cd_yes / len(ci_cd_rows) * 100) if ci_cd_rows else 0

    monitoring_rows = db.query(Response).filter(Response.question_key == "model_monitoring").all()
    monitoring_counts = [
        len(r.answer_json["value"])
        for r in monitoring_rows
        if isinstance(r.answer_json, dict) and isinstance(r.answer_json.get("value"), list)
    ]
    avg_monitoring = round(sum(monitoring_counts) / len(monitoring_counts), 1) if monitoring_counts else 0.0

    return {
        "total_submissions": total,
        "strategy_adoption_pct": strategy_pct,
        "ci_cd_adoption_pct": ci_cd_pct,
        "avg_monitoring_coverage": avg_monitoring,
    }


def get_all_submissions_with_scores(db: Session) -> list[dict]:
    submissions = db.query(Submission).order_by(Submission.submitted_at.desc()).all()
    result = []
    for sub in submissions:
        responses = db.query(Response).filter(Response.submission_id == sub.submission_id).all()
        s = compute_score(responses)
        result.append({
            "submission_id": sub.submission_id,
            "respondent_id": sub.respondent_id,
            "submitted_at": sub.submitted_at.isoformat(),
            "score": s["total"],
            "pct": s["pct"],
            "band": s["band"],
        })
    all_pcts = [r["pct"] for r in result]
    n = len(all_pcts)
    for r in result:
        below = sum(1 for p in all_pcts if p < r["pct"])
        r["percentile"] = round(below / n * 100) if n else 0
    return result


def get_response_distributions(db: Session) -> dict:
    QTYPES = {
        "ml_strategy": "boolean",
        "prod_scale": "single_select",
        "experiment_tracking": "single_select",
        "ci_cd_ml": "boolean",
        "serving_patterns": "multi_select",
        "model_monitoring": "multi_select",
    }
    result = {}
    for key, qtype in QTYPES.items():
        rows = db.query(Response).filter(Response.question_key == key).all()
        dist: dict[str, int] = {}
        for r in rows:
            if qtype == "boolean":
                val = r.answer_json.get("value") if isinstance(r.answer_json, dict) else None
                label = "Yes" if val is True else "No"
                dist[label] = dist.get(label, 0) + 1
            elif qtype == "single_select":
                label = r.answer_text or "No answer"
                dist[label] = dist.get(label, 0) + 1
            elif qtype == "multi_select":
                vals = r.answer_json.get("value", []) if isinstance(r.answer_json, dict) else []
                if isinstance(vals, list) and vals:
                    for v in vals:
                        dist[v] = dist.get(v, 0) + 1
                else:
                    dist["None selected"] = dist.get("None selected", 0) + 1
        result[key] = {"type": qtype, "n": len(rows), "distribution": dist}
    return result
