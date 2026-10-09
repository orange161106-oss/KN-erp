"""Service layer for M3.4 — Plant Confirmation & Additional Requirement Workflow.

All business rules are here. FastAPI routes call these functions only.
No business logic in routes.

Rules enforced:
  - calculated_qty is NEVER modified (read-only from Yathish's domain)
  - Only plant users (plant_workflow:confirm / plant_workflow:request) may act
  - Users can only act within plants they are assigned to (user_plants)
  - Adjustment reason must be non-blank
  - Adjustment requested_qty must be > 0 (enforced by Pydantic + guarded here)
  - Withdrawing an adjustment is only allowed if status is PENDING and actor is the requester
  - Every mutation writes to audit_logs
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable, Unit
from app.models.plant_workflow import PlantConfirmation, RequirementAdjustment, UserPlant
from app.models.production import Plant
from app.models.requirements import CalculatedRequirement
from app.schemas.auth import CurrentUser
from app.schemas.plant_workflow import (
    ConfirmRequirementRequest,
    FinalRequirementItemResponse,
    PlantConfirmationResponse,
    RequirementAdjustmentResponse,
    ReviewAdjustmentRequest,
    SubmitAdjustmentRequest,
    UserPlantAssignRequest,
    UserPlantResponse,
)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _get_user_plant_ids(session: Session, user_id: UUID) -> set[UUID]:
    """Return the set of plant IDs the user is authorised to act within."""
    rows = session.execute(
        select(UserPlant.plant_id).where(UserPlant.user_id == user_id)
    ).scalars().all()
    return set(rows)


def _assert_plant_access(session: Session, user: CurrentUser, plant_id: UUID) -> None:
    """Raise 403 if the user is not assigned to the given plant."""
    plant = session.get(Plant, plant_id)
    if plant is None or not plant.is_active:
        raise ApplicationError("PLANT_NOT_FOUND", "An active plant is required.", 422)
    if not user.is_super_admin and plant_id not in user.plant_ids:
        raise ApplicationError(
            "PLANT_ACCESS_DENIED",
            "You are not authorised to act on behalf of this plant.",
            403,
        )


def _write_audit(
    session: Session,
    *,
    actor_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new_values: dict,
    old_values: Optional[dict] = None,
    reason: str,
) -> None:
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old_values,
        new_values=new_values,
        reason=reason,
    )
    session.add(log)


def _confirmation_to_response(conf: PlantConfirmation) -> PlantConfirmationResponse:
    plant_name: Optional[str] = None
    username: Optional[str] = None
    if conf.plant is not None:
        plant_name = conf.plant.name
    if conf.confirmed_by_user is not None:
        username = conf.confirmed_by_user.username
    return PlantConfirmationResponse(
        id=conf.id,
        calculated_requirement_id=conf.calculated_requirement_id,
        planning_version_id=conf.planning_version_id,
        plant_id=conf.plant_id,
        plant_name=plant_name,
        confirmed_by=conf.confirmed_by,
        confirmed_by_username=username,
        confirmed_at=conf.confirmed_at,
        notes=conf.notes,
    )


def _adjustment_to_response(adj: RequirementAdjustment) -> RequirementAdjustmentResponse:
    plant_name: Optional[str] = None
    consumable_code: Optional[str] = None
    consumable_name: Optional[str] = None
    username: Optional[str] = None
    if adj.plant is not None:
        plant_name = adj.plant.name
    if adj.consumable is not None:
        consumable_code = adj.consumable.code
        consumable_name = adj.consumable.name
    if adj.requested_by_user is not None:
        username = adj.requested_by_user.username
    return RequirementAdjustmentResponse(
        id=adj.id,
        planning_version_id=adj.planning_version_id,
        plant_id=adj.plant_id,
        plant_name=plant_name,
        consumable_id=adj.consumable_id,
        consumable_code=consumable_code,
        consumable_name=consumable_name,
        category=adj.category,
        requested_qty=adj.requested_qty,
        uom=adj.uom,
        reason=adj.reason,
        requested_by=adj.requested_by,
        requested_by_username=username,
        requested_at=adj.requested_at,
        status=adj.status,
        reviewed_by=adj.reviewed_by,
        reviewed_at=adj.reviewed_at,
        reviewer_comment=adj.reviewer_comment,
    )


# ── UserPlant management ───────────────────────────────────────────────────────

def assign_user_to_plant(
    session: Session,
    req: UserPlantAssignRequest,
    current_user: CurrentUser,
) -> UserPlantResponse:
    """Assign a user to a plant. Idempotent — returns existing record if already assigned."""
    existing = session.execute(
        select(UserPlant).where(
            UserPlant.user_id == req.user_id,
            UserPlant.plant_id == req.plant_id,
        )
    ).scalar_one_or_none()

    if existing:
        return UserPlantResponse.model_validate(existing)

    assignment = UserPlant(
        user_id=req.user_id,
        plant_id=req.plant_id,
        assigned_by=current_user.id,
    )
    session.add(assignment)
    _write_audit(
        session,
        actor_id=current_user.id,
        action="CREATE",
        entity_type="user_plant",
        entity_id=assignment.id,
        new_values={"user_id": str(req.user_id), "plant_id": str(req.plant_id)},
        reason="User assigned to plant.",
    )
    session.commit()
    session.refresh(assignment)
    return UserPlantResponse.model_validate(assignment)


def list_user_plants(session: Session, user_id: UUID) -> list[UserPlantResponse]:
    rows = session.execute(
        select(UserPlant).where(UserPlant.user_id == user_id)
    ).scalars().all()
    return [UserPlantResponse.model_validate(r) for r in rows]


def remove_user_from_plant(
    session: Session,
    assignment_id: UUID,
    current_user: CurrentUser,
) -> None:
    assignment = session.get(UserPlant, assignment_id)
    if not assignment:
        raise ApplicationError("USER_PLANT_NOT_FOUND", "Assignment not found.", 404)
    _write_audit(
        session,
        actor_id=current_user.id,
        action="DELETE",
        entity_type="user_plant",
        entity_id=assignment.id,
        new_values={},
        old_values={"user_id": str(assignment.user_id), "plant_id": str(assignment.plant_id)},
        reason="User removed from plant.",
    )
    session.delete(assignment)
    session.commit()


# ── Plant Confirmation ─────────────────────────────────────────────────────────

def list_confirmations(
    session: Session,
    *,
    planning_version_id: Optional[UUID] = None,
    plant_id: Optional[UUID] = None,
    allowed_plant_ids: list[UUID] | None = None,
) -> list[PlantConfirmationResponse]:
    stmt = select(PlantConfirmation)
    if allowed_plant_ids is not None:
        stmt = stmt.where(PlantConfirmation.plant_id.in_(allowed_plant_ids))
    if planning_version_id:
        stmt = stmt.where(PlantConfirmation.planning_version_id == planning_version_id)
    if plant_id:
        stmt = stmt.where(PlantConfirmation.plant_id == plant_id)
    rows = session.execute(stmt).scalars().all()
    return [_confirmation_to_response(r) for r in rows]


def confirm_requirement(
    session: Session,
    req: ConfirmRequirementRequest,
    current_user: CurrentUser,
) -> PlantConfirmationResponse:
    """Confirm a calculated requirement on behalf of the requesting user's plant.

    Rules:
      - The CalculatedRequirement must exist.
      - The user must be assigned to the requirement's plant.
      - Only one confirmation per calculated requirement (unique constraint).
      - calculated_qty is NEVER modified.
    """
    calc_req = session.get(CalculatedRequirement, req.calculated_requirement_id)
    if not calc_req:
        raise ApplicationError(
            "CALCULATED_REQUIREMENT_NOT_FOUND",
            "Calculated requirement not found.",
            404,
        )

    # Plant-scope security — server enforced
    _assert_plant_access(session, current_user, calc_req.plant_id)

    # Idempotency check — one confirmation per calculated requirement
    existing = session.execute(
        select(PlantConfirmation).where(
            PlantConfirmation.calculated_requirement_id == req.calculated_requirement_id
        )
    ).scalar_one_or_none()
    if existing:
        raise ApplicationError(
            "CONFIRMATION_EXISTS",
            "This calculated requirement has already been confirmed.",
            409,
        )

    confirmation = PlantConfirmation(
        calculated_requirement_id=req.calculated_requirement_id,
        planning_version_id=calc_req.planning_version_id,
        plant_id=calc_req.plant_id,
        confirmed_by=current_user.id,
        notes=req.notes,
    )
    session.add(confirmation)
    _write_audit(
        session,
        actor_id=current_user.id,
        action="CONFIRM",
        entity_type="plant_confirmation",
        entity_id=confirmation.id,
        new_values={
            "calculated_requirement_id": str(req.calculated_requirement_id),
            "planning_version_id": str(calc_req.planning_version_id),
            "plant_id": str(calc_req.plant_id),
            "notes": req.notes,
        },
        reason="Plant confirmation submitted.",
    )
    session.commit()
    session.refresh(confirmation)
    return _confirmation_to_response(confirmation)


def retract_confirmation(
    session: Session,
    confirmation_id: UUID,
    current_user: CurrentUser,
) -> None:
    """Retract a confirmation. Only allowed while the planning version is not locked.

    Version locking is introduced in M3.5. Until then retraction is freely allowed
    for any user assigned to the same plant.
    """
    confirmation = session.get(PlantConfirmation, confirmation_id)
    if not confirmation:
        raise ApplicationError("CONFIRMATION_NOT_FOUND", "Confirmation not found.", 404)

    # Plant-scope security
    _assert_plant_access(session, current_user, confirmation.plant_id)

    _write_audit(
        session,
        actor_id=current_user.id,
        action="RETRACT",
        entity_type="plant_confirmation",
        entity_id=confirmation.id,
        old_values={
            "calculated_requirement_id": str(confirmation.calculated_requirement_id),
            "plant_id": str(confirmation.plant_id),
            "confirmed_by": str(confirmation.confirmed_by),
        },
        new_values={},
        reason="Plant confirmation retracted.",
    )
    session.delete(confirmation)
    session.commit()


# ── Requirement Adjustment ─────────────────────────────────────────────────────

def list_adjustments(
    session: Session,
    *,
    planning_version_id: Optional[UUID] = None,
    plant_id: Optional[UUID] = None,
    status: Optional[str] = None,
    allowed_plant_ids: list[UUID] | None = None,
) -> list[RequirementAdjustmentResponse]:
    stmt = select(RequirementAdjustment)
    if allowed_plant_ids is not None:
        stmt = stmt.where(RequirementAdjustment.plant_id.in_(allowed_plant_ids))
    if planning_version_id:
        stmt = stmt.where(RequirementAdjustment.planning_version_id == planning_version_id)
    if plant_id:
        stmt = stmt.where(RequirementAdjustment.plant_id == plant_id)
    if status:
        stmt = stmt.where(RequirementAdjustment.status == status)
    rows = session.execute(stmt).scalars().all()
    return [_adjustment_to_response(r) for r in rows]


def submit_adjustment(
    session: Session,
    req: SubmitAdjustmentRequest,
    current_user: CurrentUser,
) -> RequirementAdjustmentResponse:
    """Submit an additional consumable requirement beyond the calculated quantity.

    Rules:
      - User must be assigned to req.plant_id.
      - requested_qty must be > 0 (Pydantic + guard).
      - reason must be non-blank (Pydantic + guard).
      - uom is copied from the consumable's unit at submission time.
      - Does NOT modify or replace any calculated_requirement.
    """
    # Plant-scope security
    _assert_plant_access(session, current_user, req.plant_id)

    # Guard — Pydantic already enforces > 0 but be explicit in service layer
    if req.requested_qty <= Decimal("0"):
        raise ApplicationError(
            "INVALID_QUANTITY",
            "requested_qty must be greater than zero.",
            422,
        )

    # Resolve consumable and copy UOM (denormalised same as calculated_requirements pattern)
    consumable = session.get(Consumable, req.consumable_id)
    if not consumable:
        raise ApplicationError("CONSUMABLE_NOT_FOUND", "Consumable not found.", 404)
    if not consumable.is_active:
        raise ApplicationError(
            "CONSUMABLE_INACTIVE", "Cannot request an inactive consumable.", 422
        )

    # Resolve UOM from consumable's unit
    unit = session.execute(
        select(Unit).where(Unit.id == consumable.unit_id)
    ).scalar_one_or_none()
    uom = unit.code if unit else "UNK"

    adjustment = RequirementAdjustment(
        planning_version_id=req.planning_version_id,
        plant_id=req.plant_id,
        consumable_id=req.consumable_id,
        category=req.category,
        requested_qty=req.requested_qty,
        uom=uom,
        reason=req.reason.strip(),
        requested_by=current_user.id,
        status="PENDING",
    )
    session.add(adjustment)
    _write_audit(
        session,
        actor_id=current_user.id,
        action="CREATE",
        entity_type="requirement_adjustment",
        entity_id=adjustment.id,
        new_values={
            "planning_version_id": str(req.planning_version_id),
            "plant_id": str(req.plant_id),
            "consumable_id": str(req.consumable_id),
            "category": req.category,
            "requested_qty": str(req.requested_qty),
            "uom": uom,
            "reason": req.reason.strip(),
        },
        reason="Additional requirement submitted.",
    )
    session.commit()
    session.refresh(adjustment)
    return _adjustment_to_response(adjustment)


def withdraw_adjustment(
    session: Session,
    adjustment_id: UUID,
    current_user: CurrentUser,
) -> None:
    """Withdraw a PENDING adjustment. Only the original requester may withdraw.

    Approved or rejected adjustments cannot be withdrawn.
    """
    adjustment = session.get(RequirementAdjustment, adjustment_id)
    if not adjustment:
        raise ApplicationError("ADJUSTMENT_NOT_FOUND", "Adjustment not found.", 404)

    # Plant-scope security
    _assert_plant_access(session, current_user, adjustment.plant_id)

    # Only the original requester may withdraw
    if adjustment.requested_by != current_user.id:
        raise ApplicationError(
            "WITHDRAWAL_DENIED",
            "Only the original requester may withdraw an adjustment.",
            403,
        )

    # Only PENDING adjustments may be withdrawn
    if adjustment.status != "PENDING":
        raise ApplicationError(
            "ADJUSTMENT_NOT_PENDING",
            f"Cannot withdraw an adjustment with status '{adjustment.status}'.",
            409,
        )

    _write_audit(
        session,
        actor_id=current_user.id,
        action="WITHDRAW",
        entity_type="requirement_adjustment",
        entity_id=adjustment.id,
        old_values={
            "consumable_id": str(adjustment.consumable_id),
            "requested_qty": str(adjustment.requested_qty),
            "status": adjustment.status,
            "reason": adjustment.reason,
        },
        new_values={},
        reason="Additional requirement withdrawn by requester.",
    )
    session.delete(adjustment)
    session.commit()


def review_adjustment(
    session: Session,
    adjustment_id: UUID,
    req: ReviewAdjustmentRequest,
    current_user: CurrentUser,
) -> RequirementAdjustmentResponse:
    """Approve or reject a pending additional requirement adjustment.

    Rules:
      - Adjustment must exist and be PENDING.
      - User cannot approve/reject their own request (prevent self-approval).
      - Original requested_qty and reason are IMMUTABLE.
      - Audit log is written.
    """
    adjustment = session.get(RequirementAdjustment, adjustment_id)
    if not adjustment:
        raise ApplicationError("ADJUSTMENT_NOT_FOUND", "Adjustment not found.", 404)

    _assert_plant_access(session, current_user, adjustment.plant_id)

    if adjustment.status != "PENDING":
        raise ApplicationError(
            "ADJUSTMENT_ALREADY_REVIEWED",
            f"Adjustment has already been reviewed (status: '{adjustment.status}').",
            409,
        )

    # Self-approval prohibition
    if adjustment.requested_by == current_user.id:
        raise ApplicationError(
            "SELF_APPROVAL_DENIED",
            "You cannot approve or reject your own additional requirement request.",
            403,
        )

    adjustment.status = req.status
    adjustment.reviewed_by = current_user.id
    adjustment.reviewed_at = datetime.now(timezone.utc)
    adjustment.reviewer_comment = req.reviewer_comment

    _write_audit(
        session,
        actor_id=current_user.id,
        action="REVIEW",
        entity_type="requirement_adjustment",
        entity_id=adjustment.id,
        old_values={"status": "PENDING"},
        new_values={
            "status": req.status,
            "reviewer_comment": req.reviewer_comment,
        },
        reason=f"Additional requirement {req.status.lower()} by reviewer.",
    )
    session.commit()
    session.refresh(adjustment)
    return _adjustment_to_response(adjustment)


def get_final_requirements(
    session: Session,
    *,
    planning_version_id: UUID,
    plant_id: Optional[UUID] = None,
    consumable_id: Optional[UUID] = None,
    allowed_plant_ids: list[UUID] | None = None,
) -> list[FinalRequirementItemResponse]:
    """Calculate and return the authoritative Final Requirements for a planning version.

    Final Requirement = Calculated Production Requirement + Approved Adjustments.
    Only requirement adjustments with status = 'APPROVED' are included.
    """
    # 1. Fetch calculated requirement totals grouped by (plant_id, consumable_id)
    calc_stmt = (
        select(
            CalculatedRequirement.plant_id,
            CalculatedRequirement.consumable_id,
            func.sum(CalculatedRequirement.calculated_qty).label("total_calc_qty"),
            func.count(CalculatedRequirement.id).label("total_calc_count"),
        )
        .where(CalculatedRequirement.planning_version_id == planning_version_id)
    )
    if allowed_plant_ids is not None:
        calc_stmt = calc_stmt.where(CalculatedRequirement.plant_id.in_(allowed_plant_ids))
    if plant_id:
        calc_stmt = calc_stmt.where(CalculatedRequirement.plant_id == plant_id)
    if consumable_id:
        calc_stmt = calc_stmt.where(CalculatedRequirement.consumable_id == consumable_id)
    calc_stmt = calc_stmt.group_by(CalculatedRequirement.plant_id, CalculatedRequirement.consumable_id)
    calc_rows = session.execute(calc_stmt).all()

    calc_map: dict[tuple[UUID, UUID], tuple[Decimal, int]] = {
        (row.plant_id, row.consumable_id): (Decimal(str(row.total_calc_qty)), row.total_calc_count)
        for row in calc_rows
    }

    # 2. Fetch confirmations count grouped by (plant_id, consumable_id)
    conf_stmt = (
        select(
            PlantConfirmation.plant_id,
            CalculatedRequirement.consumable_id,
            func.count(PlantConfirmation.id).label("confirmed_count"),
        )
        .join(CalculatedRequirement, PlantConfirmation.calculated_requirement_id == CalculatedRequirement.id)
        .where(PlantConfirmation.planning_version_id == planning_version_id)
    )
    if plant_id:
        conf_stmt = conf_stmt.where(PlantConfirmation.plant_id == plant_id)
    if consumable_id:
        conf_stmt = conf_stmt.where(CalculatedRequirement.consumable_id == consumable_id)
    conf_stmt = conf_stmt.group_by(PlantConfirmation.plant_id, CalculatedRequirement.consumable_id)
    conf_rows = session.execute(conf_stmt).all()

    conf_map: dict[tuple[UUID, UUID], int] = {
        (row.plant_id, row.consumable_id): row.confirmed_count
        for row in conf_rows
    }

    # 3. Fetch approved adjustments grouped by (plant_id, consumable_id)
    adj_stmt = (
        select(
            RequirementAdjustment.plant_id,
            RequirementAdjustment.consumable_id,
            func.sum(RequirementAdjustment.requested_qty).label("total_adj_qty"),
        )
        .where(
            RequirementAdjustment.planning_version_id == planning_version_id,
            RequirementAdjustment.status == "APPROVED",
        )
    )
    if allowed_plant_ids is not None:
        adj_stmt = adj_stmt.where(RequirementAdjustment.plant_id.in_(allowed_plant_ids))
    if plant_id:
        adj_stmt = adj_stmt.where(RequirementAdjustment.plant_id == plant_id)
    if consumable_id:
        adj_stmt = adj_stmt.where(RequirementAdjustment.consumable_id == consumable_id)
    adj_stmt = adj_stmt.group_by(RequirementAdjustment.plant_id, RequirementAdjustment.consumable_id)
    adj_rows = session.execute(adj_stmt).all()

    adj_map: dict[tuple[UUID, UUID], Decimal] = {
        (row.plant_id, row.consumable_id): Decimal(str(row.total_adj_qty))
        for row in adj_rows
    }

    # Combine all unique (plant_id, consumable_id) pairs
    all_keys = set(calc_map.keys()) | set(adj_map.keys())

    # Pre-fetch plants and consumables for metadata
    plant_ids = {k[0] for k in all_keys}
    consumable_ids = {k[1] for k in all_keys}

    plants: dict[UUID, str] = {}
    if plant_ids:
        p_rows = session.execute(select(Plant).where(Plant.id.in_(plant_ids))).scalars().all()
        plants = {p.id: p.name for p in p_rows}

    consumables: dict[UUID, Consumable] = {}
    if consumable_ids:
        c_rows = session.execute(select(Consumable).where(Consumable.id.in_(consumable_ids))).scalars().all()
        consumables = {c.id: c for c in c_rows}

    units: dict[UUID, str] = {}
    unit_ids = {c.unit_id for c in consumables.values() if c.unit_id}
    if unit_ids:
        u_rows = session.execute(select(Unit).where(Unit.id.in_(unit_ids))).scalars().all()
        units = {u.id: u.code for u in u_rows}

    results: list[FinalRequirementItemResponse] = []
    for p_id, c_id in sorted(all_keys, key=lambda k: (plants.get(k[0], ""), consumables[k[1]].code if k[1] in consumables else "")):
        calc_qty, calc_count = calc_map.get((p_id, c_id), (Decimal("0"), 0))
        adj_qty = adj_map.get((p_id, c_id), Decimal("0"))
        final_qty = calc_qty + adj_qty

        confirmed_count = conf_map.get((p_id, c_id), 0)
        is_fully_confirmed = (calc_count > 0) and (confirmed_count == calc_count)

        c_obj = consumables.get(c_id)
        uom_str = units.get(c_obj.unit_id, "UNK") if c_obj else "UNK"

        results.append(
            FinalRequirementItemResponse(
                planning_version_id=planning_version_id,
                plant_id=p_id,
                plant_name=plants.get(p_id),
                consumable_id=c_id,
                consumable_code=c_obj.code if c_obj else None,
                consumable_name=c_obj.name if c_obj else None,
                uom=uom_str,
                calculated_qty=calc_qty,
                approved_adjustment_qty=adj_qty,
                final_required_qty=final_qty,
                is_fully_confirmed=is_fully_confirmed,
            )
        )

    return results

