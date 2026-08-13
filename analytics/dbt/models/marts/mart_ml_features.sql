{{
  config(
    materialized='incremental',
    unique_key='submission_id'
  )
}}

-- Offline feature store: point-in-time feature snapshot for ML training.
-- Mirrors ml/features/extractor.py::FEATURE_COLS (all 9 columns).
-- Source: Iceberg Gold (populated by Spark jobs/build_gold_views.sql).
-- Consumed by: feature_pipeline.py --source trino.
select
    submission_id,
    respondent_id,
    template_id,
    submitted_at,
    coalesce(has_ml_strategy,             0) as has_ml_strategy,
    coalesce(has_ci_cd,                   0) as has_ci_cd,
    coalesce(serving_pattern_count,       0) as serving_pattern_count,
    coalesce(monitoring_count,            0) as monitoring_count,
    coalesce(experiment_tracking_score,   0) as experiment_tracking_score,
    coalesce(prod_scale_score,            0) as prod_scale_score,
    coalesce(answered_question_count,     0) as answered_question_count,
    coalesce(respondent_submission_count, 1) as respondent_submission_count,
    coalesce(days_since_first_submission, 0) as days_since_first_submission
from demo.gold.ml_features

{% if is_incremental() %}
where submitted_at > (select max(submitted_at) from {{ this }})
{% endif %}
