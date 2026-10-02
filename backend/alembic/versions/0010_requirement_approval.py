"""M3.5 — Requirement Approval and Final Requirement Contract.

Revision ID: 0010_requirement_approval
Revises: 0009_plant_workflow
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_requirement_approval"
down_revision = "0009_plant_workflow"
branch_labels = None
depends_on = None

# New permission seeded in this milestone.
# Must be granted to APPROVER and ADMIN roles via admin UI.
_PERMISSIONS = [
    (
        "plant_workflow:approve",
        "Approve or reject a pending additional requirement adjustment",
    ),
]


def upgrade() -> None:
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
        "DELETE FROM permissions WHERE code = 'plant_workflow:approve'"
    )
