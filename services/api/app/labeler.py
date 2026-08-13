"""
Real-time auto-labelling: computes and upserts a readiness label after each submission.
Runs as a FastAPI BackgroundTask so it never blocks the POST /submissions response.

Label rule is defined in ml/features/extractor.py::compute_label.
Imports from ml/ via the ./ml:/app/ml volume mount (see docker-compose.yml).
"""
import logging

from sqlalchemy import text

from app.db import SessionLocal
from app.models import Response, Submission

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS labeled_outcomes (
    submission_id   VARCHAR(26) PRIMARY KEY,
    respondent_id   TEXT        NOT NULL,
    template_id     VARCHAR(26) NOT NULL,
    high_readiness  SMALLINT    NOT NULL,
    labeled_at      TIMESTAMP   NOT NULL DEFAULT now()
);
"""


def label_submission(submission_id: str) -> None:
    """Compute and upsert the readiness label for a single submission."""
    try:
        from ml.features.extractor import compute_label, extract_features_from_dict
    except ImportError:
        logger.warning("ml.features.extractor not available (volume not mounted?); skipping auto-label")
        return

    with SessionLocal() as db:
        sub = db.query(Submission).filter(Submission.submission_id == submission_id).first()
        if not sub:
            return

        db.execute(text(_CREATE_TABLE))
        db.commit()

        responses = db.query(Response).filter(Response.submission_id == submission_id).all()
        response_dicts = [
            {
                "question_key": r.question_key,
                "answer_text":  r.answer_text,
                "answer_json":  r.answer_json,
            }
            for r in responses
        ]
        feat = extract_features_from_dict(response_dicts)
        high_readiness = compute_label(feat)

        db.execute(
            text("""
                INSERT INTO labeled_outcomes (submission_id, respondent_id, template_id, high_readiness)
                VALUES (:sid, :rid, :tid, :label)
                ON CONFLICT (submission_id)
                DO UPDATE SET high_readiness = EXCLUDED.high_readiness, labeled_at = now()
            """),
            {
                "sid":   sub.submission_id,
                "rid":   sub.respondent_id,
                "tid":   sub.template_id,
                "label": high_readiness,
            },
        )
        db.commit()
        logger.debug("Auto-labeled %s → high_readiness=%d", submission_id, high_readiness)
