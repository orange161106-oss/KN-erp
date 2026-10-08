"""Retired shared-password seeder; account provisioning is operator controlled."""

if __name__ == "__main__":
    raise SystemExit(
        "This seeder is retired to protect Super Admin and role permissions. "
        "Set SUPER_ADMIN_USERNAME and SUPER_ADMIN_PASSWORD privately, then run "
        "python -m app.db.bootstrap_admin after migrations. "
        "Create employee accounts and explicit feature grants through Administration."
    )
