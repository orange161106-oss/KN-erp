"""Script to seed local development users and assign role permissions."""

import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.core.config import load_settings
from app.db.session import create_db_engine, create_session_factory, session_scope
from app.models.auth import Permission, Role, User
from app.security.passwords import PasswordService


def seed_users():
    settings = load_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    passwords = PasswordService()

    with session_scope(session_factory) as session:
        print("1. Querying database roles and permissions...")
        roles = session.execute(select(Role)).scalars().all()
        permissions = session.execute(select(Permission)).scalars().all()

        roles_by_code = {r.code: r for r in roles}
        print(f"Found {len(roles)} roles and {len(permissions)} permissions.")

        # Assign permissions strictly: only ADMIN receives full wildcard permissions
        for r in roles:
            if r.code == "ADMIN":
                r.permissions = permissions
            else:
                r.permissions = []

        session.commit()
        print("Assigned permissions to roles.")

        # User accounts to seed
        dev_accounts = [
            ("admin", "admin123", ["ADMIN", "PLANNER", "PLANT_INCHARGE", "STORE", "PURCHASE", "APPROVER", "MANAGEMENT"]),
            ("planner", "planner123", ["PLANNER"]),
            ("plant_incharge", "incharge123", ["PLANT_INCHARGE"]),
            ("purchase", "purchase123", ["PURCHASE", "APPROVER"]),
            ("store", "store123", ["STORE"]),
            ("manager", "manager123", ["MANAGEMENT"]),
        ]

        print("2. Seeding user accounts...")
        for username, password, role_codes in dev_accounts:
            existing = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
            user_roles = [roles_by_code[code] for code in role_codes if code in roles_by_code]
            p_hash = passwords.hash(password)

            is_super = (username == "admin")
            CRUD_MODULES = [
                "masters", "production_mappings", "consumption_norms",
                "prd_planning", "requirements", "plant_workflow",
                "inventory", "purchase", "purchase_orders", "goods_receipts",
            ]
            crud_permissions = {}
            for mod in CRUD_MODULES:
                if is_super:
                    crud_permissions[f"{mod}_read"] = True
                    crud_permissions[f"{mod}_create"] = True
                    crud_permissions[f"{mod}_update"] = True
                    crud_permissions[f"{mod}_delete"] = True
                elif username == "planner":
                    can_full = mod in ["production_mappings", "consumption_norms", "prd_planning", "requirements"]
                    can_edit = mod in ["masters"]
                    can_view = mod in ["plant_workflow", "inventory"]
                    crud_permissions[f"{mod}_read"] = can_full or can_edit or can_view
                    crud_permissions[f"{mod}_create"] = can_full or can_edit
                    crud_permissions[f"{mod}_update"] = can_full or can_edit
                    crud_permissions[f"{mod}_delete"] = can_full
                elif username == "plant_incharge":
                    can_full = mod in ["plant_workflow"]
                    can_view = mod in ["inventory"]
                    crud_permissions[f"{mod}_read"] = can_full or can_view
                    crud_permissions[f"{mod}_create"] = can_full
                    crud_permissions[f"{mod}_update"] = can_full
                    crud_permissions[f"{mod}_delete"] = can_full
                elif username == "purchase":
                    can_full = mod in ["purchase", "purchase_orders"]
                    can_view = mod in ["masters"]
                    crud_permissions[f"{mod}_read"] = can_full or can_view
                    crud_permissions[f"{mod}_create"] = can_full
                    crud_permissions[f"{mod}_update"] = can_full
                    crud_permissions[f"{mod}_delete"] = can_full
                elif username == "store":
                    can_full = mod in ["inventory", "goods_receipts"]
                    can_view = mod in ["masters"]
                    crud_permissions[f"{mod}_read"] = can_full or can_view
                    crud_permissions[f"{mod}_create"] = can_full
                    crud_permissions[f"{mod}_update"] = can_full
                    crud_permissions[f"{mod}_delete"] = can_full
                elif username == "manager":
                    can_view = mod in ["prd_planning", "requirements", "purchase"]
                    can_manage = mod in ["purchase_orders"]
                    crud_permissions[f"{mod}_read"] = can_view or can_manage
                    crud_permissions[f"{mod}_create"] = False
                    crud_permissions[f"{mod}_update"] = can_manage
                    crud_permissions[f"{mod}_delete"] = False
                else:
                    crud_permissions[f"{mod}_read"] = False
                    crud_permissions[f"{mod}_create"] = False
                    crud_permissions[f"{mod}_update"] = False
                    crud_permissions[f"{mod}_delete"] = False

            all_flags = {
                "is_super_admin": is_super,
                **crud_permissions,
                "can_access_plant_1": True,
                "can_access_plant_2": True,
                "can_access_plant_3": True,
                "can_access_plant_4": True,
                "can_access_plant_5": True,
                "can_access_dashboard": True if (is_super or username == "manager") else False,
                "alert_production": True if (is_super or username in ["planner", "plant_incharge"]) else False,
                "alert_inventory": True if (is_super or username in ["store", "planner"]) else False,
                "alert_purchasing": True if (is_super or username in ["purchase", "manager"]) else False,
                "alert_system": True if is_super else False,
            }

            if existing:
                existing.password_hash = p_hash
                existing.is_active = True
                existing.roles = user_roles
                for k, v in all_flags.items():
                    setattr(existing, k, v)
                print(f"  - Updated user '{username}' (Password: {password})")
            else:
                new_user = User(
                    username=username,
                    password_hash=p_hash,
                    is_active=True,
                    roles=user_roles,
                    **all_flags
                )
                session.add(new_user)
                print(f"  - Created user '{username}' (Password: {password})")

        session.commit()
        print("Dev users seeded successfully!")


if __name__ == "__main__":
    seed_users()
