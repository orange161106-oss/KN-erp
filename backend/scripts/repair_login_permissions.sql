-- Targeted repair for the login schema mismatch observed on 8 October 2026.
-- Run the entire file in the SQL Editor of the Supabase project used by backend/.env.
-- New permission flags default to false, matching app/models/auth.py.
-- Existing flags, accounts, passwords and migration versions are preserved.
-- This repairs the observed missing columns; it does not reconcile Alembic history.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS can_view_master_data boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS can_edit_master_data boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS can_view_planning boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS can_run_calculations boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS can_confirm_demand boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS can_approve_extra_demand boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS can_create_po boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS can_approve_po boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS can_upload_grn boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS can_view_reports boolean NOT NULL DEFAULT false;

-- Validate the columns selected by the current login model without reading accounts.
SELECT id, username, password_hash, is_active, is_super_admin, full_name, employee_id,
       can_view_master_data, can_edit_master_data, can_view_planning,
       can_run_calculations, can_confirm_demand, can_approve_extra_demand,
       can_create_po, can_approve_po, can_upload_grn, can_view_reports,
       can_access_plant_1, can_access_plant_2, can_access_plant_3,
       can_access_plant_4, can_access_plant_5, created_at, updated_at
FROM public.users
WHERE false;

COMMIT;
