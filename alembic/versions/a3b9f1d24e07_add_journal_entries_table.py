"""add_journal_entries_table

Revision ID: a3b9f1d24e07
Revises: 182f47c15503
Create Date: 2026-03-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b9f1d24e07'
down_revision: Union[str, None] = '182f47c15503'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'journal_entries',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('date', sa.Date(), nullable=False, index=True),

        # Gmail tracking
        sa.Column('prompt_message_id', sa.String(255), nullable=True),
        sa.Column('prompt_thread_id', sa.String(255), nullable=True),
        sa.Column('prompt_sent_at', sa.DateTime(timezone=True), nullable=True),

        # User reply
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('response_received_at', sa.DateTime(timezone=True), nullable=True),

        # AI-parsed structure
        sa.Column('extracted_todos', sa.JSON(), nullable=True),
        sa.Column('extracted_focus_areas', sa.JSON(), nullable=True),
        sa.Column('extracted_reflections', sa.Text(), nullable=True),

        # Executive ownership
        sa.Column('executive_id', sa.Integer(), nullable=True, index=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),

        # Foreign key
        sa.ForeignKeyConstraint(
            ['executive_id'],
            ['executives.id'],
            name='fk_journal_entries_executive',
            ondelete='CASCADE',
        ),
    )


def downgrade() -> None:
    op.drop_table('journal_entries')
