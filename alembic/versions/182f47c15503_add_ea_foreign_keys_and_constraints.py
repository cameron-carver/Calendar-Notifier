"""add_ea_foreign_keys_and_constraints

Revision ID: 182f47c15503
Revises: 07c541973018
Create Date: 2026-02-10 19:27:28.328336

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '182f47c15503'
down_revision: Union[str, None] = '07c541973018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add foreign key constraints with proper cascade behavior
    # SQLite requires batch mode for FK constraints and unique constraints
    with op.batch_alter_table('briefs') as batch_op:
        batch_op.create_foreign_key(
            'fk_briefs_executive',
            'executives',
            ['executive_id'],
            ['id'],
            ondelete='SET NULL'  # Keep briefs if executive deleted
        )

    with op.batch_alter_table('meeting_annotations') as batch_op:
        batch_op.create_foreign_key(
            'fk_annotations_executive',
            'executives',
            ['executive_id'],
            ['id'],
            ondelete='CASCADE'  # Delete annotations if executive deleted
        )
        # Add unique constraint in batch mode
        batch_op.create_unique_constraint(
            'uq_meeting_annotations_executive_event',
            ['executive_id', 'event_id']
        )

    with op.batch_alter_table('person_relationships') as batch_op:
        batch_op.create_foreign_key(
            'fk_relationships_executive',
            'executives',
            ['executive_id'],
            ['id'],
            ondelete='CASCADE'  # Delete relationships if executive deleted
        )
        # Add unique constraint in batch mode
        batch_op.create_unique_constraint(
            'uq_person_relationships_executive_email',
            ['executive_id', 'person_email']
        )


def downgrade() -> None:
    # Drop constraints in batch mode (SQLite requirement)
    with op.batch_alter_table('person_relationships') as batch_op:
        batch_op.drop_constraint('uq_person_relationships_executive_email', type_='unique')
        batch_op.drop_constraint('fk_relationships_executive', type_='foreignkey')

    with op.batch_alter_table('meeting_annotations') as batch_op:
        batch_op.drop_constraint('uq_meeting_annotations_executive_event', type_='unique')
        batch_op.drop_constraint('fk_annotations_executive', type_='foreignkey')

    with op.batch_alter_table('briefs') as batch_op:
        batch_op.drop_constraint('fk_briefs_executive', type_='foreignkey')
