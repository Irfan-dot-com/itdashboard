"""Drop FK devices.edge_id → edge_boxes

Devices can be discovered via periodic/transition messages before the edge box
registers via edge_health.  The edge_id column remains as metadata but without
a hard FK constraint.

Revision ID: 002
Revises: b4df3bf9ecf4
Create Date: 2026-05-08
"""

from alembic import op

revision = "002"
down_revision = "b4df3bf9ecf4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE devices DROP CONSTRAINT IF EXISTS devices_edge_id_fkey")


def downgrade():
    op.execute(
        """
        ALTER TABLE devices
        ADD CONSTRAINT devices_edge_id_fkey
        FOREIGN KEY (edge_id) REFERENCES edge_boxes(edge_id) ON DELETE SET NULL
        """
    )
