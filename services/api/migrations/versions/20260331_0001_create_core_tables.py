"""create core tables"""

from alembic import op
import sqlalchemy as sa

revision = "20260331_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assessment_templates",
        sa.Column("template_id", sa.String(length=26), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "questions",
        sa.Column("question_id", sa.String(length=26), primary_key=True),
        sa.Column("template_id", sa.String(length=26), sa.ForeignKey("assessment_templates.template_id"), nullable=False),
        sa.Column("section_key", sa.String(length=120), nullable=False),
        sa.Column("question_key", sa.String(length=120), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("question_type", sa.String(length=50), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.UniqueConstraint("template_id", "question_key", name="uq_question_template_key"),
    )
    op.create_table(
        "submissions",
        sa.Column("submission_id", sa.String(length=26), primary_key=True),
        sa.Column("template_id", sa.String(length=26), sa.ForeignKey("assessment_templates.template_id"), nullable=False),
        sa.Column("respondent_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )
    op.create_table(
        "responses",
        sa.Column("response_id", sa.String(length=26), primary_key=True),
        sa.Column("submission_id", sa.String(length=26), sa.ForeignKey("submissions.submission_id"), nullable=False),
        sa.Column("question_key", sa.String(length=120), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answer_numeric", sa.Integer(), nullable=True),
        sa.Column("answer_json", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("submission_id", "question_key", name="uq_submission_question"),
    )


def downgrade():
    op.drop_table("responses")
    op.drop_table("submissions")
    op.drop_table("questions")
    op.drop_table("assessment_templates")
