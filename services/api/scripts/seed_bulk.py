"""
Seeds 20 synthetic submissions covering the full maturity spectrum.
Run: docker compose exec -e PYTHONPATH=/app api python scripts/seed_bulk.py
"""
import random
from app.db import SessionLocal
from app.schemas import SubmissionCreate, AnswerPayload
from app.services import submit_assessment

TEMPLATE_ID = "01KX0J5J5C0V5JHKYXY9MXBZJJ"

PROFILES = [
    # (ml_strategy, prod_scale, experiment_tracking, ci_cd_ml, serving_patterns, model_monitoring)
    # High maturity
    (True,  "10+ models in production",  "MLflow + model registry",    True,  ["Real-time API (<100ms)", "Batch inference", "Streaming (Kafka / Redpanda)", "Shadow mode / A-B testing"], ["Data drift", "Prediction drift", "Latency / SLOs", "Feature quality", "Business KPIs"]),
    (True,  "10+ models in production",  "MLflow + model registry",    True,  ["Real-time API (<100ms)", "Batch inference", "Streaming (Kafka / Redpanda)"],                              ["Data drift", "Prediction drift", "Latency / SLOs", "Business KPIs"]),
    (True,  "10+ models in production",  "Weights & Biases / Neptune", True,  ["Real-time API (<100ms)", "Batch inference", "Edge / on-device"],                                         ["Data drift", "Latency / SLOs", "Feature quality", "Business KPIs"]),
    (True,  "1–9 models in production",  "MLflow + model registry",    True,  ["Real-time API (<100ms)", "Batch inference", "Streaming (Kafka / Redpanda)"],                              ["Data drift", "Prediction drift", "Latency / SLOs", "Feature quality"]),
    (True,  "1–9 models in production",  "MLflow + model registry",    True,  ["Batch inference", "Real-time API (<100ms)"],                                                              ["Data drift", "Latency / SLOs", "Business KPIs"]),
    (True,  "1–9 models in production",  "Weights & Biases / Neptune", True,  ["Real-time API (<100ms)", "Shadow mode / A-B testing"],                                                   ["Prediction drift", "Latency / SLOs", "Business KPIs"]),
    (True,  "10+ models in production",  "MLflow + model registry",    True,  ["Batch inference", "Streaming (Kafka / Redpanda)", "Edge / on-device"],                                   ["Data drift", "Feature quality", "Business KPIs"]),
    # Mid maturity
    (True,  "1–9 models in production",  "Custom solution",             False, ["Batch inference"],                                                                                       ["Data drift", "Business KPIs"]),
    (False, "1–9 models in production",  "MLflow + model registry",    False, ["Real-time API (<100ms)", "Batch inference"],                                                              ["Latency / SLOs", "Business KPIs"]),
    (True,  "Proof of concept / pilot",  "MLflow + model registry",    True,  ["Batch inference"],                                                                                       ["Data drift", "Prediction drift"]),
    (True,  "1–9 models in production",  "Custom solution",             True,  ["Batch inference", "Real-time API (<100ms)"],                                                             ["Data drift"]),
    (False, "1–9 models in production",  "Weights & Biases / Neptune", False, ["Batch inference"],                                                                                       ["Business KPIs"]),
    (True,  "Proof of concept / pilot",  "Custom solution",             False, ["Batch inference"],                                                                                       ["Data drift", "Latency / SLOs"]),
    # Low maturity
    (False, "Proof of concept / pilot",  "Notebooks / ad-hoc",          False, [],                                                                                                        []),
    (False, "Not yet deployed",          "Notebooks / ad-hoc",          False, [],                                                                                                        []),
    (True,  "Proof of concept / pilot",  "Notebooks / ad-hoc",          False, [],                                                                                                        ["Business KPIs"]),
    (False, "Proof of concept / pilot",  "Custom solution",             False, [],                                                                                                        []),
    (False, "Not yet deployed",          "Notebooks / ad-hoc",          False, [],                                                                                                        []),
    (True,  "Proof of concept / pilot",  "Notebooks / ad-hoc",          False, ["Batch inference"],                                                                                       ["Data drift"]),
    (False, "1–9 models in production",  "Notebooks / ad-hoc",          False, ["Batch inference"],                                                                                       ["Business KPIs"]),
]

with SessionLocal() as db:
    for i, (strategy, scale, tracking, ci_cd, serving, monitoring) in enumerate(PROFILES):
        payload = SubmissionCreate(
            template_id=TEMPLATE_ID,
            respondent_id=f"synthetic-org-{i+1:02d}",
            channel="virtual",
            metadata_json={"source": "seed_bulk"},
            answers=[
                AnswerPayload(question_key="ml_strategy",         answer_json={"value": strategy}),
                AnswerPayload(question_key="prod_scale",          answer_text=scale),
                AnswerPayload(question_key="experiment_tracking", answer_text=tracking),
                AnswerPayload(question_key="ci_cd_ml",            answer_json={"value": ci_cd}),
                AnswerPayload(question_key="serving_patterns",    answer_json={"value": serving}),
                AnswerPayload(question_key="model_monitoring",    answer_json={"value": monitoring}),
            ],
        )
        sub = submit_assessment(db, payload)
        print(f"  [{i+1:02d}] {sub.submission_id}  strategy={strategy} scale={scale[:20]:<20} ci_cd={ci_cd}")

print(f"\nSeeded {len(PROFILES)} synthetic submissions.")
