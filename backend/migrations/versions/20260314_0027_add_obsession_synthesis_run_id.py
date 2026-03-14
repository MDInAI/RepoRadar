"""add obsession synthesis_run_id

Revision ID: 20260314_0027
Revises: 20260313_0026
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260314_0027'
down_revision = '20260313_0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('obsession_context', schema=None) as batch_op:
        batch_op.alter_column('idea_family_id', existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column('synthesis_run_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_obsession_context_synthesis_run_id', 'synthesis_run', ['synthesis_run_id'], ['id'], ondelete='CASCADE')
        batch_op.create_check_constraint('ck_obsession_context_exactly_one_target', "(idea_family_id IS NOT NULL AND synthesis_run_id IS NULL) OR (idea_family_id IS NULL AND synthesis_run_id IS NOT NULL)")
        batch_op.create_index('ix_obsession_context_synthesis_run_id', ['synthesis_run_id'])


def downgrade() -> None:
    with op.batch_alter_table('obsession_context', schema=None) as batch_op:
        batch_op.drop_index('ix_obsession_context_synthesis_run_id')
        batch_op.drop_constraint('ck_obsession_context_exactly_one_target', type_='check')
        batch_op.drop_constraint('fk_obsession_context_synthesis_run_id', type_='foreignkey')
        batch_op.drop_column('synthesis_run_id')
        batch_op.alter_column('idea_family_id', existing_type=sa.Integer(), nullable=False)
