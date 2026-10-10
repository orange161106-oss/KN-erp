"""M4.4 — Inventory Stock and MSL Alerts Workflow.

Revision ID: 0013_inventory_alerts
Revises: 0012_projected_inventory
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_inventory_alerts"
down_revision = "0012_projected_inventory"
branch_labels = None
depends_on = None

_PERMISSIONS = [
    ("alerts:view", "View inventory alerts and stock warnings"),
    ("alerts:acknowledge", "Acknowledge active inventory alerts"),
]


def upgrade() -> None:
    op.create_table(
        "inventory_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("consumable_id", sa.Uuid(), nullable=False),
        sa.Column("alert_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("current_stock", sa.Numeric(14, 4), nullable=False),
        sa.Column("threshold_qty", sa.Numeric(14, 4), nullable=False),
        sa.Column("uom", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["consumable_id"],
            ["consumables.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_alerts_consumable_id_consumables"),
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"],
            ["users.id"],
            ondelete="SET NULL",
            name=op.f("fk_inventory_alerts_acknowledged_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_alerts")),
    )
    op.create_index("ix_inv_alerts_consumable", "inventory_alerts", ["consumable_id"])
    op.create_index("ix_inv_alerts_status", "inventory_alerts", ["status"])
    op.create_index("ix_inv_alerts_severity", "inventory_alerts", ["severity"])
    op.create_index(
        "ix_inv_alerts_type_status",
        "inventory_alerts",
        ["alert_type", "status"],
    )

    # Seed permission records
    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        permissions_table,
        [
            {
                "id": sa.text("gen_random_uuid()"),
                "code": code,
                "description": description,
            }
            for code, description in _PERMISSIONS
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM permissions WHERE code IN ('alerts:view', 'alerts:acknowledge')"
    )
    op.drop_table("inventory_alerts")
