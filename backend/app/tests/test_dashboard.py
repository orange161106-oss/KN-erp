"""Unit tests for M6.3 — Executive Management Dashboard."""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestDashboardSummary:
    """get_dashboard_summary service function."""

    def test_dashboard_summary_success(self):
        from app.services.dashboard import get_dashboard_summary

        session = MagicMock()
        session.execute.side_effect = [
            MagicMock(scalar_one=lambda: 2),  # active critical alerts
            MagicMock(scalar_one=lambda: 5),  # active warning alerts
            MagicMock(scalar_one=lambda: 3),  # pending purchase approvals
            MagicMock(scalar_one=lambda: 1),  # pending plant adjustments
            MagicMock(scalar_one=lambda: 4),  # issued pending pos
            MagicMock(scalar_one=lambda: 10),  # total active consumables
            MagicMock(scalar_one=lambda: Decimal("1000.0000")),  # tot_calc_qty
            MagicMock(scalar_one=lambda: Decimal("200.0000")),   # tot_approved_adj_qty
            MagicMock(scalar_one=lambda: Decimal("1200.0000")),  # tot_recommended_qty
            MagicMock(scalar_one=lambda: Decimal("1100.0000")),  # tot_approved_purchase_qty
            MagicMock(scalar_one=lambda: Decimal("1000.0000")),  # tot_ordered_qty
            MagicMock(scalar_one=lambda: Decimal("800.0000")),   # tot_grn_accepted_qty
        ]

        res = get_dashboard_summary(session)

        assert res.active_critical_alerts == 2
        assert res.active_warning_alerts == 5
        assert res.pending_purchase_approvals == 3
        assert res.pending_plant_adjustments == 1
        assert res.issued_pending_pos == 4
        assert res.total_active_consumables == 10

        p = res.pipeline_summary
        assert p.total_calculated_quantity == Decimal("1000.0000")
        assert p.total_approved_additions == Decimal("200.0000")
        assert p.total_final_requirement == Decimal("1200.0000")
        assert p.total_recommended_quantity == Decimal("1200.0000")
        assert p.total_approved_purchase_quantity == Decimal("1100.0000")
        assert p.total_ordered_quantity == Decimal("1000.0000")
        assert p.total_accepted_grn_quantity == Decimal("800.0000")
