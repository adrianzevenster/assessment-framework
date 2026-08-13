"""Unit tests for canonical feature extraction — no database required."""
import pytest

from ml.features.extractor import (
    FEATURE_COLS,
    build_full_feature_dict,
    compute_label,
    extract_features_from_dict,
    features_to_vector,
)


def _r(question_key, answer_text=None, answer_json=None):
    return {"question_key": question_key, "answer_text": answer_text, "answer_json": answer_json}


class TestExtractFeaturesFromDict:
    def test_empty_responses_all_zeros(self):
        feat = extract_features_from_dict([])
        assert feat["has_ml_strategy"] == 0
        assert feat["has_ci_cd"] == 0
        assert feat["serving_pattern_count"] == 0
        assert feat["monitoring_count"] == 0
        assert feat["experiment_tracking_score"] == 0
        assert feat["prod_scale_score"] == 0
        assert feat["answered_question_count"] == 0

    def test_boolean_true(self):
        feat = extract_features_from_dict([_r("ml_strategy", answer_json={"value": True})])
        assert feat["has_ml_strategy"] == 1

    def test_boolean_false(self):
        feat = extract_features_from_dict([_r("ml_strategy", answer_json={"value": False})])
        assert feat["has_ml_strategy"] == 0

    def test_boolean_none_json(self):
        feat = extract_features_from_dict([_r("ml_strategy", answer_json=None)])
        assert feat["has_ml_strategy"] == 0

    def test_multiselect_count(self):
        feat = extract_features_from_dict([
            _r("serving_patterns", answer_json={"value": ["API", "Batch", "Stream"]})
        ])
        assert feat["serving_pattern_count"] == 3

    def test_multiselect_empty_list(self):
        feat = extract_features_from_dict([_r("serving_patterns", answer_json={"value": []})])
        assert feat["serving_pattern_count"] == 0

    def test_categorical_mlflow(self):
        feat = extract_features_from_dict([
            _r("experiment_tracking", answer_text="MLflow + model registry")
        ])
        assert feat["experiment_tracking_score"] == 3

    def test_categorical_wandb(self):
        feat = extract_features_from_dict([
            _r("experiment_tracking", answer_text="Weights & Biases / Neptune")
        ])
        assert feat["experiment_tracking_score"] == 2

    def test_categorical_unknown_maps_to_zero(self):
        feat = extract_features_from_dict([
            _r("experiment_tracking", answer_text="something unknown")
        ])
        assert feat["experiment_tracking_score"] == 0

    def test_prod_scale_score_high(self):
        feat = extract_features_from_dict([
            _r("prod_scale", answer_text="10+ models in production")
        ])
        assert feat["prod_scale_score"] == 3

    def test_answered_question_count(self):
        feat = extract_features_from_dict([
            _r("ml_strategy", answer_json={"value": True}),
            _r("ci_cd_ml", answer_json={"value": True}),
            _r("prod_scale", answer_text="1–9 models in production"),
        ])
        assert feat["answered_question_count"] == 3

    def test_features_to_vector_length_and_order(self):
        feat = extract_features_from_dict([
            _r("ml_strategy", answer_json={"value": True}),
            _r("ci_cd_ml", answer_json={"value": True}),
            _r("serving_patterns", answer_json={"value": ["API", "Batch"]}),
            _r("model_monitoring", answer_json={"value": ["Data drift"]}),
            _r("experiment_tracking", answer_text="Custom solution"),
            _r("prod_scale", answer_text="1–9 models in production"),
        ])
        vec = features_to_vector(feat)
        assert len(vec) == len(FEATURE_COLS)
        assert vec[FEATURE_COLS.index("has_ml_strategy")] == 1
        assert vec[FEATURE_COLS.index("has_ci_cd")] == 1
        assert vec[FEATURE_COLS.index("serving_pattern_count")] == 2
        assert vec[FEATURE_COLS.index("monitoring_count")] == 1
        assert vec[FEATURE_COLS.index("experiment_tracking_score")] == 1
        assert vec[FEATURE_COLS.index("prod_scale_score")] == 2
        assert vec[FEATURE_COLS.index("answered_question_count")] == 6


class TestBuildFullFeatureDict:
    def test_merges_submission_level_features(self):
        resp_feats = extract_features_from_dict([
            _r("ml_strategy", answer_json={"value": True}),
            _r("ci_cd_ml",    answer_json={"value": True}),
        ])
        full = build_full_feature_dict(resp_feats, respondent_submission_count=3, days_since_first_submission=14)
        assert full["has_ml_strategy"] == 1
        assert full["has_ci_cd"] == 1
        assert full["respondent_submission_count"] == 3
        assert full["days_since_first_submission"] == 14

    def test_defaults_to_one_and_zero(self):
        resp_feats = extract_features_from_dict([])
        full = build_full_feature_dict(resp_feats)
        assert full["respondent_submission_count"] == 1
        assert full["days_since_first_submission"] == 0

    def test_full_dict_feeds_features_to_vector(self):
        resp_feats = extract_features_from_dict([
            _r("ml_strategy", answer_json={"value": True}),
            _r("prod_scale",  answer_text="10+ models in production"),
        ])
        full = build_full_feature_dict(resp_feats, respondent_submission_count=5, days_since_first_submission=30)
        vec = features_to_vector(full)
        assert len(vec) == len(FEATURE_COLS)
        assert vec[FEATURE_COLS.index("respondent_submission_count")] == 5
        assert vec[FEATURE_COLS.index("days_since_first_submission")] == 30
        assert vec[FEATURE_COLS.index("prod_scale_score")] == 3

    def test_features_to_vector_tolerates_partial_dict(self):
        # extract_features_from_dict only returns 7 keys; features_to_vector should default missing to 0
        resp_feats = extract_features_from_dict([_r("ml_strategy", answer_json={"value": True})])
        vec = features_to_vector(resp_feats)
        assert len(vec) == len(FEATURE_COLS)
        assert vec[FEATURE_COLS.index("respondent_submission_count")] == 0
        assert vec[FEATURE_COLS.index("days_since_first_submission")] == 0


class TestComputeLabel:
    def _high_feat(self):
        return {
            "has_ci_cd": 1, "monitoring_count": 2, "prod_scale_score": 2,
            "has_ml_strategy": 1, "serving_pattern_count": 3,
            "experiment_tracking_score": 3, "answered_question_count": 6,
        }

    def test_high_readiness(self):
        assert compute_label(self._high_feat()) == 1

    def test_no_cicd(self):
        feat = {**self._high_feat(), "has_ci_cd": 0}
        assert compute_label(feat) == 0

    def test_insufficient_monitoring(self):
        feat = {**self._high_feat(), "monitoring_count": 1}
        assert compute_label(feat) == 0

    def test_not_in_production(self):
        feat = {**self._high_feat(), "prod_scale_score": 1}
        assert compute_label(feat) == 0

    def test_boundary_monitoring_exactly_two(self):
        feat = {**self._high_feat(), "monitoring_count": 2}
        assert compute_label(feat) == 1

    def test_boundary_prod_scale_exactly_two(self):
        feat = {**self._high_feat(), "prod_scale_score": 2}
        assert compute_label(feat) == 1


class TestModelSmoke:
    def test_sklearn_pipeline_fits_and_predicts(self):
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        rng = np.random.RandomState(42)
        n = 30
        X = rng.randint(0, 4, size=(n, len(FEATURE_COLS)))
        y = (X[:, 0] + X[:, 1] > 1).astype(int)

        model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500, random_state=42)),
        ])
        model.fit(X, y)
        preds = model.predict(X)
        proba = model.predict_proba(X)

        assert len(preds) == n
        assert proba.shape == (n, 2)
        assert set(preds).issubset({0, 1})
        assert model.n_features_in_ == len(FEATURE_COLS)

    def test_feature_vector_feeds_model(self):
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        from ml.features.extractor import build_full_feature_dict, extract_features_from_dict, features_to_vector

        rng = np.random.RandomState(1)
        X_train = rng.randint(0, 4, size=(20, len(FEATURE_COLS)))
        y_train = rng.randint(0, 2, size=20)

        model = Pipeline([("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=200))])
        model.fit(X_train, y_train)

        resp_feats = extract_features_from_dict([
            {"question_key": "ml_strategy", "answer_text": None, "answer_json": {"value": True}},
            {"question_key": "ci_cd_ml",    "answer_text": None, "answer_json": {"value": True}},
            {"question_key": "prod_scale",  "answer_text": "1–9 models in production", "answer_json": None},
        ])
        feat = build_full_feature_dict(resp_feats, respondent_submission_count=1, days_since_first_submission=0)
        vec = features_to_vector(feat)
        X = np.array([vec])
        prob = model.predict_proba(X)
        assert prob.shape == (1, 2)
        assert abs(prob[0].sum() - 1.0) < 1e-6
