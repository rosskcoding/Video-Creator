"""Add music fade in/out settings

Revision ID: add_music_fade_001
Revises: canvas_editor_001
Create Date: 2026-01-08

"""
import sqlalchemy as sa
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "add_music_fade_001"
down_revision: Union[str, None] = "canvas_editor_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add music fade in/out columns to project_audio_settings
    op.add_column(
        "project_audio_settings",
        sa.Column("music_fade_in_sec", sa.Float(), nullable=False, server_default="2.0"),
    )
    op.add_column(
        "project_audio_settings",
        sa.Column("music_fade_out_sec", sa.Float(), nullable=False, server_default="3.0"),
    )


def downgrade() -> None:
    op.drop_column("project_audio_settings", "music_fade_out_sec")
    op.drop_column("project_audio_settings", "music_fade_in_sec")

