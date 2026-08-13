select
    respondent_id,
    template_id,
    count(distinct submission_id)                       as submission_count,
    min(event_time)                                     as first_submission_at,
    max(event_time)                                     as last_submission_at,
    date_diff('day', min(event_time), max(event_time))  as days_active
from {{ ref('stg_fact_assessment_response') }}
group by 1, 2
