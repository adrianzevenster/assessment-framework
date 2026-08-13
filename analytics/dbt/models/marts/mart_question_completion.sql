with submission_totals as (
    select template_id, count(distinct submission_id) as total_submissions
    from {{ ref('stg_fact_assessment_response') }}
    group by template_id
),
question_counts as (
    select
        template_id,
        question_key,
        count(distinct submission_id)                                              as response_count,
        count(distinct case when answer_numeric is not null then submission_id end) as numeric_response_count,
        count(distinct case when answer_text    is not null then submission_id end) as text_response_count,
        avg(answer_numeric)                                                        as avg_numeric_answer
    from {{ ref('stg_fact_assessment_response') }}
    group by 1, 2
)
select
    q.template_id,
    q.question_key,
    q.response_count,
    q.numeric_response_count,
    q.text_response_count,
    q.avg_numeric_answer,
    q.response_count * 1.0 / nullif(t.total_submissions, 0) as completion_rate
from question_counts q
join submission_totals t using (template_id)
