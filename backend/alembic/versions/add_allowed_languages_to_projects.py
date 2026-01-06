"""Add allowed_languages to projects

Revision ID: add_allowed_langs_001
Revises: add_voice_id_001
Create Date: 2026-01-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_allowed_langs_001'
down_revision: Union[str, None] = 'add_render_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add allowed_languages JSON column (stores list of lang codes)
    op.add_column(
        'projects',
        sa.Column('allowed_languages', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json"))
    )
    
    # Backfill: base_language + any existing script languages for the project (to avoid breaking existing data)
    op.execute("""
        UPDATE projects p
        SET allowed_languages = (
            SELECT COALESCE(json_agg(t.lang), '[]'::json)
            FROM (
                SELECT DISTINCT lower(l.lang) AS lang
                FROM (
                    SELECT p.base_language AS lang
                    UNION ALL
                    SELECT ss.lang
                    FROM slides s
                    JOIN slide_scripts ss ON ss.slide_id = s.id
                    WHERE s.project_id = p.id
                ) l
                WHERE l.lang IS NOT NULL AND l.lang <> ''
                ORDER BY lower(l.lang)
            ) t
        )
    """)


def downgrade() -> None:
    op.drop_column('projects', 'allowed_languages')

