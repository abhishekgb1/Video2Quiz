"""Store timestamped OCR text alongside speech transcripts.

Revision ID: 0004_transcript_visual_text
Revises: 0003_exam_attempts_responses
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_transcript_visual_text"
down_revision = "0003_exam_attempts_responses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transcripts",
        sa.Column("visual_text_json", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("transcripts", "visual_text_json")
