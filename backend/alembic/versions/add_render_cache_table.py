"""Add render cache table for segment caching

This migration implements EPIC B: Render Service without PNG-per-frame.

Key changes:
1. Creates `render_cache` table for caching rendered video segments
2. Each slide/language/render_key combination can have a cached segment
3. Avoids re-rendering when scene hasn't changed

Cache key includes:
- slide_id
- lang
- render_key (hash of scene layers + canvas size)
- fps
- resolution
- renderer_version

Revision ID: add_render_cache_table
Revises: add_global_markers
Create Date: 2026-01-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_render_cache_table'
down_revision = 'add_global_markers'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create render_cache table
    op.create_table(
        'render_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slide_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('slides.id', ondelete='CASCADE'), nullable=False),
        sa.Column('lang', sa.String(10), nullable=False),
        sa.Column('render_key', sa.String(64), nullable=False),  # Hash of scene content
        sa.Column('fps', sa.Integer, nullable=False, server_default='30'),
        sa.Column('width', sa.Integer, nullable=False, server_default='1920'),
        sa.Column('height', sa.Integer, nullable=False, server_default='1080'),
        sa.Column('renderer_version', sa.String(20), nullable=False, server_default='1.0'),
        sa.Column('segment_path', sa.String(500), nullable=False),  # Path to cached mp4/webm
        sa.Column('duration_sec', sa.Float, nullable=False),
        sa.Column('frame_count', sa.Integer, nullable=False),
        sa.Column('file_size_bytes', sa.Integer, nullable=True),
        sa.Column('render_time_ms', sa.Integer, nullable=True),  # How long the render took
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('last_accessed_at', sa.DateTime, server_default=sa.func.now()),
    )
    
    # Create unique constraint for cache lookup
    op.create_unique_constraint(
        'uq_render_cache_slide_lang_key_fps_res',
        'render_cache',
        ['slide_id', 'lang', 'render_key', 'fps', 'width', 'height', 'renderer_version']
    )
    
    # Create indexes for efficient lookups
    op.create_index('ix_render_cache_slide_id', 'render_cache', ['slide_id'])
    op.create_index('ix_render_cache_render_key', 'render_cache', ['render_key'])
    op.create_index('ix_render_cache_last_accessed', 'render_cache', ['last_accessed_at'])


def downgrade() -> None:
    op.drop_table('render_cache')

