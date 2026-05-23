from datetime import datetime
import ulid
from sqlalchemy.orm import Session

from app import models
from app.kafka import publish
from app.config import settings


def create_template(db: Session, payload):
    template = models.AssessmentTemplate(
        template_id=str(ulid.ULID()),
        name=payload.name,
        version=payload.version,
        status=payload.status,
        definition_json=payload.definition_json,
    )
    db.add(template)
    for question in payload.questions:
        db.add(models.Question(
            question_id=str(ulid.ULID()),
            template_id=template.template_id,
            section_key=question.section_key,
            question_key=question.question_key,
            prompt=question.prompt,
            question_type=question.question_type,
            required=question.required,
            options_json={"options": question.options} if question.options else None,
            ordinal=question.ordinal,
        ))
    db.commit()
    db.refresh(template)
    return template


def submit_assessment(db: Session, payload):
    submission = models.Submission(
        submission_id=str(ulid.ULID()),
        template_id=payload.template_id,
        respondent_id=payload.respondent_id,
        channel=payload.channel,
        metadata_json=payload.metadata_json,
    )
    db.add(submission)
    db.flush()

    response_events = []
    for answer in payload.answers:
        response = models.Response(
            response_id=str(ulid.ULID()),
            submission_id=submission.submission_id,
            question_key=answer.question_key,
            answer_text=answer.answer_text,
            answer_numeric=answer.answer_numeric,
            answer_json=answer.answer_json if isinstance(answer.answer_json, dict) else {"value": answer.answer_json},
            updated_at=datetime.utcnow(),
        )
        db.add(response)
        response_events.append({
            "event_type": "response_recorded",
            "event_time": datetime.utcnow().isoformat(),
            "submission_id": submission.submission_id,
            "template_id": payload.template_id,
            "respondent_id": payload.respondent_id,
            "question_key": answer.question_key,
            "answer_text": answer.answer_text,
            "answer_numeric": answer.answer_numeric,
            "answer_json": answer.answer_json,
        })

    db.commit()

    publish(settings.submission_topic, submission.submission_id, {
        "event_type": "assessment_submitted",
        "event_time": datetime.utcnow().isoformat(),
        "submission_id": submission.submission_id,
        "template_id": payload.template_id,
        "respondent_id": payload.respondent_id,
        "channel": payload.channel,
        "answer_count": len(payload.answers),
        "metadata": payload.metadata_json,
    })
    for event in response_events:
        publish(settings.response_topic, submission.submission_id, event)

    return submission
