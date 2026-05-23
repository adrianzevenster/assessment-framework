CREATE TABLE IF NOT EXISTS demo.gold.question_response_summary AS
SELECT
    template_id,
    question_key,
    count(*) AS response_count,
    avg(answer_numeric) AS avg_numeric_answer
FROM demo.silver.fact_assessment_response
GROUP BY 1, 2;
