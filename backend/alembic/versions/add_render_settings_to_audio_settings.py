"""Add render settings to project_audio_settings

Revision ID: add_render_settings
Revises: add_voice_id_001
Create Date: 2026-01-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_render_settings"
down_revision: Union[str, None] = "add_voice_id_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type for transition_type first
    op.execute("CREATE TYPE transitiontype AS ENUM ('none', 'fade', 'crossfade')")
    
    # Add new columns for render/timing settings
    op.add_column(
        'project_audio_settings',
        sa.Column('pre_padding_sec', sa.Float(), nullable=False, server_default='3.0')
    )
    op.add_column(
        'project_audio_settings',
        sa.Column('post_padding_sec', sa.Float(), nullable=False, server_default='3.0')
    )
    op.add_column(
        'project_audio_settings',
        sa.Column('first_slide_hold_sec', sa.Float(), nullable=False, server_default='1.0')
    )
    op.add_column(
        'project_audio_settings',
        sa.Column('last_slide_hold_sec', sa.Float(), nullable=False, server_default='1.0')
    )
    # For PostgreSQL enum, use text cast in server_default
    op.add_column(
        'project_audio_settings',
        sa.Column(
            'transition_type',
            sa.Enum('none', 'fade', 'crossfade', name='transitiontype', create_type=False),
            nullable=False,
            server_default=sa.text("'fade'::transitiontype")
        )
    )
    op.add_column(
        'project_audio_settings',
        sa.Column('transition_duration_sec', sa.Float(), nullable=False, server_default='0.5')
    )


def downgrade() -> None:
    # Remove columns
    op.drop_column('project_audio_settings', 'transition_duration_sec')
    op.drop_column('project_audio_settings', 'transition_type')
    op.drop_column('project_audio_settings', 'last_slide_hold_sec')
    op.drop_column('project_audio_settings', 'first_slide_hold_sec')
    op.drop_column('project_audio_settings', 'post_padding_sec')
    op.drop_column('project_audio_settings', 'pre_padding_sec')
    
    # Drop enum type
    op.execute("DROP TYPE IF EXISTS transitiontype")

