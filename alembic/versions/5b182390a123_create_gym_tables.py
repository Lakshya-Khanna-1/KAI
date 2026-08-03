"""create gym tables

Revision ID: 5b182390a123
Revises: 4a92911b3304
Create Date: 2026-08-03 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b182390a123'
down_revision: Union[str, None] = '4a92911b3304'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'workouts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('split_name', sa.String(), nullable=True),
        sa.Column('duration_min', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('energy_rating', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'exercise_sets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('workout_id', sa.String(), sa.ForeignKey('workouts.id'), nullable=False),
        sa.Column('exercise', sa.String(), nullable=False),
        sa.Column('set_number', sa.Integer(), nullable=True, default=1),
        sa.Column('reps', sa.Integer(), nullable=False),
        sa.Column('weight_kg', sa.Float(), nullable=False),
        sa.Column('rpe', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'body_metrics',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('weight_kg', sa.Float(), nullable=False),
        sa.Column('body_fat_pct', sa.Float(), nullable=True),
        sa.Column('measurements_json', sa.Text(), nullable=True, default='{}'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'exercise_prs',
        sa.Column('exercise', sa.String(), nullable=False),
        sa.Column('best_weight', sa.Float(), nullable=False),
        sa.Column('best_reps', sa.Integer(), nullable=False),
        sa.Column('est_1rm', sa.Float(), nullable=False),
        sa.Column('achieved_on', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('exercise')
    )


def downgrade() -> None:
    op.drop_table('exercise_prs')
    op.drop_table('body_metrics')
    op.drop_table('exercise_sets')
    op.drop_table('workouts')
