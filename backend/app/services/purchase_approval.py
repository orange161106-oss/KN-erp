"""Service layer for M5.2 — Purchase Recommendation Review & Approval Queue.

Business Rules:
  - Purchase recommendations are submitted into the approval queue with PENDING status.
  - Approvers can APPROVE (accept system recommendation as-is), MODIFY (override qty with reason), or REJECT (decline with reason).
  - Original raw_calculated_qty and system_recommended_qty are immutable.
  - Self-approval prohibition: User cannot approve their own submitted recommendation (403 SELF_APPROVAL_DENIED).
  - Every review action writes to audit_logs.
  - Approved handoff contract returns APPROVED and MODIFIED queue items for PO creation.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable, Supplier
from app.models.purchase_approval import PurchaseApproval
from app.schemas.auth import CurrentUser
from app.schemas.purchase_approval import (
    PurchaseApprovalResponse,
    ReviewPurchaseApprovalRequest,
    SubmitPurchaseApprovalRequest,
)


def _approval_to_response(appr: PurchaseApproval) -> PurchaseApprovalResponse:
    c_code: Optional[str] = None
    c_name: Optional[str] = None
    s_code: Optional[str] = None
    s_name: Optional[str] = None
    req_username: Optional[str] = None
    rev_username: Optional[str] = None

    if appr.consumable is not None:
        c_code = appr.consumable.code
        c_name = appr.consumable.name
    if appr.supplier is not None:
        s_code = appr.supplier.code
        s_name = appr.supplier.name
    if appr.requested_by_user is not None:
        req_username = appr.requested_by_user.username
    if appr.reviewed_by_user is not None:
        rev_username = appr.reviewed_by_user.username

    return PurchaseApprovalResponse(
        id=appr.id,
        consumable_id=appr.consumable_id,
        consumable_code=c_code,
        consumable_name=c_name,
        supplier_id=appr.supplier_id,
        supplier_code=s_code,
        supplier_name=s_name,
        planning_version_id=appr.planning_version_id,
        rule_version=appr.rule_version,
        raw_calculated_qty=appr.raw_calculated_qty,
        system_recommended_qty=appr.system_recommended_qty,
        approved_qty=appr.approved_qty,
        uom=appr.uom,
        status=appr.status,  # type: ignore
        reason=appr.reason,
        requested_by=appr.requested_by,
        requested_by_username=req_username,
        reviewed_by=appr.reviewed_by,
        reviewed_by_username=rev_username,
        reviewed_at=appr.reviewed_at,
        created_at=appr.created_at,
        updated_at=appr.updated_at,
    )


def list_purchase_approvals(
    session: Session,
    *,
    status: Optional[str] = None,
    consumable_id: Optional[UUID] = None,
    supplier_id: Optional[UUID] = None,
    planning_version_id: Optional[UUID] = None,
) -> list[PurchaseApprovalResponse]:
    stmt = select(PurchaseApproval)
    if status:
        stmt = stmt.where(PurchaseApproval.status == status)
    if consumable_id:
        stmt = stmt.where(PurchaseApproval.consumable_id == consumable_id)
    if supplier_id:
        stmt = stmt.where(PurchaseApproval.supplier_id == supplier_id)
    if planning_version_id:
        stmt = stmt.where(PurchaseApproval.planning_version_id == planning_version_id)

    stmt = stmt.order_by(
        desc(PurchaseApproval.status == "PENDING"),
        desc(PurchaseApproval.created_at),
    )
    rows = session.execute(stmt).scalars().all()
    return [_approval_to_response(r) for r in rows]


def submit_purchase_approval(
    session: Session,
    req: SubmitPurchaseApprovalRequest,
    current_user: CurrentUser,
) -> PurchaseApprovalResponse:
    consumable = session.get(Consumable, req.consumable_id)
    if not consumable or not consumable.is_active:
        raise ApplicationError("CONSUMABLE_NOT_FOUND", "Active consumable not found.", 404)

    supplier = session.get(Supplier, req.supplier_id)
    if not supplier or not supplier.is_active:
        raise ApplicationError("SUPPLIER_NOT_FOUND", "Active supplier not found.", 404)

    approval = PurchaseApproval(
        consumable_id=req.consumable_id,
        supplier_id=req.supplier_id,
        planning_version_id=req.planning_version_id,
        rule_version="M5.1_V1",
        raw_calculated_qty=req.raw_calculated_qty,
        system_recommended_qty=req.system_recommended_qty,
        approved_qty=None,
        uom=req.uom,
        status="PENDING",
        reason=req.reason,
        requested_by=current_user.id,
    )
    session.add(approval)
    session.commit()
    session.refresh(approval)
    return _approval_to_response(approval)


def review_purchase_approval(
    session: Session,
    approval_id: UUID,
    req: ReviewPurchaseApprovalRequest,
    current_user: CurrentUser,
) -> PurchaseApprovalResponse:
    approval = session.get(PurchaseApproval, approval_id)
    if not approval:
        raise ApplicationError("APPROVAL_NOT_FOUND", "Purchase approval item not found.", 404)

    if approval.status != "PENDING":
        raise ApplicationError(
            "APPROVAL_ALREADY_REVIEWED",
            f"Purchase approval item is already in status '{approval.status}'.",
            409,
        )

    # Self-approval prohibition
    if approval.requested_by and approval.requested_by == current_user.id:
        raise ApplicationError(
            "SELF_APPROVAL_DENIED",
            "You cannot approve or reject your own purchase recommendation submission.",
            403,
        )

    now = datetime.now(timezone.utc)
    old_status = approval.status

    if req.action == "APPROVE":
        approval.status = "APPROVED"
        approval.approved_qty = approval.system_recommended_qty
    elif req.action == "MODIFY":
        if req.approved_qty is None or req.approved_qty <= Decimal("0"):
            raise ApplicationError(
                "INVALID_APPROVED_QTY",
                "Approved quantity must be positive when modifying a recommendation.",
                422,
            )
        approval.status = "MODIFIED"
        approval.approved_qty = req.approved_qty
        approval.reason = req.reason
    elif req.action == "REJECT":
        approval.status = "REJECTED"
        approval.approved_qty = Decimal("0.0000")
        approval.reason = req.reason

    approval.reviewed_by = current_user.id
    approval.reviewed_at = now

    audit = AuditLog(
        actor_id=current_user.id,
        action="REVIEW",
        entity_type="purchase_approval",
        entity_id=approval.id,
        old_values={"status": old_status},
        new_values={
            "status": approval.status,
            "approved_qty": str(approval.approved_qty),
            "reason": approval.reason,
            "reviewed_by": str(current_user.id),
        },
        reason=f"Purchase recommendation {approval.status.lower()} by reviewer.",
    )
    session.add(audit)
    session.commit()
    session.refresh(approval)
    return _approval_to_response(approval)


def get_approved_handoff(
    session: Session,
    *,
    planning_version_id: Optional[UUID] = None,
) -> list[PurchaseApprovalResponse]:
    """Return authoritative approved purchase recommendations ready for PO creation (M5.3)."""
    stmt = select(PurchaseApproval).where(
        PurchaseApproval.status.in_(["APPROVED", "MODIFIED"])
    )
    if planning_version_id:
        stmt = stmt.where(PurchaseApproval.planning_version_id == planning_version_id)

    stmt = stmt.order_by(desc(PurchaseApproval.reviewed_at))
    rows = session.execute(stmt).scalars().all()
    return [_approval_to_response(r) for r in rows]
