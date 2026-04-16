"""
Alembic Migration Template for Supabase Integration

Run this with: alembic revision --autogenerate -m "add supabase id to users"

If you're using Alembic for migrations, this is the Python template.
Otherwise, use the SQL script in prisma/migrations/add_supabase_id.sql
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    """Add Supabase ID support to users table"""
    # Add supabase_id column
    op.add_column('users', sa.Column('supabase_id', sa.String(255), nullable=True))
    
    # Create unique index
    op.create_index('idx_users_supabase_id', 'users', ['supabase_id'], unique=True)
    
    # Make hashed_password nullable
    op.alter_column('users', 'hashed_password',
                    existing_type=sa.String(255),
                    nullable=True)


def downgrade():
    """Remove Supabase ID support"""
    # Remove index
    op.drop_index('idx_users_supabase_id', table_name='users')
    
    # Remove column
    op.drop_column('users', 'supabase_id')
    
    # Make hashed_password non-nullable again
    op.alter_column('users', 'hashed_password',
                    existing_type=sa.String(255),
                    nullable=False)

