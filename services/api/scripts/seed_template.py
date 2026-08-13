from app.db import SessionLocal
from app.schemas import TemplateCreate, QuestionPayload
from app.services import create_template

payload = TemplateCreate(
    name="Staff ML Engineer — Org Readiness Assessment",
    version=2,
    status="published",
    definition_json={"description": "Evaluates an organisation's ML maturity across strategy, production, MLOps, and observability dimensions."},
    questions=[
        QuestionPayload(
            section_key="strategy", question_key="ml_strategy",
            prompt="Does your organisation have a documented ML/AI strategy with executive sponsorship?",
            question_type="boolean", required=True, ordinal=1,
        ),
        QuestionPayload(
            section_key="production", question_key="prod_scale",
            prompt="How many ML models does your organisation currently have in production?",
            question_type="single_select", required=True, ordinal=2,
            options=[
                {"label": "10+ models in production"},
                {"label": "1–9 models in production"},
                {"label": "Proof of concept / pilot"},
                {"label": "Not yet deployed"},
            ],
        ),
        QuestionPayload(
            section_key="mlops", question_key="experiment_tracking",
            prompt="How does your team track ML experiments and model lineage?",
            question_type="single_select", required=True, ordinal=3,
            options=[
                {"label": "MLflow + model registry"},
                {"label": "Weights & Biases / Neptune"},
                {"label": "Custom solution"},
                {"label": "Notebooks / ad-hoc"},
            ],
        ),
        QuestionPayload(
            section_key="mlops", question_key="ci_cd_ml",
            prompt="Do you have CI/CD pipelines for automated model training, validation, and deployment?",
            question_type="boolean", required=True, ordinal=4,
        ),
        QuestionPayload(
            section_key="production", question_key="serving_patterns",
            prompt="Which model serving patterns are currently in production? (select all that apply)",
            question_type="multi_select", required=False, ordinal=5,
            options=[
                {"label": "Real-time API (<100ms)"},
                {"label": "Batch inference"},
                {"label": "Streaming (Kafka / Redpanda)"},
                {"label": "Edge / on-device"},
                {"label": "Shadow mode / A-B testing"},
            ],
        ),
        QuestionPayload(
            section_key="observability", question_key="model_monitoring",
            prompt="What do you actively monitor for models in production? (select all that apply)",
            question_type="multi_select", required=False, ordinal=6,
            options=[
                {"label": "Data drift"},
                {"label": "Prediction drift"},
                {"label": "Latency / SLOs"},
                {"label": "Feature quality"},
                {"label": "Business KPIs"},
            ],
        ),
        QuestionPayload(
            section_key="general", question_key="notes",
            prompt="Anything else to capture? (team structure, key blockers, roadmap priorities...)",
            question_type="text", required=False, ordinal=7,
        ),
    ],
)

with SessionLocal() as db:
    template = create_template(db, payload)
    print({"template_id": template.template_id})
