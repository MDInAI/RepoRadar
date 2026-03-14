"""add synthesis output fields

Revision ID: 20260312_0024
Revises: 20260312_0023
Create Date: 2026-03-12 21:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260312_0024'
down_revision = '20260312_0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('synthesis_run', sa.Column('title', sa.String(length=500), nullable=True))
    op.add_column('synthesis_run', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('synthesis_run', sa.Column('key_insights', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('synthesis_run', 'key_insights')
    op.drop_column('synthesis_run', 'summary')
    op.drop_column('synthesis_run', 'title')
