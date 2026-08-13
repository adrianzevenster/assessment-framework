with value_counts as (
    select
        template_id,
        question_key,
        answer_text,
        count(*) as cnt
    from {{ ref('stg_fact_assessment_response') }}
    where answer_text is not null
    group by 1, 2, 3
),
totals as (
    select template_id, question_key, sum(cnt) as total
    from value_counts
    group by 1, 2
),
probs as (
    select
        v.template_id,
        v.question_key,
        v.answer_text,
        v.cnt * 1.0 / t.total as p
    from value_counts v
    join totals t using (template_id, question_key)
)
select
    template_id,
    question_key,
    -sum(p * ln(p)) / ln(2)     as shannon_entropy_bits,
    count(distinct answer_text) as unique_values,
    sum(cnt)                    as total_responses
from probs
join value_counts using (template_id, question_key, answer_text)
group by 1, 2
