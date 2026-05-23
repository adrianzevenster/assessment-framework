select
  template_id,
  question_key,
  count(*) as responses,
  avg(answer_numeric) as avg_score,
  approx_distinct(respondent_id) as unique_respondents
from {{ ref('stg_fact_assessment_response') }}
group by 1, 2
