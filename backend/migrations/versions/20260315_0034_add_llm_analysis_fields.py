"""add llm analysis fields

Revision ID: 20260315_0034
Revises: 20260315_0033
Create Date: 2026-03-15 21:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260315_0034'
down_revision = '20260315_0033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('repository_analysis_result', sa.Column('category_confidence_score', sa.Integer(), nullable=True))
    op.add_column('repository_analysis_result', sa.Column('problem_statement', sa.Text(), nullable=True))
    op.add_column('repository_analysis_result', sa.Column('target_customer', sa.Text(), nullable=True))
    op.add_column('repository_analysis_result', sa.Column('product_type', sa.Text(), nullable=True))
    op.add_column('repository_analysis_result', sa.Column('business_model_guess', sa.Text(), nullable=True))
    op.add_column('repository_analysis_result', sa.Column('technical_stack', sa.Text(), nullable=True))
    op.add_column('repository_analysis_result', sa.Column('target_audience', sa.Text(), nullable=True))
    op.add_column('repository_analysis_result', sa.Column('open_problems', sa.Text(), nullable=True))
    op.add_column('repository_analysis_result', sa.Column('competitors', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('repository_analysis_result', 'competitors')
    op.drop_column('repository_analysis_result', 'open_problems')
    op.drop_column('repository_analysis_result', 'target_audience')
    op.drop_column('repository_analysis_result', 'technical_stack')
    op.drop_column('repository_analysis_result', 'business_model_guess')
    op.drop_column('repository_analysis_result', 'product_type')
    op.drop_column('repository_analysis_result', 'target_customer')
    op.drop_column('repository_analysis_result', 'problem_statement')
    op.drop_column('repository_analysis_result', 'category_confidence_score')
