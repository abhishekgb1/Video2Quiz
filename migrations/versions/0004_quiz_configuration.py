"""Add quiz configuration jobs and source/evaluation metadata, preserving rows."""
from alembic import op
import sqlalchemy as sa

revision = "0004_quiz_configuration"
down_revision = "0003_exam_attempts_responses"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("questions", sa.Column("evidence", sa.Text(), nullable=True))
    op.add_column("questions", sa.Column("generation_method", sa.String(40), nullable=False, server_default="baseline"))
    op.add_column("exam_attempts", sa.Column("mode", sa.String(20), nullable=False, server_default="exam"))
    op.add_column("exam_attempts", sa.Column("time_limit_seconds", sa.Integer(), nullable=True))
    op.add_column("exam_responses", sa.Column("difficulty", sa.String(20), nullable=True))
    op.add_column("exam_responses", sa.Column("timestamp_seconds", sa.Integer(), nullable=True))
    op.add_column("exam_responses", sa.Column("evidence", sa.Text(), nullable=True))
    op.create_table(
        "quiz_generations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quiz_version", sa.Integer(), nullable=True),
        sa.Column("easy_count", sa.Integer(), nullable=False),
        sa.Column("medium_count", sa.Integer(), nullable=False),
        sa.Column("hard_count", sa.Integer(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("question_generation_mode", sa.String(20), nullable=False),
        sa.Column("generation_method", sa.String(40), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("video_id", "quiz_version", name="uq_generation_video_version"),
    )
    op.create_index("ix_quiz_generations_video_id", "quiz_generations", ["video_id"])
    # Backfill snapshot metadata without changing historic answers or scores.
    op.execute("UPDATE exam_responses SET difficulty = (SELECT difficulty FROM questions WHERE questions.id = exam_responses.question_id), timestamp_seconds = (SELECT timestamp_seconds FROM questions WHERE questions.id = exam_responses.question_id)")


def downgrade():
    raise RuntimeError("This additive migration preserves quiz history; restore a reviewed backup instead of dropping metadata.")
