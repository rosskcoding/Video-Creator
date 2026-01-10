"""add script_text_hash to slide_audio

Revision ID: add_script_hash_001
Revises: add_music_fade_001
Create Date: 2026-01-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_script_hash_001'
down_revision: Union[str, None] = 'add_render_cache_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add script_text_hash column to slide_audio table
    # This tracks which script text was used to generate the TTS audio
    op.add_column('slide_audio', sa.Column('script_text_hash', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('slide_audio', 'script_text_hash')

