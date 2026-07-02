"""odds_quotes.match_id required, value_bets.model_source added

Phase 6 domain changes: `OddsQuote` now carries a full `Match` reference
(closing the long-flagged gap), so `odds_quotes.match_id` becomes NOT NULL;
`ValueBet` gained `model_source` (which probability model produced it), so
`value_bets` gains the matching column.

Quotes persisted with no match association under the old `save(quote,
match_id=None)` workaround cannot satisfy the new constraint and carry no
usable context, so they are deleted. Batch mode is required for SQLite,
which cannot ALTER COLUMN in place.

Revision ID: c3d9a41b7f02
Revises: ae2f4ed2ca6e
Create Date: 2026-07-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d9a41b7f02'
down_revision: Union[str, Sequence[str], None] = 'ae2f4ed2ca6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DELETE FROM odds_quotes WHERE match_id IS NULL")
    with op.batch_alter_table('odds_quotes') as batch_op:
        batch_op.alter_column('match_id', existing_type=sa.String(length=64), nullable=False)
    # server_default backfills any pre-existing rows (all of which were
    # market-model output by definition); new rows always set it explicitly.
    with op.batch_alter_table('value_bets') as batch_op:
        batch_op.add_column(
            sa.Column('model_source', sa.String(length=32), nullable=False,
                      server_default='MARKET')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('value_bets') as batch_op:
        batch_op.drop_column('model_source')
    with op.batch_alter_table('odds_quotes') as batch_op:
        batch_op.alter_column('match_id', existing_type=sa.String(length=64), nullable=True)
