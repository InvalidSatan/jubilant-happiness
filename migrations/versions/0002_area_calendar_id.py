"""add shop_area.calendar_id

Holds the Google Calendar id backing each area's monitor shift schedule.
Faculty create and own these calendars, so the id is data they manage from
the faculty portal rather than deployment configuration.

Revision ID: 0002_area_calendar_id
Revises: 0001_initial_schema
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0002_area_calendar_id'
down_revision = '0001_initial_schema'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('shop_area', schema=None) as batch_op:
        batch_op.add_column(sa.Column('calendar_id', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('shop_area', schema=None) as batch_op:
        batch_op.drop_column('calendar_id')
