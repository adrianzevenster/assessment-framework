select
    submission_id,
    template_id,
    respondent_id,
    question_key,
    answer_text,
    cast(answer_numeric as integer) as answer_numeric,
    cast(event_time as timestamp)   as event_time
from demo.silver.fact_assessment_response
