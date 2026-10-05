"""Unit tests for M5.2 — Purchase Recommendation Review & Approval Queue."""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.errors import ApplicationError
from app.models.inventory_masters import Consumable, Supplier
from app.models.purchase_approval import PurchaseApproval
from app.schemas.auth import CurrentUser
from app.schemas.purchase_approval import (
    PurchaseApprovalResponse,
    ReviewPurchaseApprovalRequest,
    SubmitPurchaseApprovalRequest,
)


def _make_current_user(user_id=None, permissions=None):
    return CurrentUser(
        id=user_id or uuid4(),
        username="approver_user",
        roles=["APPROVER"],
        permissions=permissions or ["purchasing:view", "purchasing:approve"],
    )


class TestSubmitPurchaseApproval:
    """submit_purchase_approval service function."""

    def test_submit_success(self):
        from app.services.purchase_approval import submit_purchase_approval

        user_id = uuid4()
        c_id = uuid4()
        s_id = uuid4()

        c_obj = MagicMock(spec=Consumable)
        c_obj.id = c_id
        c_obj.is_active = True

        s_obj = MagicMock(spec=Supplier)
        s_obj.id = s_id
        s_obj.is_active = True

        session = MagicMock()
        session.get.side_effect = lambda model, pk: c_obj if model == Consumable else s_obj

        current_user = _make_current_user(user_id=user_id)
        req = SubmitPurchaseApprovalRequest(
            consumable_id=c_id,
            supplier_id=s_id,
            raw_calculated_qty=Decimal("15.0000"),
            system_recommended_qty=Decimal("20.0000"),
            uom="PCS",
            reason="Low stock warning",
        )

        with patch("app.services.purchase_approval._approval_to_response") as mock_resp:
            mock_resp.return_value = MagicMock(spec=PurchaseApprovalResponse)
            submit_purchase_approval(session, req, current_user)

        session.add.assert_called_once()
        session.commit.assert_called_once()


class TestReviewPurchaseApproval:
    """review_purchase_approval service function."""

    def _make_approval(self, requested_by, status="PENDING"):
        appr = MagicMock(spec=PurchaseApproval)
        appr.id = uuid4()
        appr.consumable_id = uuid4()
        appr.supplier_id = uuid4()
        appr.requested_by = requested_by
        appr.status = status
        appr.raw_calculated_qty = Decimal("15.0000")
        appr.system_recommended_qty = Decimal("20.0000")
        appr.approved_qty = None
        appr.reason = None
        return appr

    def test_approve_recommendation_success(self):
        from app.services.purchase_approval import review_purchase_approval

        requester_id = uuid4()
        approver_id = uuid4()
        appr = self._make_approval(requester_id, "PENDING")

        session = MagicMock()
        session.get.return_value = appr
        current_user = _make_current_user(user_id=approver_id)

        req = ReviewPurchaseApprovalRequest(action="APPROVE")

        with patch("app.services.purchase_approval._approval_to_response") as mock_resp:
            mock_resp.return_value = MagicMock(spec=PurchaseApprovalResponse)
            review_purchase_approval(session, appr.id, req, current_user)

        assert appr.status == "APPROVED"
        assert appr.approved_qty == Decimal("20.0000")
        assert appr.reviewed_by == approver_id
        session.commit.assert_called_once()

    def test_modify_recommendation_success(self):
        from app.services.purchase_approval import review_purchase_approval

        requester_id = uuid4()
        approver_id = uuid4()
        appr = self._make_approval(requester_id, "PENDING")

        session = MagicMock()
        session.get.return_value = appr
        current_user = _make_current_user(user_id=approver_id)

        req = ReviewPurchaseApprovalRequest(
            action="MODIFY",
            approved_qty=Decimal("30.0000"),
            reason="Expecting spike in plant demand",
        )

        with patch("app.services.purchase_approval._approval_to_response") as mock_resp:
            mock_resp.return_value = MagicMock(spec=PurchaseApprovalResponse)
            review_purchase_approval(session, appr.id, req, current_user)

        assert appr.status == "MODIFIED"
        assert appr.approved_qty == Decimal("30.0000")
        assert appr.reason == "Expecting spike in plant demand"
        session.commit.assert_called_once()

    def test_reject_recommendation_success(self):
        from app.services.purchase_approval import review_purchase_approval

        requester_id = uuid4()
        approver_id = uuid4()
        appr = self._make_approval(requester_id, "PENDING")

        session = MagicMock()
        session.get.return_value = appr
        current_user = _make_current_user(user_id=approver_id)

        req = ReviewPurchaseApprovalRequest(
            action="REJECT",
            reason="Sufficient stock in secondary store",
        )

        with patch("app.services.purchase_approval._approval_to_response") as mock_resp:
            mock_resp.return_value = MagicMock(spec=PurchaseApprovalResponse)
            review_purchase_approval(session, appr.id, req, current_user)

        assert appr.status == "REJECTED"
        assert appr.approved_qty == Decimal("0.0000")
        session.commit.assert_called_once()

    def test_self_approval_prohibited(self):
        from app.services.purchase_approval import review_purchase_approval

        user_id = uuid4()
        appr = self._make_approval(requested_by=user_id, status="PENDING")

        session = MagicMock()
        session.get.return_value = appr
        current_user = _make_current_user(user_id=user_id)

        req = ReviewPurchaseApprovalRequest(action="APPROVE")

        with pytest.raises(ApplicationError) as exc_info:
            review_purchase_approval(session, appr.id, req, current_user)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "SELF_APPROVAL_DENIED"

    def test_already_reviewed_prohibited(self):
        from app.services.purchase_approval import review_purchase_approval

        requester_id = uuid4()
        approver_id = uuid4()
        appr = self._make_approval(requester_id, status="APPROVED")

        session = MagicMock()
        session.get.return_value = appr
        current_user = _make_current_user(user_id=approver_id)

        req = ReviewPurchaseApprovalRequest(
            action="REJECT",
            reason="Already approved",
        )

        with pytest.raises(ApplicationError) as exc_info:
            review_purchase_approval(session, appr.id, req, current_user)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "APPROVAL_ALREADY_REVIEWED"
