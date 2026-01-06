"""Migrate absolute paths to relative paths

This migration converts absolute file paths stored in the database
to relative paths (relative to DATA_DIR). This makes the system
portable across different deployments and DATA_DIR configurations.

Affected tables:
- slides.image_path
- slide_audio.audio_path
- render_jobs.output_video_path
- render_jobs.output_srt_path
- render_jobs.logs_path
- audio_assets.file_path
- project_versions.pptx_asset_path

Revision ID: migrate_rel_paths_001
Revises: add_allowed_langs_001
Create Date: 2026-01-06

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'migrate_rel_paths_001'
down_revision: Union[str, None] = 'add_allowed_langs_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Convert absolute paths to relative paths.
    
    Paths in DB look like:
      /some/path/data/projects/{project_id}/versions/{version_id}/slides/001.png
    
    We want to strip everything up to and including 'data/projects/' to get:
      {project_id}/versions/{version_id}/slides/001.png
    
    This handles various DATA_DIR locations.
    """
    
    # Migrate slides.image_path
    # Match pattern: anything followed by /data/projects/ or just data/projects/
    op.execute("""
        UPDATE slides 
        SET image_path = REGEXP_REPLACE(
            image_path, 
            '^.*/data/projects/', 
            ''
        )
        WHERE image_path LIKE '%/data/projects/%'
    """)
    
    # Also handle Windows-style paths (backslashes)
    op.execute("""
        UPDATE slides 
        SET image_path = REGEXP_REPLACE(
            REPLACE(image_path, '\\', '/'),
            '^.*/data/projects/', 
            ''
        )
        WHERE image_path LIKE '%\\data\\projects\\%'
    """)
    
    # Migrate slide_audio.audio_path
    op.execute("""
        UPDATE slide_audio 
        SET audio_path = REGEXP_REPLACE(
            audio_path, 
            '^.*/data/projects/', 
            ''
        )
        WHERE audio_path LIKE '%/data/projects/%'
    """)
    
    op.execute("""
        UPDATE slide_audio 
        SET audio_path = REGEXP_REPLACE(
            REPLACE(audio_path, '\\', '/'),
            '^.*/data/projects/', 
            ''
        )
        WHERE audio_path LIKE '%\\data\\projects\\%'
    """)
    
    # Migrate render_jobs.output_video_path
    op.execute("""
        UPDATE render_jobs 
        SET output_video_path = REGEXP_REPLACE(
            output_video_path, 
            '^.*/data/projects/', 
            ''
        )
        WHERE output_video_path IS NOT NULL 
          AND output_video_path LIKE '%/data/projects/%'
    """)
    
    # Migrate render_jobs.output_srt_path
    op.execute("""
        UPDATE render_jobs 
        SET output_srt_path = REGEXP_REPLACE(
            output_srt_path, 
            '^.*/data/projects/', 
            ''
        )
        WHERE output_srt_path IS NOT NULL 
          AND output_srt_path LIKE '%/data/projects/%'
    """)
    
    # Migrate render_jobs.logs_path
    op.execute("""
        UPDATE render_jobs 
        SET logs_path = REGEXP_REPLACE(
            logs_path, 
            '^.*/data/projects/', 
            ''
        )
        WHERE logs_path IS NOT NULL 
          AND logs_path LIKE '%/data/projects/%'
    """)
    
    # Migrate audio_assets.file_path
    op.execute("""
        UPDATE audio_assets 
        SET file_path = REGEXP_REPLACE(
            file_path, 
            '^.*/data/projects/', 
            ''
        )
        WHERE file_path LIKE '%/data/projects/%'
    """)
    
    # Migrate project_versions.pptx_asset_path
    op.execute("""
        UPDATE project_versions 
        SET pptx_asset_path = REGEXP_REPLACE(
            pptx_asset_path, 
            '^.*/data/projects/', 
            ''
        )
        WHERE pptx_asset_path IS NOT NULL 
          AND pptx_asset_path LIKE '%/data/projects/%'
    """)


def downgrade() -> None:
    """
    Cannot automatically restore absolute paths since the original
    DATA_DIR location is not stored. This is a one-way migration.
    
    If you need to rollback, you'll need to manually update paths
    with the correct DATA_DIR prefix for your environment.
    """
    # No-op: absolute paths cannot be automatically reconstructed
    pass

