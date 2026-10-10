"""FastAPI router for M5.2 — Purchase Recommendation Review & Approval Queue.

No business logic in routes. All calls delegate to app.services.purchase_approval.
"""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.purchase_approval import (
    PurchaseApprovalResponse,
    ReviewPurchaseApprovalRequest,
    SubmitPurchaseApprovalRequest,
)
from app.security.permissions import require_permissions
from app.services.purchase_approval import (
    get_approved_handoff,
    list_purchase_approvals,
    review_purchase_approval,
    submit_purchase_approval,
)

router = APIRouter(prefix="/purchasing/approvals", tags=["purchasing-approvals"])


@router.get(
    "",
    response_model=list[PurchaseApprovalResponse],
    summary="List purchase recommendations in the approval queue",
)
def get_purchase_approvals(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_permissions("purchasing:view"))],
    approval_status: Optional[str] = Query(None, alias="status"),
    consumable_id: Optional[UUID] = Query(None),
    supplier_id: Optional[UUID] = Query(None),
    planning_version_id: Optional[UUID] = Query(None),
) -> list[PurchaseApprovalResponse]:
    return list_purchase_approvals(
        session,
        status=approval_status,
        consumable_id=consumable_id,
        supplier_id=supplier_id,
        planning_version_id=planning_version_id,
    )


@router.post(
    "",
    response_model=PurchaseApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a system purchase recommendation into the approval queue",
)
def post_submit_purchase_approval(
    req: SubmitPurchaseApprovalRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("purchasing:view"))],
) -> PurchaseApprovalResponse:
    return submit_purchase_approval(session, req, current_user)


@router.patch(
    "/{approval_id}/review",
    response_model=PurchaseApprovalResponse,
    summary="Review (Approve, Modify, or Reject) a purchase recommendation",
)
def patch_review_purchase_approval(
    approval_id: UUID,
    req: ReviewPurchaseApprovalRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_permissions("purchasing:approve"))],
) -> PurchaseApprovalResponse:
    return review_purchase_approval(session, approval_id, req, current_user)


@router.get(
    "/approved-handoff",
    response_model=list[PurchaseApprovalResponse],
    summary="Get approved purchase recommendations ready for PO creation (M5.3 handoff)",
)
def get_approved_purchase_handoff(
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_permissions("purchasing:view"))],
    planning_version_id: Optional[UUID] = Query(None),
) -> list[PurchaseApprovalResponse]:
    return get_approved_handoff(
        session,
        planning_version_id=planning_version_id,
    )
