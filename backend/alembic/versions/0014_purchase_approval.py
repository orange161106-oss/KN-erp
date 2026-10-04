"""M5.2 — Purchase Recommendation Review & Approval Queue.

Revision ID: 0014_purchase_approval
Revises: 0013_inventory_alerts
"""

from alembic import op
import sqlalchemy as sa

revision = "0014_purchase_approval"
down_revision = "0013_inventory_alerts"
branch_labels = None
depends_on = None

_PERMISSIONS = [
    ("purchasing:view", "View purchase recommendations and approval queue"),
    ("purchasing:approve", "Approve, modify, or reject purchase recommendations"),
]


def upgrade() -> None:
    op.create_table(
        "purchase_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("consumable_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("planning_version_id", sa.Uuid(), nullable=True),
        sa.Column("rule_version", sa.String(16), nullable=False, server_default="M5.1_V1"),
        sa.Column("raw_calculated_qty", sa.Numeric(14, 4), nullable=False),
        sa.Column("system_recommended_qty", sa.Numeric(14, 4), nullable=False),
        sa.Column("approved_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("uom", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_purchase_approvals_consumable_id_consumables"),
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            ondelete="RESTRICT",
            name=op.f("fk_purchase_approvals_supplier_id_suppliers"),
        ),
        sa.ForeignKeyConstraint(
            ["planning_version_id"],
            ["planning_versions.id"],
            ondelete="SET NULL",
            name=op.f("fk_purchase_approvals_planning_version_id_planning_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            ondelete="SET NULL",
            name=op.f("fk_purchase_approvals_requested_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            ondelete="SET NULL",
            name=op.f("fk_purchase_approvals_reviewed_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_approvals")),
    )
    op.create_index("ix_purch_appr_consumable", "purchase_approvals", ["consumable_id"])
    op.create_index("ix_purch_appr_supplier", "purchase_approvals", ["supplier_id"])
    op.create_index("ix_purch_appr_status", "purchase_approvals", ["status"])
    op.create_index("ix_purch_appr_version", "purchase_approvals", ["planning_version_id"])

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
        "DELETE FROM permissions WHERE code IN ('purchasing:view', 'purchasing:approve')"
    )
    op.drop_table("purchase_approvals")
