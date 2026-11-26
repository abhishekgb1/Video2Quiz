"""Add optional durable cloud media keys without moving existing local files."""
from alembic import op
import sqlalchemy as sa

revision = "0005_cloud_media"
down_revision = "0004_quiz_configuration"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("videos", sa.Column("original_object_key", sa.String(512), nullable=True))
    op.add_column("videos", sa.Column("playback_object_key", sa.String(512), nullable=True))


def downgrade():
    raise RuntimeError("Cloud object references must not be dropped; restore a reviewed backup instead.")
