from app.db import SessionLocal
from app.schemas import TemplateCreate, QuestionPayload
from app.services import create_template

payload = TemplateCreate(
    name="AI Readiness Assessment",
    version=1,
    status="published",
    definition_json={"description": "Sample principal-engineering assessment"},
    questions=[
        QuestionPayload(section_key="strategy", question_key="ai_strategy", prompt="Do you have an AI strategy?", question_type="boolean", required=True, ordinal=1),
        QuestionPayload(section_key="platform", question_key="streaming_stack", prompt="Which streaming stack do you use?", question_type="single_select", required=True, ordinal=2, options=[{"label": "Kafka"}, {"label": "Redpanda"}, {"label": "Other"}]),
        QuestionPayload(section_key="maturity", question_key="ml_maturity", prompt="Rate your ML maturity", question_type="rating", required=True, ordinal=3),
    ],
)

with SessionLocal() as db:
    template = create_template(db, payload)
    print({"template_id": template.template_id})
