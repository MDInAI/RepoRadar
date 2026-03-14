"""add idea families

Revision ID: 20260312_0022
Revises: 20260312_0021
Create Date: 2026-03-12 13:33:50.511000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260312_0022'
down_revision = '20260312_0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'idea_family',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"), nullable=False),
        sa.CheckConstraint("title != ''", name='ck_idea_family_title_not_blank'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'idea_family_membership',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('idea_family_id', sa.Integer(), nullable=False),
        sa.Column('github_repository_id', sa.BigInteger(), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"), nullable=False),
        sa.ForeignKeyConstraint(['idea_family_id'], ['idea_family.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['github_repository_id'], ['repository_intake.github_repository_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idea_family_id', 'github_repository_id', name='uq_idea_family_membership_idea_family_id_github_repository_id')
    )

    op.create_index('ix_idea_family_membership_idea_family_id', 'idea_family_membership', ['idea_family_id'], unique=False)
    op.create_index('ix_idea_family_membership_github_repository_id', 'idea_family_membership', ['github_repository_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_idea_family_membership_github_repository_id', table_name='idea_family_membership')
    op.drop_index('ix_idea_family_membership_idea_family_id', table_name='idea_family_membership')
    op.drop_table('idea_family_membership')
    op.drop_table('idea_family')
