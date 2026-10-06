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

        # Assign all permissions to ADMIN and appropriate domain roles
        for r in roles:
            r.permissions = permissions  # Give full permissions for local dev testing

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

            if existing:
                existing.password_hash = p_hash
                existing.is_active = True
                existing.roles = user_roles
                print(f"  - Updated user '{username}' (Password: {password})")
            else:
                new_user = User(
                    username=username,
                    password_hash=p_hash,
                    is_active=True,
                    roles=user_roles,
                )
                session.add(new_user)
                print(f"  - Created user '{username}' (Password: {password})")

        session.commit()
        print("Dev users seeded successfully!")


if __name__ == "__main__":
    seed_users()
