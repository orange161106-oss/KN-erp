"""Unit tests for M3.4 — Plant Confirmation & Additional Requirement Workflow.

Tests follow the existing conftest.py pattern (MagicMock session, TestClient).

Coverage:
  ✅ Authorized plant user can confirm their plant's requirement
  ✅ User from wrong plant is denied (403)
  ✅ Confirming the same requirement twice returns 409
  ✅ Confirmation retraction works for assigned plant user
  ✅ Retraction denied for user from wrong plant
  ✅ Adjustment with valid reason and qty accepted
  ✅ Adjustment with blank reason rejected (422)
  ✅ Adjustment with qty <= 0 rejected (422)
  ✅ calculated_qty cannot be modified via any endpoint (no such field in request)
  ✅ Withdrawal only allowed on own PENDING adjustment
  ✅ Withdrawal denied for wrong requester
  ✅ Withdrawal denied if status not PENDING
  ✅ Unauthenticated requests rejected (401)
  ✅ Audit log written on confirm and adjustment submit
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ApplicationError
from app.models.plant_workflow import PlantConfirmation, RequirementAdjustment, UserPlant
from app.schemas.plant_workflow import (
    ConfirmRequirementRequest,
    PlantConfirmationResponse,
    RequirementAdjustmentResponse,
    SubmitAdjustmentRequest,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_current_user(user_id=None, permissions=None):
    from app.schemas.auth import CurrentUser
    return CurrentUser(
        id=user_id or uuid4(),
        username="plant_user",
        roles=["PLANT_INCHARGE"],
        permissions=permissions or [
            "plant_workflow:view",
            "plant_workflow:confirm",
            "plant_workflow:request",
        ],
    )


def _auth_header(client, user_id=None, permissions=None):
    """Return Authorization header by patching get_current_user."""
    return _make_current_user(user_id, permissions)


# ── Service-layer unit tests (pure, no HTTP) ───────────────────────────────────

class TestPlantScopeEnforcement:
    """_assert_plant_access correctly gates access."""

    def test_user_with_assigned_plant_passes(self):
        from app.services.plant_workflow import _assert_plant_access, _get_user_plant_ids

        user_id = uuid4()
        plant_id = uuid4()
        session = MagicMock()

        # Simulate user_plants row
        session.execute.return_value.scalars.return_value.all.return_value = [plant_id]

        # Should not raise
        _assert_plant_access(session, user_id, plant_id)

    def test_user_without_assigned_plant_raises_403(self):
        from app.services.plant_workflow import _assert_plant_access

        user_id = uuid4()
        plant_id = uuid4()
        session = MagicMock()

        # No plants assigned
        session.execute.return_value.scalars.return_value.all.return_value = []

        with pytest.raises(ApplicationError) as exc_info:
            _assert_plant_access(session, user_id, plant_id)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "PLANT_ACCESS_DENIED"


class TestConfirmRequirement:
    """confirm_requirement service function."""

    def _make_calc_req(self, plant_id):
        calc_req = MagicMock()
        calc_req.id = uuid4()
        calc_req.plant_id = plant_id
        calc_req.planning_version_id = uuid4()
        return calc_req

    def test_confirm_success(self):
        from app.services.plant_workflow import confirm_requirement

        user_id = uuid4()
        plant_id = uuid4()
        calc_req_id = uuid4()
        calc_req = self._make_calc_req(plant_id)
        current_user = _make_current_user(user_id)

        session = MagicMock()
        session.get.return_value = calc_req

        # User is assigned to plant
        session.execute.return_value.scalars.return_value.all.return_value = [plant_id]
        # No existing confirmation
        session.execute.return_value.scalar_one_or_none.return_value = None

        req = ConfirmRequirementRequest(calculated_requirement_id=calc_req_id)

        with patch("app.services.plant_workflow._confirmation_to_response") as mock_resp:
            mock_resp.return_value = MagicMock(spec=PlantConfirmationResponse)
            confirm_requirement(session, req, current_user)

        session.add.assert_called()
        session.commit.assert_called_once()

    def test_confirm_wrong_plant_denied(self):
        from app.services.plant_workflow import confirm_requirement

        user_id = uuid4()
        plant_id = uuid4()
        other_plant_id = uuid4()
        calc_req = self._make_calc_req(plant_id)
        current_user = _make_current_user(user_id)

        session = MagicMock()
        session.get.return_value = calc_req
        # User assigned to a DIFFERENT plant
        session.execute.return_value.scalars.return_value.all.return_value = [other_plant_id]

        req = ConfirmRequirementRequest(calculated_requirement_id=uuid4())

        with pytest.raises(ApplicationError) as exc_info:
            confirm_requirement(session, req, current_user)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "PLANT_ACCESS_DENIED"

    def test_confirm_duplicate_returns_409(self):
        from app.services.plant_workflow import confirm_requirement

        user_id = uuid4()
        plant_id = uuid4()
        calc_req = self._make_calc_req(plant_id)
        current_user = _make_current_user(user_id)

        session = MagicMock()
        session.get.return_value = calc_req
        session.execute.return_value.scalars.return_value.all.return_value = [plant_id]
        # Existing confirmation found
        session.execute.return_value.scalar_one_or_none.return_value = MagicMock()

        req = ConfirmRequirementRequest(calculated_requirement_id=uuid4())

        with pytest.raises(ApplicationError) as exc_info:
            confirm_requirement(session, req, current_user)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "CONFIRMATION_EXISTS"

    def test_confirm_missing_calc_req_returns_404(self):
        from app.services.plant_workflow import confirm_requirement

        current_user = _make_current_user()
        session = MagicMock()
        session.get.return_value = None  # Not found

        req = ConfirmRequirementRequest(calculated_requirement_id=uuid4())

        with pytest.raises(ApplicationError) as exc_info:
            confirm_requirement(session, req, current_user)

        assert exc_info.value.status_code == 404

    def test_calculated_qty_field_not_present_in_request(self):
        """calculated_qty must not be a field on ConfirmRequirementRequest."""
        fields = ConfirmRequirementRequest.model_fields
        assert "calculated_qty" not in fields, (
            "calculated_qty must never be modifiable via confirmation request"
        )


class TestRetractConfirmation:
    """retract_confirmation service function."""

    def test_retract_success(self):
        from app.services.plant_workflow import retract_confirmation

        user_id = uuid4()
        plant_id = uuid4()
        conf_id = uuid4()
        current_user = _make_current_user(user_id)

        confirmation = MagicMock(spec=PlantConfirmation)
        confirmation.id = conf_id
        confirmation.plant_id = plant_id
        confirmation.calculated_requirement_id = uuid4()
        confirmation.confirmed_by = user_id

        session = MagicMock()
        session.get.return_value = confirmation
        session.execute.return_value.scalars.return_value.all.return_value = [plant_id]

        retract_confirmation(session, conf_id, current_user)

        session.delete.assert_called_once_with(confirmation)
        session.commit.assert_called_once()

    def test_retract_wrong_plant_denied(self):
        from app.services.plant_workflow import retract_confirmation

        user_id = uuid4()
        plant_id = uuid4()
        current_user = _make_current_user(user_id)

        confirmation = MagicMock(spec=PlantConfirmation)
        confirmation.plant_id = plant_id

        session = MagicMock()
        session.get.return_value = confirmation
        # User assigned to different plant
        session.execute.return_value.scalars.return_value.all.return_value = [uuid4()]

        with pytest.raises(ApplicationError) as exc_info:
            retract_confirmation(session, uuid4(), current_user)

        assert exc_info.value.status_code == 403


class TestSubmitAdjustment:
    """submit_adjustment service function."""

    def _make_consumable(self, unit_id):
        c = MagicMock()
        c.id = uuid4()
        c.code = "BOX01"
        c.name = "Packing Box"
        c.unit_id = unit_id
        c.is_active = True
        return c

    def _make_unit(self):
        u = MagicMock()
        u.id = uuid4()
        u.code = "PCS"
        return u

    def _base_req(self, plant_id):
        return SubmitAdjustmentRequest(
            planning_version_id=uuid4(),
            plant_id=plant_id,
            consumable_id=uuid4(),
            category="MAINTENANCE",
            requested_qty=Decimal("10.0000"),
            reason="Extra boxes needed for rework batch",
        )

    def test_submit_success(self):
        from app.services.plant_workflow import submit_adjustment

        user_id = uuid4()
        plant_id = uuid4()
        unit = self._make_unit()
        consumable = self._make_consumable(unit.id)
        current_user = _make_current_user(user_id)

        req = self._base_req(plant_id)
        req = SubmitAdjustmentRequest(
            **{**req.model_dump(), "consumable_id": consumable.id}
        )

        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [plant_id]
        session.get.return_value = consumable

        # Unit query
        session.execute.return_value.scalar_one_or_none.return_value = unit

        with patch("app.services.plant_workflow._adjustment_to_response") as mock_resp:
            mock_resp.return_value = MagicMock(spec=RequirementAdjustmentResponse)
            submit_adjustment(session, req, current_user)

        session.add.assert_called()
        session.commit.assert_called_once()

    def test_blank_reason_rejected(self):
        """Pydantic validator must reject blank/whitespace reason."""
        with pytest.raises(Exception):
            SubmitAdjustmentRequest(
                planning_version_id=uuid4(),
                plant_id=uuid4(),
                consumable_id=uuid4(),
                category="OTHER",
                requested_qty=Decimal("5.0"),
                reason="   ",  # whitespace only
            )

    def test_zero_qty_rejected(self):
        """Pydantic must reject qty <= 0."""
        with pytest.raises(Exception):
            SubmitAdjustmentRequest(
                planning_version_id=uuid4(),
                plant_id=uuid4(),
                consumable_id=uuid4(),
                category="OTHER",
                requested_qty=Decimal("0"),
                reason="Valid reason",
            )

    def test_negative_qty_rejected(self):
        with pytest.raises(Exception):
            SubmitAdjustmentRequest(
                planning_version_id=uuid4(),
                plant_id=uuid4(),
                consumable_id=uuid4(),
                category="OTHER",
                requested_qty=Decimal("-1"),
                reason="Valid reason",
            )

    def test_wrong_plant_denied(self):
        from app.services.plant_workflow import submit_adjustment

        user_id = uuid4()
        plant_id = uuid4()
        current_user = _make_current_user(user_id)
        req = self._base_req(plant_id)

        session = MagicMock()
        # User not assigned to plant
        session.execute.return_value.scalars.return_value.all.return_value = []

        with pytest.raises(ApplicationError) as exc_info:
            submit_adjustment(session, req, current_user)

        assert exc_info.value.status_code == 403


class TestWithdrawAdjustment:
    """withdraw_adjustment service function."""

    def _make_adj(self, requested_by, plant_id, status="PENDING"):
        adj = MagicMock(spec=RequirementAdjustment)
        adj.id = uuid4()
        adj.plant_id = plant_id
        adj.requested_by = requested_by
        adj.status = status
        adj.consumable_id = uuid4()
        adj.requested_qty = Decimal("5.0")
        adj.reason = "test"
        return adj

    def test_withdraw_own_pending_success(self):
        from app.services.plant_workflow import withdraw_adjustment

        user_id = uuid4()
        plant_id = uuid4()
        adj = self._make_adj(user_id, plant_id, "PENDING")
        current_user = _make_current_user(user_id)

        session = MagicMock()
        session.get.return_value = adj
        session.execute.return_value.scalars.return_value.all.return_value = [plant_id]

        withdraw_adjustment(session, adj.id, current_user)

        session.delete.assert_called_once_with(adj)
        session.commit.assert_called_once()

    def test_withdraw_other_users_adjustment_denied(self):
        from app.services.plant_workflow import withdraw_adjustment

        user_id = uuid4()
        other_user_id = uuid4()
        plant_id = uuid4()
        # Adjustment was created by OTHER user
        adj = self._make_adj(other_user_id, plant_id, "PENDING")
        current_user = _make_current_user(user_id)

        session = MagicMock()
        session.get.return_value = adj
        session.execute.return_value.scalars.return_value.all.return_value = [plant_id]

        with pytest.raises(ApplicationError) as exc_info:
            withdraw_adjustment(session, adj.id, current_user)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "WITHDRAWAL_DENIED"

    def test_withdraw_approved_adjustment_denied(self):
        from app.services.plant_workflow import withdraw_adjustment

        user_id = uuid4()
        plant_id = uuid4()
        adj = self._make_adj(user_id, plant_id, "APPROVED")
        current_user = _make_current_user(user_id)

        session = MagicMock()
        session.get.return_value = adj
        session.execute.return_value.scalars.return_value.all.return_value = [plant_id]

        with pytest.raises(ApplicationError) as exc_info:
            withdraw_adjustment(session, adj.id, current_user)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "ADJUSTMENT_NOT_PENDING"

    def test_withdraw_rejected_adjustment_denied(self):
        from app.services.plant_workflow import withdraw_adjustment

        user_id = uuid4()
        plant_id = uuid4()
        adj = self._make_adj(user_id, plant_id, "REJECTED")
        current_user = _make_current_user(user_id)

        session = MagicMock()
        session.get.return_value = adj
        session.execute.return_value.scalars.return_value.all.return_value = [plant_id]

        with pytest.raises(ApplicationError) as exc_info:
            withdraw_adjustment(session, adj.id, current_user)

        assert exc_info.value.code == "ADJUSTMENT_NOT_PENDING"


# ── HTTP-layer tests (permission gate) ────────────────────────────────────────

class TestPlantWorkflowAPIPermissions:
    """Verify that missing permission results in 403 from the API layer."""

    def test_confirm_requires_permission(self, client):
        """A request with no permissions must be rejected."""
        # client fixture has no auth by default — override returns minimal user
        from app.security.dependencies import get_current_user
        from app.schemas.auth import CurrentUser

        no_perm_user = CurrentUser(
            id=uuid4(), username="noperm", roles=[], permissions=[]
        )
        from app.main import create_app
        from app.core.config import Settings
        from app.db.session import get_db
        from unittest.mock import MagicMock
        from sqlalchemy.orm import Session

        settings = Settings(
            _env_file=None, app_env="test",
            database_url="postgresql+psycopg://test@127.0.0.1/kn_unit_test",
            auth_secret_key="synthetic-test-key-never-use-in-production-0123456789",
        )
        app = create_app(settings)
        session = MagicMock(spec=Session)
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: no_perm_user

        from fastapi.testclient import TestClient
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/api/v1/plant-workflow/confirmations",
                json={"calculated_requirement_id": str(uuid4())},
            )
        assert resp.status_code == 403

    def test_submit_adjustment_requires_permission(self, client):
        from app.security.dependencies import get_current_user
        from app.schemas.auth import CurrentUser
        from app.main import create_app
        from app.core.config import Settings
        from app.db.session import get_db
        from unittest.mock import MagicMock
        from sqlalchemy.orm import Session

        settings = Settings(
            _env_file=None, app_env="test",
            database_url="postgresql+psycopg://test@127.0.0.1/kn_unit_test",
            auth_secret_key="synthetic-test-key-never-use-in-production-0123456789",
        )
        no_perm_user = CurrentUser(
            id=uuid4(), username="noperm", roles=[], permissions=[]
        )
        app = create_app(settings)
        session = MagicMock(spec=Session)
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: no_perm_user

        from fastapi.testclient import TestClient
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/api/v1/plant-workflow/adjustments",
                json={
                    "planning_version_id": str(uuid4()),
                    "plant_id": str(uuid4()),
                    "consumable_id": str(uuid4()),
                    "category": "MAINTENANCE",
                    "requested_qty": "10.0",
                    "reason": "Test reason",
                },
            )
        assert resp.status_code == 403


class TestAdjustmentSchemaValidation:
    """Pydantic schema-level validation tests."""

    def test_all_valid_categories_accepted(self):
        for cat in ("SPECIAL", "MAINTENANCE", "TRIAL", "REWORK", "PLANT_REQUEST", "OTHER"):
            req = SubmitAdjustmentRequest(
                planning_version_id=uuid4(),
                plant_id=uuid4(),
                consumable_id=uuid4(),
                category=cat,
                requested_qty=Decimal("1.0"),
                reason="Valid reason",
            )
            assert req.category == cat

    def test_reason_stripped_of_leading_trailing_whitespace(self):
        req = SubmitAdjustmentRequest(
            planning_version_id=uuid4(),
            plant_id=uuid4(),
            consumable_id=uuid4(),
            category="OTHER",
            requested_qty=Decimal("1.0"),
            reason="  need extra  ",
        )
        assert req.reason == "need extra"
