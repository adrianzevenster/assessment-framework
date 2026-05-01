from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AssessmentTemplate(Base):
    __tablename__ = "assessment_templates"

    template_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    definition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    questions = relationship("Question", back_populates="template", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("template_id", "question_key", name="uq_question_template_key"),)

    question_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("assessment_templates.template_id"), nullable=False)
    section_key: Mapped[str] = mapped_column(String(120), nullable=False)
    question_key: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(50), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    options_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    template = relationship("AssessmentTemplate", back_populates="questions")


class Submission(Base):
    __tablename__ = "submissions"

    submission_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("assessment_templates.template_id"), nullable=False)
    respondent_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="submitted")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="virtual")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Response(Base):
    __tablename__ = "responses"
    __table_args__ = (UniqueConstraint("submission_id", "question_key", name="uq_submission_question"),)

    response_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.submission_id"), nullable=False)
    question_key: Mapped[str] = mapped_column(String(120), nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_numeric: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
