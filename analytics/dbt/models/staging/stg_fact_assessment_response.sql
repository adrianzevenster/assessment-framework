select
  template_id,
  respondent_id,
  question_key,
  answer_text,
  cast(answer_numeric as integer) as answer_numeric,
  event_time
from demo.silver.fact_assessment_response
