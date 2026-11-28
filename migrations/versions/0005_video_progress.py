"""Expose readable video processing progress in the library.

Revision ID: 0005_video_progress
Revises: 0004_transcript_visual_text
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_video_progress"
down_revision = "0004_transcript_visual_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("progress_message", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "progress_message")
