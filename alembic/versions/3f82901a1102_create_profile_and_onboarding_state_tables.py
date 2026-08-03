"""create profile and onboarding_state tables

Revision ID: 3f82901a1102
Revises: 2289175804e6
Create Date: 2026-08-03 10:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f82901a1102'
down_revision: Union[str, None] = '2289175804e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'profile',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value_json', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('asked_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )
    op.create_table(
        'onboarding_state',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('phase', sa.String(), nullable=True),
        sa.Column('questions_asked', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('onboarding_state')
    op.drop_table('profile')
