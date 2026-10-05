"""Unit tests for M4.4 — Inventory & MSL Alerts Workflow."""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.errors import ApplicationError
from app.models.alerts import InventoryAlert
from app.schemas.alerts import InventoryAlertResponse


def _make_current_user(user_id=None, permissions=None):
    from app.schemas.auth import CurrentUser
    return CurrentUser(
        id=user_id or uuid4(),
        username="alert_user",
        roles=["STORE"],
        permissions=permissions or ["alerts:view", "alerts:acknowledge"],
    )


class TestAcknowledgeAlert:
    """acknowledge_alert service function."""

    def test_acknowledge_success(self):
        from app.services.alerts import acknowledge_alert

        user_id = uuid4()
        alert_id = uuid4()
        alert = MagicMock(spec=InventoryAlert)
        alert.id = alert_id
        alert.status = "ACTIVE"

        current_user = _make_current_user(user_id=user_id)
        session = MagicMock()
        session.get.return_value = alert

        with patch("app.services.alerts._alert_to_response") as mock_resp:
            mock_resp.return_value = MagicMock(spec=InventoryAlertResponse)
            acknowledge_alert(session, alert_id, current_user, notes="Reviewed")

        assert alert.status == "ACKNOWLEDGED"
        assert alert.acknowledged_by == user_id
        session.add.assert_called()
        session.commit.assert_called_once()

    def test_acknowledge_nonexistent_returns_404(self):
        from app.services.alerts import acknowledge_alert

        current_user = _make_current_user()
        session = MagicMock()
        session.get.return_value = None

        with pytest.raises(ApplicationError) as exc_info:
            acknowledge_alert(session, uuid4(), current_user)

        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "ALERT_NOT_FOUND"

    def test_acknowledge_already_acknowledged_returns_409(self):
        from app.services.alerts import acknowledge_alert

        alert_id = uuid4()
        alert = MagicMock(spec=InventoryAlert)
        alert.id = alert_id
        alert.status = "ACKNOWLEDGED"

        current_user = _make_current_user()
        session = MagicMock()
        session.get.return_value = alert

        with pytest.raises(ApplicationError) as exc_info:
            acknowledge_alert(session, alert_id, current_user)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "ALERT_ALREADY_ACKNOWLEDGED"


class TestAlertEvaluation:
    """evaluate_inventory_alerts service function."""

    def test_evaluation_summary_counts(self):
        from app.services.alerts import evaluate_inventory_alerts

        c1 = MagicMock()
        c1.id = uuid4()
        c1.code = "CONS01"
        c1.unit_id = uuid4()
        c1.is_active = True

        snap1 = MagicMock()
        snap1.consumable_id = c1.id
        snap1.usable_quantity = Decimal("10.0000")  # Below MSL floor 100

        unit = MagicMock()
        unit.id = c1.unit_id
        unit.code = "PCS"

        session = MagicMock()
        exec_mock = session.execute

        exec_mock.side_effect = [
            MagicMock(scalars=lambda: MagicMock(all=lambda: [c1])),  # MSL consumables
            MagicMock(scalars=lambda: MagicMock(all=lambda: [unit])),  # MSL units
            MagicMock(scalars=lambda: MagicMock(all=lambda: [snap1])),  # latest snapshots
            MagicMock(scalar_one_or_none=lambda: None),  # BELOW_MSL check
            MagicMock(scalar_one_or_none=lambda: None),  # LOW_STOCK check
            MagicMock(scalars=lambda: MagicMock(all=lambda: [c1])),  # PO consumables
            MagicMock(scalars=lambda: MagicMock(all=lambda: [unit])),  # PO units
            MagicMock(all=lambda: []),  # PO items
            MagicMock(all=lambda: []),  # GRN sums
            MagicMock(scalar_one_or_none=lambda: None),  # PO_OVERDUE check
            MagicMock(scalar_one_or_none=lambda: None),  # PO_DUE_SOON check
            MagicMock(scalar_one=lambda: 1),  # active critical count
            MagicMock(scalar_one=lambda: 0),  # active warning count
            MagicMock(scalar_one=lambda: 0),  # active info count
        ]

        summary = evaluate_inventory_alerts(session)
        assert summary.total_evaluated == 1
        assert summary.active_critical_count == 1


class TestPODeliveryAlerts:
    """_evaluate_po_delivery_alerts logic."""

    def test_po_overdue_created(self):
        from datetime import datetime, timedelta, timezone
        from app.services.alerts import _evaluate_po_delivery_alerts

        c1 = MagicMock()
        c1.id = uuid4()
        c1.code = "ITEM01"
        c1.unit_id = uuid4()
        c1.is_active = True

        unit = MagicMock()
        unit.id = c1.unit_id
        unit.code = "PCS"

        po_item = MagicMock()
        po_item.id = uuid4()
        po_item.consumable_id = c1.id
        po_item.ordered_quantity = Decimal("50.0000")
        po_item.expected_delivery = datetime.now(timezone.utc) - timedelta(days=2)

        session = MagicMock()
        session.execute.side_effect = [
            MagicMock(scalars=lambda: MagicMock(all=lambda: [c1])),
            MagicMock(scalars=lambda: MagicMock(all=lambda: [unit])),
            MagicMock(all=lambda: [(po_item, "PO-001")]),  # po items
            MagicMock(all=lambda: []),  # grn sums (0 received)
            MagicMock(scalar_one_or_none=lambda: None),  # existing PO_OVERDUE check
            MagicMock(scalar_one_or_none=lambda: None),  # existing PO_DUE_SOON check
        ]

        counts = {"created": 0, "updated": 0}
        _evaluate_po_delivery_alerts(session, counts)

        assert counts["created"] == 1
        session.add.assert_called()
        added_alert = session.add.call_args[0][0]
        assert added_alert.alert_type == "PO_OVERDUE"
        assert added_alert.severity == "CRITICAL"

    def test_po_due_soon_created(self):
        from datetime import datetime, timedelta, timezone
        from app.services.alerts import _evaluate_po_delivery_alerts

        c1 = MagicMock()
        c1.id = uuid4()
        c1.code = "ITEM02"
        c1.unit_id = uuid4()
        c1.is_active = True

        unit = MagicMock()
        unit.id = c1.unit_id
        unit.code = "PCS"

        po_item = MagicMock()
        po_item.id = uuid4()
        po_item.consumable_id = c1.id
        po_item.ordered_quantity = Decimal("100.0000")
        po_item.expected_delivery = datetime.now(timezone.utc) + timedelta(days=1)

        session = MagicMock()
        session.execute.side_effect = [
            MagicMock(scalars=lambda: MagicMock(all=lambda: [c1])),
            MagicMock(scalars=lambda: MagicMock(all=lambda: [unit])),
            MagicMock(all=lambda: [(po_item, "PO-002")]),  # po items
            MagicMock(all=lambda: []),  # grn sums (0 received)
            MagicMock(scalar_one_or_none=lambda: None),  # existing PO_OVERDUE check
            MagicMock(scalar_one_or_none=lambda: None),  # existing PO_DUE_SOON check
        ]

        counts = {"created": 0, "updated": 0}
        _evaluate_po_delivery_alerts(session, counts)

        assert counts["created"] == 1
        session.add.assert_called()
        added_alert = session.add.call_args[0][0]
        assert added_alert.alert_type == "PO_DUE_SOON"
        assert added_alert.severity == "WARNING"

    def test_grn_full_receipt_resolves_active_po_alert(self):
        from datetime import datetime, timedelta, timezone
        from app.services.alerts import _evaluate_po_delivery_alerts

        c1 = MagicMock()
        c1.id = uuid4()
        c1.code = "ITEM03"
        c1.unit_id = uuid4()
        c1.is_active = True

        unit = MagicMock()
        unit.id = c1.unit_id
        unit.code = "PCS"

        po_item = MagicMock()
        po_item.id = uuid4()
        po_item.consumable_id = c1.id
        po_item.ordered_quantity = Decimal("50.0000")
        po_item.expected_delivery = datetime.now(timezone.utc) - timedelta(days=5)

        existing_alert = MagicMock()
        existing_alert.status = "ACTIVE"

        session = MagicMock()
        session.execute.side_effect = [
            MagicMock(scalars=lambda: MagicMock(all=lambda: [c1])),
            MagicMock(scalars=lambda: MagicMock(all=lambda: [unit])),
            MagicMock(all=lambda: [(po_item, "PO-003")]),  # po items
            MagicMock(all=lambda: [(po_item.id, Decimal("50.0000"))]),  # grn sums (50/50 received)
            MagicMock(scalar_one_or_none=lambda: existing_alert),  # existing PO_OVERDUE check
            MagicMock(scalar_one_or_none=lambda: None),  # existing PO_DUE_SOON check
        ]

        counts = {"created": 0, "updated": 0}
        _evaluate_po_delivery_alerts(session, counts)

        assert existing_alert.status == "RESOLVED"

