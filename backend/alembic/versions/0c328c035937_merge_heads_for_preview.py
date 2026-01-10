"""merge_heads_for_preview

Revision ID: 0c328c035937
Revises: add_music_fade_001, add_script_hash_001
Create Date: 2026-01-09 19:22:10.373821

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c328c035937'
down_revision: Union[str, None] = ('add_music_fade_001', 'add_script_hash_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

