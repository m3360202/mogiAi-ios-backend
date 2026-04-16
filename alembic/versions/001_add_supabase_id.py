"""Add supabase_id to users

Revision ID: 001
Revises: 
Create Date: 2024-01-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """整合来自 prisma/migrations/add_supabase_id.sql 的变更 + OAuth 支持"""
    
    # Add supabase_id column
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS supabase_id VARCHAR(255);
    """)
    
    # Create unique index on supabase_id
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_supabase_id 
        ON users(supabase_id);
    """)
    
    # Make hashed_password nullable (for OAuth users)
    op.execute("""
        ALTER TABLE users 
        ALTER COLUMN hashed_password DROP NOT NULL;
    """)
    
    # Add OAuth support fields
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500),
        ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(50),
        ADD COLUMN IF NOT EXISTS oauth_id VARCHAR(255);
    """)
    
    # Create index on oauth_provider + oauth_id combination
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_oauth 
        ON users(oauth_provider, oauth_id);
    """)


def downgrade() -> None:
    """回滚变更"""
    
    # Remove OAuth index
    op.execute("""
        DROP INDEX IF EXISTS idx_users_oauth;
    """)
    
    # Remove OAuth columns
    op.execute("""
        ALTER TABLE users 
        DROP COLUMN IF EXISTS oauth_id,
        DROP COLUMN IF EXISTS oauth_provider,
        DROP COLUMN IF EXISTS avatar_url;
    """)
    
    # Remove supabase index
    op.execute("""
        DROP INDEX IF EXISTS idx_users_supabase_id;
    """)
    
    # Remove supabase column
    op.execute("""
        ALTER TABLE users 
        DROP COLUMN IF EXISTS supabase_id;
    """)
    
    # Note: 我们不回滚 hashed_password 的 nullable 变更
    # 因为这可能会破坏现有数据

