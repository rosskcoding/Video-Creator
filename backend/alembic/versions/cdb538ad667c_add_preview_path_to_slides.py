"""add_preview_path_to_slides

Revision ID: cdb538ad667c
Revises: 0c328c035937
Create Date: 2026-01-09 19:22:16.122046

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdb538ad667c'
down_revision: Union[str, None] = '0c328c035937'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('slides', sa.Column('preview_path', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('slides', 'preview_path')

