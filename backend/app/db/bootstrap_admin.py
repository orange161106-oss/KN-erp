"""Explicit environment-based provisioning; never run during an API request.

Run after migrations: python -m app.db.bootstrap_admin
Existing Super Admin password rotation requires --rotate-password.
"""
import argparse
from uuid import uuid4
from sqlalchemy import select
from app.core.config import Settings, load_settings
from app.core.errors import ApplicationError
from app.db.session import create_db_engine, create_session_factory, session_scope
from app.models.auth import User
from app.models.audit import AuditLog
from app.security.identity import normalize_username
from app.security.passwords import PasswordService


def provision(session, settings: Settings, *, rotate_password=False):
    if not settings.super_admin_username or settings.super_admin_password is None:
        raise ApplicationError("SUPER_ADMIN_CONFIG_REQUIRED", "Set SUPER_ADMIN_USERNAME and SUPER_ADMIN_PASSWORD privately.", 422)
    username = normalize_username(settings.super_admin_username)
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy import text
        session.execute(text("SELECT pg_advisory_xact_lock(71420020)"))
    existing = session.scalar(select(User).where(User.is_super_admin.is_(True)).with_for_update())
    if existing:
        if existing.username != username or not existing.is_active:
            raise ApplicationError("SUPER_ADMIN_CONFLICT", "Existing Super Admin does not match the active configured identity.", 409)
        if not rotate_password:
            return existing
        existing.password_hash = PasswordService().hash(settings.super_admin_password.get_secret_value())
        action = "ROTATE_PASSWORD"
    else:
        if session.scalar(select(User.id).where(User.username == username)):
            raise ApplicationError("SUPER_ADMIN_CONFLICT", "Configured username belongs to an employee; choose a separate Super Admin identity.", 409)
        existing = User(id=uuid4(), username=username, is_super_admin=True, is_active=True,
            password_hash=PasswordService().hash(settings.super_admin_password.get_secret_value()))
        session.add(existing)
        session.flush()
        action = "PROVISION"
    session.add(AuditLog(actor_id=existing.id, action=action, entity_type="user", entity_id=existing.id,
        old_values=None, new_values={"username": username, "is_super_admin": True},
        reason="Explicit operator command using environment configuration"))
    session.commit()
    return existing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotate-password", action="store_true")
    args = parser.parse_args()
    engine = create_db_engine(load_settings())
    try:
        with session_scope(create_session_factory(engine)) as session:
            provision(session, load_settings(), rotate_password=args.rotate_password)
        print("Super Admin provisioning completed.")
    except ApplicationError as error:
        raise SystemExit(error.message) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
