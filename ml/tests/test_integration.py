"""
Integration tests for the ML pipeline — feature building, labeling, and end-to-end smoke.

Requires a Postgres instance (set DATABASE_URL env var).
In CI a Postgres service container is provisioned automatically.

Run locally:
  DATABASE_URL=postgresql+psycopg://assessment:assessment@localhost:5433/assessment \
  pytest ml/tests/test_integration.py -v
"""
import json
import os

import numpy as np
import pytest
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://assessment:assessment@localhost:5433/assessment",
)

# ── Schema DDL (no FK constraints — test is self-contained) ──────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS assessment_templates (
    template_id     VARCHAR(26) PRIMARY KEY,
    name            TEXT        NOT NULL,
    version         INTEGER     NOT NULL DEFAULT 1,
    status          TEXT        NOT NULL DEFAULT 'published',
    definition_json JSONB,
    created_at      TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS submissions (
    submission_id VARCHAR(26) PRIMARY KEY,
    template_id   VARCHAR(26) NOT NULL,
    respondent_id TEXT        NOT NULL,
    channel       TEXT        NOT NULL DEFAULT 'virtual',
    metadata_json JSONB,
    status        TEXT        NOT NULL DEFAULT 'submitted',
    submitted_at  TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS responses (
    response_id   VARCHAR(26) PRIMARY KEY,
    submission_id VARCHAR(26) NOT NULL,
    question_key  TEXT        NOT NULL,
    answer_text   TEXT,
    answer_numeric INTEGER,
    answer_json   JSONB,
    updated_at    TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS labeled_outcomes (
    submission_id  VARCHAR(26) PRIMARY KEY,
    respondent_id  TEXT        NOT NULL,
    template_id    VARCHAR(26) NOT NULL,
    high_readiness SMALLINT    NOT NULL,
    labeled_at     TIMESTAMP   NOT NULL DEFAULT now()
);
"""

_TEARDOWN = """
DROP TABLE IF EXISTS labeled_outcomes;
DROP TABLE IF EXISTS responses;
DROP TABLE IF EXISTS submissions;
DROP TABLE IF EXISTS assessment_templates;
"""


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DATABASE_URL)
    with eng.begin() as conn:
        conn.execute(text(_DDL))
    yield eng
    with eng.begin() as conn:
        conn.execute(text(_TEARDOWN))


@pytest.fixture(autouse=True)
def clean(engine):
    """Wipe rows between tests (DDL stays in place)."""
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM labeled_outcomes"))
        conn.execute(text("DELETE FROM responses"))
        conn.execute(text("DELETE FROM submissions"))
        conn.execute(text("DELETE FROM assessment_templates"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _seed(
    engine,
    submission_id: str = "sub-0001",
    respondent_id: str = "org-001",
    template_id: str = "tmpl-0001",
    responses: list | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO assessment_templates (template_id, name, definition_json)
            VALUES (:tid, 'Integration Test Template', '{}')
            ON CONFLICT DO NOTHING
        """), {"tid": template_id})
        conn.execute(text("""
            INSERT INTO submissions (submission_id, template_id, respondent_id)
            VALUES (:sid, :tid, :rid)
            ON CONFLICT DO NOTHING
        """), {"sid": submission_id, "tid": template_id, "rid": respondent_id})
        for i, r in enumerate(responses or []):
            conn.execute(text("""
                INSERT INTO responses (response_id, submission_id, question_key, answer_text, answer_json)
                VALUES (:rid, :sid, :key, :text, :json::jsonb)
                ON CONFLICT DO NOTHING
            """), {
                "rid":  f"{submission_id}-r{i}",
                "sid":  submission_id,
                "key":  r["question_key"],
                "text": r.get("answer_text"),
                "json": json.dumps(r["answer_json"]) if r.get("answer_json") is not None else None,
            })


def _high_readiness_responses() -> list[dict]:
    return [
        {"question_key": "ml_strategy",         "answer_json":  {"value": True}},
        {"question_key": "ci_cd_ml",             "answer_json":  {"value": True}},
        {"question_key": "model_monitoring",     "answer_json":  {"value": ["Data drift", "Latency / SLOs"]}},
        {"question_key": "prod_scale",           "answer_text":  "1–9 models in production"},
        {"question_key": "experiment_tracking",  "answer_text":  "MLflow + model registry"},
        {"question_key": "serving_patterns",     "answer_json":  {"value": ["Real-time API (<100ms)", "Batch inference"]}},
    ]


def _low_readiness_responses() -> list[dict]:
    return [
        {"question_key": "ci_cd_ml",         "answer_json": {"value": False}},
        {"question_key": "model_monitoring",  "answer_json": {"value": ["Data drift"]}},
        {"question_key": "prod_scale",        "answer_text": "Not yet deployed"},
    ]


# ── Feature pipeline tests ────────────────────────────────────────────────────

class TestBuildFeatureFrame:
    def test_empty_db_returns_empty_frame(self, engine):
        from ml.features.feature_pipeline import build_feature_frame
        frame = build_feature_frame(engine)
        assert frame.empty

    def test_all_feature_cols_present(self, engine):
        from ml.features.extractor import FEATURE_COLS
        from ml.features.feature_pipeline import build_feature_frame
        _seed(engine)
        frame = build_feature_frame(engine)
        for col in FEATURE_COLS:
            assert col in frame.columns, f"Missing column: {col}"

    def test_high_readiness_features_encoded_correctly(self, engine):
        from ml.features.feature_pipeline import build_feature_frame
        _seed(engine, responses=_high_readiness_responses())
        frame = build_feature_frame(engine)
        assert len(frame) == 1
        row = frame.iloc[0]
        assert row["has_ml_strategy"] == 1
        assert row["has_ci_cd"] == 1
        assert row["monitoring_count"] == 2
        assert row["prod_scale_score"] == 2
        assert row["experiment_tracking_score"] == 3
        assert row["serving_pattern_count"] == 2
        assert row["answered_question_count"] == 6

    def test_low_readiness_features_encoded_correctly(self, engine):
        from ml.features.feature_pipeline import build_feature_frame
        _seed(engine, responses=_low_readiness_responses())
        frame = build_feature_frame(engine)
        row = frame.iloc[0]
        assert row["has_ci_cd"] == 0
        assert row["monitoring_count"] == 1
        assert row["prod_scale_score"] == 0

    def test_no_responses_all_zeros(self, engine):
        from ml.features.extractor import FEATURE_COLS
        from ml.features.feature_pipeline import build_feature_frame
        _seed(engine, responses=[])
        frame = build_feature_frame(engine)
        assert len(frame) == 1
        for col in FEATURE_COLS:
            assert frame.iloc[0][col] == 0

    def test_respondent_submission_count_aggregated(self, engine):
        from ml.features.feature_pipeline import build_feature_frame
        for i in range(3):
            _seed(engine, submission_id=f"sub-{i:04d}", respondent_id="org-repeat")
        frame = build_feature_frame(engine)
        assert len(frame) == 3
        assert (frame["respondent_submission_count"] == 3).all()

    def test_multiple_respondents_independent(self, engine):
        from ml.features.feature_pipeline import build_feature_frame
        _seed(engine, submission_id="sub-0001", respondent_id="org-A")
        _seed(engine, submission_id="sub-0002", respondent_id="org-B")
        frame = build_feature_frame(engine)
        assert len(frame) == 2
        assert (frame["respondent_submission_count"] == 1).all()


# ── Labeling tests ────────────────────────────────────────────────────────────

class TestGenerateLabels:
    def test_high_readiness_all_conditions_met(self, engine):
        from ml.features.feature_pipeline import build_feature_frame
        from ml.outcomes.labeled_outcomes import generate_labels
        _seed(engine, responses=_high_readiness_responses())
        frame = build_feature_frame(engine)
        labels = generate_labels(frame)
        assert labels.iloc[0]["high_readiness"] == 1

    def test_low_readiness_no_cicd(self, engine):
        from ml.features.feature_pipeline import build_feature_frame
        from ml.outcomes.labeled_outcomes import generate_labels
        _seed(engine, responses=_low_readiness_responses())
        frame = build_feature_frame(engine)
        labels = generate_labels(frame)
        assert labels.iloc[0]["high_readiness"] == 0

    def test_low_readiness_insufficient_monitoring(self, engine):
        from ml.features.feature_pipeline import build_feature_frame
        from ml.outcomes.labeled_outcomes import generate_labels
        _seed(engine, responses=[
            {"question_key": "ci_cd_ml",        "answer_json": {"value": True}},
            {"question_key": "model_monitoring", "answer_json": {"value": ["Data drift"]}},  # only 1
            {"question_key": "prod_scale",       "answer_text": "1–9 models in production"},
        ])
        frame = build_feature_frame(engine)
        labels = generate_labels(frame)
        assert labels.iloc[0]["high_readiness"] == 0

    def test_low_readiness_not_in_prod(self, engine):
        from ml.features.feature_pipeline import build_feature_frame
        from ml.outcomes.labeled_outcomes import generate_labels
        _seed(engine, responses=[
            {"question_key": "ci_cd_ml",        "answer_json": {"value": True}},
            {"question_key": "model_monitoring", "answer_json": {"value": ["A", "B"]}},
            {"question_key": "prod_scale",       "answer_text": "Not yet deployed"},
        ])
        frame = build_feature_frame(engine)
        labels = generate_labels(frame)
        assert labels.iloc[0]["high_readiness"] == 0

    def test_upsert_idempotent(self, engine):
        from ml.features.feature_pipeline import build_feature_frame
        from ml.outcomes.labeled_outcomes import generate_labels, upsert_labels
        _seed(engine)
        frame = build_feature_frame(engine)
        labels = generate_labels(frame)
        upsert_labels(engine, labels)
        upsert_labels(engine, labels)  # must not raise or duplicate
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM labeled_outcomes")).scalar()
        assert count == 1

    def test_label_update_on_conflict(self, engine):
        from ml.features.feature_pipeline import build_feature_frame
        from ml.outcomes.labeled_outcomes import generate_labels, upsert_labels
        _seed(engine, responses=_high_readiness_responses())
        frame = build_feature_frame(engine)
        labels = generate_labels(frame)
        labels.at[labels.index[0], "high_readiness"] = 0  # force low
        upsert_labels(engine, labels)
        labels.at[labels.index[0], "high_readiness"] = 1  # flip back to high
        upsert_labels(engine, labels)
        with engine.connect() as conn:
            val = conn.execute(text(
                "SELECT high_readiness FROM labeled_outcomes WHERE submission_id = :sid"
            ), {"sid": frame.iloc[0]["submission_id"]}).scalar()
        assert val == 1


# ── End-to-end pipeline smoke ─────────────────────────────────────────────────

class TestPipelineEndToEnd:
    def test_features_labels_train_smoke(self, engine):
        """Seed → features → labels → train a minimal model without errors."""
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        from ml.features.extractor import FEATURE_COLS
        from ml.features.feature_pipeline import build_feature_frame
        from ml.outcomes.labeled_outcomes import generate_labels, upsert_labels

        for i in range(20):
            has_cicd   = i % 2 == 0
            monitoring = ["A", "B", "C"] if i % 3 == 0 else ["A"]
            prod_scale = "1–9 models in production" if has_cicd else "Not yet deployed"
            _seed(
                engine,
                submission_id=f"sub-{i:04d}",
                respondent_id=f"org-{i:04d}",
                responses=[
                    {"question_key": "ci_cd_ml",        "answer_json": {"value": has_cicd}},
                    {"question_key": "model_monitoring", "answer_json": {"value": monitoring}},
                    {"question_key": "prod_scale",       "answer_text": prod_scale},
                ],
            )

        frame = build_feature_frame(engine)
        assert len(frame) == 20

        labels = generate_labels(frame)
        upsert_labels(engine, labels)

        merged = frame.merge(labels[["submission_id", "high_readiness"]], on="submission_id")
        X = merged[FEATURE_COLS].fillna(0).values
        y = merged["high_readiness"].values

        assert y.sum() > 0, "No positive labels — label rule may not match seeded data"
        assert y.sum() < len(y), "All positive labels — class imbalance too severe for smoke test"

        model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500, class_weight="balanced", random_state=42)),
        ])
        model.fit(X, y)
        preds = model.predict(X)
        proba = model.predict_proba(X)

        assert len(preds) == 20
        assert set(preds).issubset({0, 1})
        assert proba.shape == (20, 2)
        assert np.allclose(proba.sum(axis=1), 1.0)
        assert model.n_features_in_ == len(FEATURE_COLS)

    def test_label_quality_gate_passes(self, engine):
        from ml.checks.label_quality import run_checks
        from ml.features.feature_pipeline import build_feature_frame
        from ml.outcomes.labeled_outcomes import generate_labels, upsert_labels

        for i in range(15):
            has_cicd   = i % 2 == 0
            monitoring = ["A", "B"] if has_cicd else ["A"]
            prod       = "1–9 models in production" if has_cicd else "Not yet deployed"
            _seed(
                engine,
                submission_id=f"sub-{i:04d}",
                respondent_id=f"org-{i:04d}",
                responses=[
                    {"question_key": "ci_cd_ml",        "answer_json": {"value": has_cicd}},
                    {"question_key": "model_monitoring", "answer_json": {"value": monitoring}},
                    {"question_key": "prod_scale",       "answer_text": prod},
                ],
            )

        frame = build_feature_frame(engine)
        labels = generate_labels(frame)
        upsert_labels(engine, labels)

        failures = run_checks(engine)
        assert failures == [], f"Label quality gate failed: {failures}"
