"""add_overall_eval_to_interviews

Revision ID: 96331842220a
Revises: 001
Create Date: 2025-11-07 21:56:54.742168

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96331842220a'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add overall_eval column to interviews table"""
    
    # Add overall_eval JSONB column to interviews table
    op.execute("""
        ALTER TABLE interviews 
        ADD COLUMN IF NOT EXISTS overall_eval JSONB;
    """)


def downgrade() -> None:
    """Remove overall_eval column from interviews table"""
    
    # Remove overall_eval column from interviews table
    op.execute("""
        ALTER TABLE interviews 
        DROP COLUMN IF EXISTS overall_eval;
    """)

