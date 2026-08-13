CREATE NAMESPACE IF NOT EXISTS demo.gold;

CREATE TABLE IF NOT EXISTS demo.gold.respondent_velocity AS
SELECT
    respondent_id,
    template_id,
    count(DISTINCT submission_id)                      AS submission_count,
    min(cast(event_time AS timestamp))                 AS first_submission_at,
    max(cast(event_time AS timestamp))                 AS last_submission_at,
    datediff(
        max(cast(event_time AS timestamp)),
        min(cast(event_time AS timestamp))
    )                                                  AS days_active
FROM demo.silver.fact_assessment_submission
GROUP BY 1, 2;

CREATE TABLE IF NOT EXISTS demo.gold.question_response_summary AS
SELECT
    template_id,
    question_key,
    count(*)                                                    AS response_count,
    count(CASE WHEN answer_numeric IS NOT NULL THEN 1 END)      AS numeric_response_count,
    avg(answer_numeric)                                         AS avg_numeric_answer,
    min(answer_numeric)                                         AS min_numeric_answer,
    max(answer_numeric)                                         AS max_numeric_answer,
    count(CASE WHEN answer_text IS NOT NULL THEN 1 END)         AS text_response_count
FROM demo.silver.fact_assessment_response
GROUP BY 1, 2;

CREATE TABLE IF NOT EXISTS demo.gold.section_maturity AS
SELECT
    template_id,
    CASE
        WHEN question_key = 'ml_strategy'          THEN 'Strategy'
        WHEN question_key = 'serving_patterns'     THEN 'Production'
        WHEN question_key = 'experiment_tracking'  THEN 'MLOps'
        WHEN question_key = 'model_monitoring'     THEN 'Observability'
        ELSE                                            'Other'
    END                                        AS section_key,
    count(DISTINCT submission_id)              AS submission_count,
    avg(answer_numeric)                        AS avg_score,
    stddev(answer_numeric)                     AS stddev_score
FROM demo.silver.fact_assessment_response
WHERE question_key IN ('ml_strategy', 'serving_patterns', 'experiment_tracking', 'model_monitoring')
GROUP BY 1, 2;

CREATE TABLE IF NOT EXISTS demo.gold.answer_diversity AS
SELECT
    template_id,
    question_key,
    count(DISTINCT answer_text)   AS unique_text_answers,
    count(*)                      AS total_responses,
    count(DISTINCT answer_text) * 1.0 / nullif(count(*), 0) AS diversity_ratio
FROM demo.silver.fact_assessment_response
WHERE answer_text IS NOT NULL
GROUP BY 1, 2;

-- ML feature table: column names and encoding match ml/features/extractor.py::FEATURE_COLS exactly.
-- Used by feature_pipeline.py --source trino and mart_ml_features dbt model.
CREATE TABLE IF NOT EXISTS demo.gold.ml_features AS
WITH respondent_stats AS (
    SELECT
        respondent_id,
        template_id,
        count(DISTINCT submission_id)      AS respondent_submission_count,
        min(cast(event_time AS timestamp)) AS first_submission_at
    FROM demo.silver.fact_assessment_submission
    GROUP BY 1, 2
)
SELECT
    s.submission_id,
    s.respondent_id,
    s.template_id,
    cast(s.event_time AS timestamp)                                                AS submitted_at,
    max(CASE WHEN r.question_key = 'ml_strategy'
             AND get_json_object(r.answer_json, '$.value') = 'true' THEN 1 ELSE 0 END) AS has_ml_strategy,
    max(CASE WHEN r.question_key = 'ci_cd_ml'
             AND get_json_object(r.answer_json, '$.value') = 'true' THEN 1 ELSE 0 END) AS has_ci_cd,
    max(CASE WHEN r.question_key = 'experiment_tracking' THEN
        CASE r.answer_text
            WHEN 'MLflow + model registry'    THEN 3
            WHEN 'Weights & Biases / Neptune' THEN 2
            WHEN 'Custom solution'             THEN 1
            ELSE 0
        END
    END)                                                                           AS experiment_tracking_score,
    max(CASE WHEN r.question_key = 'prod_scale' THEN
        CASE r.answer_text
            WHEN '10+ models in production' THEN 3
            WHEN '1–9 models in production' THEN 2
            WHEN 'Proof of concept / pilot'  THEN 1
            ELSE 0
        END
    END)                                                                           AS prod_scale_score,
    max(CASE WHEN r.question_key = 'serving_patterns'
        THEN size(from_json(get_json_object(r.answer_json, '$.value'), 'array<string>'))
        ELSE 0 END)                                                                AS serving_pattern_count,
    max(CASE WHEN r.question_key = 'model_monitoring'
        THEN size(from_json(get_json_object(r.answer_json, '$.value'), 'array<string>'))
        ELSE 0 END)                                                                AS monitoring_count,
    count(DISTINCT r.question_key)                                                 AS answered_question_count,
    coalesce(rs.respondent_submission_count, 1)                                    AS respondent_submission_count,
    coalesce(
        datediff(cast(s.event_time AS timestamp), rs.first_submission_at), 0
    )                                                                              AS days_since_first_submission
FROM demo.silver.fact_assessment_submission s
LEFT JOIN demo.silver.fact_assessment_response r ON s.submission_id = r.submission_id
LEFT JOIN respondent_stats rs
       ON s.respondent_id = rs.respondent_id AND s.template_id = rs.template_id
GROUP BY 1, 2, 3, 4, rs.respondent_submission_count, rs.first_submission_at;
