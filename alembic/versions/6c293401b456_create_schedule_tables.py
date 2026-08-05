"""create schedule tables

Revision ID: 6c293401b456
Revises: 5b182390a123
Create Date: 2026-08-03 15:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c293401b456'
down_revision: Union[str, None] = '5b182390a123'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'schedule_blocks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('date', sa.String(), nullable=False),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('type', sa.String(), nullable=False, server_default='routine'),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('linked_id', sa.String(), nullable=True),
        sa.Column('locked', sa.Boolean(), server_default='0'),
        sa.Column('status', sa.String(), server_default='scheduled'),
        sa.Column('actual_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_end', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_schedule_blocks_date'), 'schedule_blocks', ['date'], unique=False)

    op.create_table(
        'availability_rules',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('weekday', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.String(), nullable=False),
        sa.Column('end_time', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False, server_default='work'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_schedule_blocks_date'), table_name='schedule_blocks')
    op.drop_table('availability_rules')
    op.drop_table('schedule_blocks')
