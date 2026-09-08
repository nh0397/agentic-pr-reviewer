"""add kind to symbol call edges

Revision ID: 662915c88546
Revises: 0fc113093244
Create Date: 2026-08-23 12:44:48.600031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '662915c88546'
down_revision: Union[str, None] = '0fc113093244'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


edgekind = sa.Enum('CALL', 'REFERENCE', name='edgekind')


def upgrade() -> None:
    # add_column does not emit CREATE TYPE for a Postgres enum, so the type
    # has to be created explicitly before a column can use it.
    edgekind.create(op.get_bind(), checkfirst=True)
    # server_default backfills existing rows, which were all call edges
    # before this column existed; without it NOT NULL fails on them.
    op.add_column(
        'symbol_calls',
        sa.Column('kind', edgekind, nullable=False, server_default='CALL'),
    )


def downgrade() -> None:
    op.drop_column('symbol_calls', 'kind')
    # The type outlives the column, so drop it too or re-running the upgrade
    # would find it already present.
    edgekind.drop(op.get_bind(), checkfirst=True)
