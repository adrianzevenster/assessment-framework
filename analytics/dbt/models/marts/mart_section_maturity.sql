with mapped as (
    select
        submission_id,
        respondent_id,
        template_id,
        answer_numeric,
        case
            when question_key = 'ai_strategy'     then 'Strategy'
            when question_key = 'streaming_stack' then 'Platform'
            when question_key = 'ml_maturity'     then 'Maturity'
            when question_key = 'obs_tools'       then 'Observability'
        end as section_key
    from {{ ref('stg_fact_assessment_response') }}
    where question_key in ('ai_strategy', 'streaming_stack', 'ml_maturity', 'obs_tools')
)
select
    template_id,
    section_key,
    count(distinct submission_id)  as submission_count,
    avg(answer_numeric)            as avg_score,
    min(answer_numeric)            as min_score,
    max(answer_numeric)            as max_score
from mapped
group by 1, 2
