"""Add global markers table for cross-language animation triggers

This migration implements EPIC A: Stable Multi-language Triggers.

Key changes:
1. Creates `global_markers` table - one marker ID per animation trigger, independent of language
2. Creates `marker_positions` table - position and timing per marker per language
3. Adds `contains_marker_tokens` column to normalized_scripts for token tracking

The marker system allows:
- Word triggers to be converted to stable marker IDs
- Marker tokens (⟦M:<uuid>⟧) to be preserved during translation
- Each language to have its own timing while referencing the same marker

Revision ID: add_global_markers
Revises: canvas_editor_001
Create Date: 2026-01-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_global_markers'
down_revision = 'canvas_editor_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum for marker source
    marker_source_enum = sa.Enum('manual', 'wordclick', 'auto', name='markersource')
    marker_source_enum.create(op.get_bind(), checkfirst=True)
    
    # Create global_markers table
    # One marker per animation trigger, independent of language
    op.create_table(
        'global_markers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slide_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('slides.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),  # Optional human-readable name
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create index for slide_id lookups
    op.create_index('ix_global_markers_slide_id', 'global_markers', ['slide_id'])
    
    # Create marker_positions table
    # Stores position and timing for each marker in each language
    op.create_table(
        'marker_positions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('marker_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('global_markers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('lang', sa.String(10), nullable=False),
        sa.Column('char_start', sa.Integer, nullable=True),  # Position in normalized text
        sa.Column('char_end', sa.Integer, nullable=True),
        sa.Column('time_seconds', sa.Float, nullable=True),  # Populated after TTS
        sa.Column('source', marker_source_enum, nullable=False, server_default='manual'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create unique constraint for marker_id + lang
    op.create_unique_constraint(
        'uq_marker_positions_marker_lang', 
        'marker_positions', 
        ['marker_id', 'lang']
    )
    
    # Create index for marker lookups by language
    op.create_index('ix_marker_positions_marker_id', 'marker_positions', ['marker_id'])
    op.create_index('ix_marker_positions_lang', 'marker_positions', ['lang'])
    
    # Add contains_marker_tokens to normalized_scripts
    # This flag indicates if the text contains ⟦M:uuid⟧ tokens
    op.add_column(
        'normalized_scripts',
        sa.Column('contains_marker_tokens', sa.Boolean, server_default='false', nullable=False)
    )
    
    # Add needs_retranslate flag to slide_scripts for migration UX
    op.add_column(
        'slide_scripts',
        sa.Column('needs_retranslate', sa.Boolean, server_default='false', nullable=False)
    )


def downgrade() -> None:
    # Remove columns
    op.drop_column('slide_scripts', 'needs_retranslate')
    op.drop_column('normalized_scripts', 'contains_marker_tokens')
    
    # Drop tables
    op.drop_table('marker_positions')
    op.drop_table('global_markers')
    
    # Drop enum
    sa.Enum(name='markersource').drop(op.get_bind(), checkfirst=True)

