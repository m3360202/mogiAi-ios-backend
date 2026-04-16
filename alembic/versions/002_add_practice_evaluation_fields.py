"""add_practice_evaluation_fields

Revision ID: 002
Revises: 96331842220a
Create Date: 2025-11-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '96331842220a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add practice evaluation fields to interviews table"""
    
    # 添加练习模式类型字段（practice=练习模式, corporate=职场测试）
    op.execute("""
        ALTER TABLE interviews 
        ADD COLUMN IF NOT EXISTS interview_type VARCHAR(50);
    """)
    
    # 添加练习分类（basic/advanced）
    op.execute("""
        ALTER TABLE interviews 
        ADD COLUMN IF NOT EXISTS practice_category VARCHAR(50);
    """)
    
    # 添加六维评分（JSONB格式存储各维度分数）
    op.execute("""
        ALTER TABLE interviews 
        ADD COLUMN IF NOT EXISTS dimension_scores JSONB;
    """)
    
    # 添加总评分
    op.execute("""
        ALTER TABLE interviews 
        ADD COLUMN IF NOT EXISTS overall_score INTEGER;
    """)
    
    # 添加总评语（brief总体点评）
    op.execute("""
        ALTER TABLE interviews 
        ADD COLUMN IF NOT EXISTS overall_feedback TEXT;
    """)
    
    # 添加详细描述（description详细分析）
    op.execute("""
        ALTER TABLE interviews 
        ADD COLUMN IF NOT EXISTS detailed_description TEXT;
    """)
    
    # 为现有记录设置默认值
    op.execute("""
        UPDATE interviews 
        SET interview_type = 'practice'
        WHERE interview_type IS NULL AND mode = 'practice';
    """)


def downgrade() -> None:
    """Remove practice evaluation fields from interviews table"""
    
    op.execute("""
        ALTER TABLE interviews 
        DROP COLUMN IF EXISTS interview_type,
        DROP COLUMN IF EXISTS practice_category,
        DROP COLUMN IF EXISTS dimension_scores,
        DROP COLUMN IF EXISTS overall_score,
        DROP COLUMN IF EXISTS overall_feedback,
        DROP COLUMN IF EXISTS detailed_description;
    """)





























