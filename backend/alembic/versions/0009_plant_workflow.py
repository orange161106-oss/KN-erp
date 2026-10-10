"""M3.4 — Plant Confirmation and Additional Requirement Workflow.

Revision ID: 0009_plant_workflow
Revises: 0008_calculated_requirements
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_plant_workflow"
down_revision = "0008_calculated_requirements"
branch_labels = None
depends_on = None

# M3.4 permission codes seeded as data.
# PLANT_INCHARGE and ADMIN roles must be assigned these via admin UI / seed data.
_PERMISSIONS = [
    ("plant_workflow:view", "View plant confirmations and additional requirement requests"),
    ("plant_workflow:confirm", "Confirm or retract a calculated requirement for an assigned plant"),
    ("plant_workflow:request", "Submit or withdraw an additional requirement for an assigned plant"),
]


def upgrade() -> None:
    # ── user_plants ────────────────────────────────────────────────────────────
    op.create_table(
        "user_plants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("assigned_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name=op.f("fk_user_plants_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["plant_id"], ["plants.id"], ondelete="CASCADE",
            name=op.f("fk_user_plants_plant_id_plants"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"], ["users.id"], ondelete="SET NULL",
            name=op.f("fk_user_plants_assigned_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_plants")),
        sa.UniqueConstraint("user_id", "plant_id", name="uq_user_plant"),
    )
    op.create_index("ix_user_plants_user_id", "user_plants", ["user_id"])
    op.create_index("ix_user_plants_plant_id", "user_plants", ["plant_id"])

    # ── plant_confirmations ────────────────────────────────────────────────────
    op.create_table(
        "plant_confirmations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("calculated_requirement_id", sa.Uuid(), nullable=False),
        sa.Column("planning_version_id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("confirmed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["calculated_requirement_id"], ["calculated_requirements.id"], ondelete="CASCADE",
            name=op.f("fk_plant_confirmations_calculated_requirement_id_calculated_requirements"),
        ),
        sa.ForeignKeyConstraint(
            ["planning_version_id"], ["planning_versions.id"], ondelete="CASCADE",
            name=op.f("fk_plant_confirmations_planning_version_id_planning_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["plant_id"], ["plants.id"], ondelete="RESTRICT",
            name=op.f("fk_plant_confirmations_plant_id_plants"),
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"], ["users.id"], ondelete="RESTRICT",
            name=op.f("fk_plant_confirmations_confirmed_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plant_confirmations")),
        sa.UniqueConstraint(
            "calculated_requirement_id", name="uq_plant_confirmation_calc_req"
        ),
    )
    op.create_index("ix_plant_conf_version", "plant_confirmations", ["planning_version_id"])
    op.create_index("ix_plant_conf_plant", "plant_confirmations", ["plant_id"])

    # ── requirement_adjustments ────────────────────────────────────────────────
    op.create_table(
        "requirement_adjustments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("planning_version_id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("consumable_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("requested_qty", sa.Numeric(14, 4), nullable=False),
        sa.Column("uom", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_comment", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["planning_version_id"], ["planning_versions.id"], ondelete="CASCADE",
            name=op.f("fk_requirement_adjustments_planning_version_id_planning_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["plant_id"], ["plants.id"], ondelete="RESTRICT",
            name=op.f("fk_requirement_adjustments_plant_id_plants"),
        ),
        sa.ForeignKeyConstraint(
            ["consumable_id"], ["consumables.id"], ondelete="RESTRICT",
            name=op.f("fk_requirement_adjustments_consumable_id_consumables"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], ondelete="RESTRICT",
            name=op.f("fk_requirement_adjustments_requested_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], ondelete="RESTRICT",
            name=op.f("fk_requirement_adjustments_reviewed_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement_adjustments")),
    )
    op.create_index("ix_req_adj_version", "requirement_adjustments", ["planning_version_id"])
    op.create_index("ix_req_adj_plant", "requirement_adjustments", ["plant_id"])
    op.create_index("ix_req_adj_status", "requirement_adjustments", ["status"])
    op.create_index(
        "ix_req_adj_version_plant",
        "requirement_adjustments",
        ["planning_version_id", "plant_id"],
    )

    # ── Seed permission records ────────────────────────────────────────────────
    # Roles (PLANT_INCHARGE, ADMIN) must be granted these permissions via admin UI.
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
    # Remove seeded permissions
    op.execute(
        "DELETE FROM permissions WHERE code IN ("
        "'plant_workflow:view', 'plant_workflow:confirm', 'plant_workflow:request'"
        ")"
    )
    op.drop_table("requirement_adjustments")
    op.drop_table("plant_confirmations")
    op.drop_table("user_plants")
