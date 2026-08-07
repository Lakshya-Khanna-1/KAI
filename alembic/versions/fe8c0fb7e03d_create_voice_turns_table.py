"""create_voice_turns_table

Revision ID: fe8c0fb7e03d
Revises: ed4c0fb7e03c
Create Date: 2026-08-07 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe8c0fb7e03d'
down_revision: Union[str, None] = 'ed4c0fb7e03c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('voice_turns',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('stt_latency_ms', sa.Float(), nullable=True),
        sa.Column('llm_first_token_ms', sa.Float(), nullable=True),
        sa.Column('tts_first_audio_ms', sa.Float(), nullable=True),
        sa.Column('total_latency_ms', sa.Float(), nullable=True),
        sa.Column('exceeded_budget', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('warning_stage', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('voice_turns')
