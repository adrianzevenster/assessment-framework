select
    submission_id,
    template_id,
    respondent_id,
    channel,
    answer_count,
    cast(event_time as timestamp) as event_time
from demo.silver.fact_assessment_submission
