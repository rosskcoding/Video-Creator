"""Add voice_id to audio settings

Revision ID: add_voice_id_001
Revises: f963154b96cf
Create Date: 2026-01-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_voice_id_001'
down_revision: Union[str, None] = 'f963154b96cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'project_audio_settings',
        sa.Column('voice_id', sa.String(100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('project_audio_settings', 'voice_id')

