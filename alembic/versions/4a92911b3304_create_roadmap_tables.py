"""create roadmap tables

Revision ID: 4a92911b3304
Revises: 3f82901a1102
Create Date: 2026-08-03 11:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a92911b3304'
down_revision: Union[str, None] = '3f82901a1102'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'roadmaps',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('source_text', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'roadmap_phases',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('roadmap_id', sa.String(), sa.ForeignKey('roadmaps.id'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=True, default=0),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'roadmap_topics',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('phase_id', sa.String(), sa.ForeignKey('roadmap_phases.id'), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('est_hours', sa.Float(), nullable=True, default=2.0),
        sa.Column('hours_done', sa.Float(), nullable=True, default=0.0),
        sa.Column('status', sa.String(), nullable=True, default='not_started'),
        sa.Column('prerequisites_json', sa.Text(), nullable=True, default='[]'),
        sa.Column('resources_json', sa.Text(), nullable=True, default='[]'),
        sa.Column('order_index', sa.Integer(), nullable=True, default=0),
        sa.Column('raw_line', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('roadmap_topics')
    op.drop_table('roadmap_phases')
    op.drop_table('roadmaps')
