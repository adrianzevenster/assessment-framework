from typing import Any, Literal

from pydantic import BaseModel, Field


class QuestionPayload(BaseModel):
    section_key: str
    question_key: str
    prompt: str
    question_type: Literal["text", "number", "single_select", "multi_select", "boolean", "rating"]
    required: bool = False
    options: list[dict[str, Any]] | None = None
    ordinal: int


class TemplateCreate(BaseModel):
    name: str
    version: int = 1
    status: str = "published"
    definition_json: dict[str, Any] = Field(default_factory=dict)
    questions: list[QuestionPayload]


class AnswerPayload(BaseModel):
    question_key: str
    answer_text: str | None = None
    answer_numeric: int | None = None
    answer_json: dict[str, Any] | list[Any] | None = None


class SubmissionCreate(BaseModel):
    template_id: str
    respondent_id: str
    channel: str = "virtual"
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    answers: list[AnswerPayload]
