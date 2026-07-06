"""value_bets.lineup_confirmed added

Phase 9 domain change: `ValueBet` gained an optional `lineup_confirmed`
(only meaningful for model_source=PLAYER_PROPS bets, NULL otherwise) so
`GET /value-bets` can display/filter on it without needing the transient
`PlayerPropDetection` wrapper - reading persisted bets back out has no
other way to recover this signal.

Revision ID: d4e1f9a2b613
Revises: c3d9a41b7f02
Create Date: 2026-07-03 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e1f9a2b613'
down_revision: Union[str, Sequence[str], None] = 'c3d9a41b7f02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('value_bets') as batch_op:
        batch_op.add_column(sa.Column('lineup_confirmed', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('value_bets') as batch_op:
        batch_op.drop_column('lineup_confirmed')
