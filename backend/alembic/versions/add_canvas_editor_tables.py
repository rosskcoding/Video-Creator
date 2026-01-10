"""Add canvas editor tables (slide_scenes, slide_markers, assets, normalized_scripts)

Revision ID: canvas_editor_001
Revises: migrate_rel_paths_001
Create Date: 2026-01-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'canvas_editor_001'
down_revision = 'migrate_rel_paths_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === slide_scenes table ===
    op.create_table(
        'slide_scenes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slide_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('slides.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('canvas_width', sa.Integer(), nullable=False, server_default='1920'),
        sa.Column('canvas_height', sa.Integer(), nullable=False, server_default='1080'),
        sa.Column('layers', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('render_key', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_slide_scenes_slide_id', 'slide_scenes', ['slide_id'], unique=True)
    op.create_index('ix_slide_scenes_render_key', 'slide_scenes', ['render_key'])

    # === slide_markers table ===
    op.create_table(
        'slide_markers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slide_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('slides.id', ondelete='CASCADE'), nullable=False),
        sa.Column('lang', sa.String(10), nullable=False),
        sa.Column('markers', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_slide_markers_slide_lang', 'slide_markers', ['slide_id', 'lang'], unique=True)

    # === normalized_scripts table ===
    op.create_table(
        'normalized_scripts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slide_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('slides.id', ondelete='CASCADE'), nullable=False),
        sa.Column('lang', sa.String(10), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False, server_default=''),
        sa.Column('normalized_text', sa.Text(), nullable=False, server_default=''),
        sa.Column('tokenization_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('word_timings', postgresql.JSONB(), nullable=True),  # [{charStart, charEnd, startTime, endTime, word}, ...]
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_normalized_scripts_slide_lang', 'normalized_scripts', ['slide_id', 'lang'], unique=True)

    # === assets table (for images, backgrounds, icons) ===
    op.create_table(
        'assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),  # 'image', 'background', 'icon'
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('thumbnail_path', sa.String(500), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_assets_project_id', 'assets', ['project_id'])
    op.create_index('ix_assets_type', 'assets', ['type'])


def downgrade() -> None:
    op.drop_table('assets')
    op.drop_table('normalized_scripts')
    op.drop_table('slide_markers')
    op.drop_table('slide_scenes')

