import calendar
from datetime import datetime, timezone
from decimal import Decimal
import io
from typing import Optional
from uuid import UUID

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.models.inventory_masters import Consumable, Supplier, SupplierConsumable, Unit
from app.models.prd import PlanningVersion, PRDOrderItem
from app.models.masters import Product
from app.models.production import Process
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_order import PurchaseDemandEvidence
from app.models.purchase_plan import PurchasePlanDraft
from app.models.audit import AuditLog
from app.models.requirements import CalculatedRequirement, MonthlyRequirementRecord
from app.models.stock_statements import (
    StockParameter,
    StockParameterBatch,
    StockStatementBatch,
    StockStatementLine,
)
from app.schemas.auth import CurrentUser
from app.schemas.purchase_approval import SubmitPurchaseApprovalRequest
from app.schemas.purchase_workspace import (
    PurchaseSubmitResponse,
    PurchaseWorkspaceRecord,
    PurchaseWorkspaceResponse,
)
from app.services.purchase_approval import submit_purchase_approval
from app.services.requirements_workspace import get_monthly_plan_metadata
from app.services.stock_management_service import resolve_stock_parameter_for_item
from app.services.monthly_purchase import MonthlyPurchaseInputs


def _filter_records(records, search, status_filter):
    if search:
        query = search.casefold()
        records = [row for row in records if any(query in (value or '').casefold() for value in
            (row.consumable_code, row.consumable_name, row.supplier_code, row.supplier_name))]
    if status_filter:
        records = [row for row in records if row.status == status_filter]
    return sorted(records, key=lambda row: (row.status != 'READY_FOR_APPROVAL', row.consumable_code))


def _with_plan_edits(session, workspace):
    if not workspace.records:
        return workspace
    material_ids = {row.consumable_id for row in workspace.records if row.consumable_id}
    masters = {identity:(name, code) for identity, name, code in session.execute(select(Consumable.id, Consumable.name, Unit.code)
        .outerjoin(Unit, Unit.id == Consumable.unit_id).where(Consumable.id.in_(material_ids)))}
    drafts = {row.consumable_id: (row, code) for row, code in session.execute(select(PurchasePlanDraft, Unit.code)
        .join(Unit, Unit.id == PurchasePlanDraft.unit_id)
        .where(PurchasePlanDraft.planning_version_id == UUID(workspace.plan_metadata.plan_id)))}
    for row in workspace.records:
        if row.consumable_id in masters:
            row.consumable_name, row.master_unit = masters[row.consumable_id]
        value = drafts.get(row.consumable_id)
        if value:
            draft, code = value
            row.requested_purchase_qty = draft.requested_qty
            row.requested_purchase_unit = code
            row.purchase_notes = draft.notes
            row.draft_version = draft.version
    return workspace


def _central_workspace(session, version, meta, *, month, year, search, status_filter, current_user, view='normal', treat_missing_as_zero: bool = True):
    """Company monthly preview alongside immutable, previously submitted evidence."""
    if current_user and not current_user.is_super_admin and current_user.plant_ids:
        raise ApplicationError('CENTRAL_REVIEW_REQUIRED', 'Central plans are reviewed by Super Admin.', 403)
    totals = session.execute(select(
        Consumable.id, Consumable.code, Consumable.name, CalculatedRequirement.unit_id,
        CalculatedRequirement.uom, func.sum(CalculatedRequirement.calculated_qty),
        func.count(CalculatedRequirement.id), func.min(CalculatedRequirement.created_at),
        func.max(CalculatedRequirement.updated_at),
    ).join(CalculatedRequirement, CalculatedRequirement.consumable_id == Consumable.id)
        .where(CalculatedRequirement.planning_version_id == version.id)
        .group_by(Consumable.id, Consumable.code, Consumable.name,
            CalculatedRequirement.unit_id, CalculatedRequirement.uom)).all()
    approved = version.status == 'APPROVED' and version.approved_at is not None
    submitted = {}
    if approved:
        # Existing assessments retain their own engine, sources and original quantities.
        for approval, report, supplier in session.execute(select(PurchaseApproval, PurchaseDemandEvidence.report, Supplier)
            .join(PurchaseDemandEvidence, PurchaseDemandEvidence.approval_id == PurchaseApproval.id)
            .join(Supplier, Supplier.id == PurchaseApproval.supplier_id)
            .where(PurchaseApproval.planning_version_id == version.id)
            .order_by(PurchaseApproval.created_at.desc(), PurchaseApproval.id.desc())):
            submitted.setdefault((approval.consumable_id, approval.uom), (approval, report, supplier))
    error_count = max(0, meta.issue_count, meta.record_count - sum(row[6] for row in totals))
    if not totals:
        notice = 'Production is uploaded, but no saved consumable requirements are available for this revision. Open Requirement, use Recalculate, then review the results.'
    elif not approved:
        notice = f'{len(totals)} consumables have saved central requirements. '
        if error_count:
            notice += f'{error_count} requirement configuration issues need review. '
        notice += 'Monthly preview uses MSL and MOQ from this month\'s Stock Management and previous month\'s closing stock. Pending POs are not deducted. Review the requirements and approve the central plan using the menu beside Recalculate in Requirement before purchase submission.'
    else:
        notice = 'Central requirements are approved. Monthly quantities are a company-formula preview. Purchase submission still requires Stock and purchase assessment in Requirement. Previously submitted assessments keep their saved quantities and calculation basis.'
    inputs = MonthlyPurchaseInputs(session, month=month, year=year, material_ids={row[0] for row in totals}, treat_missing_as_zero=treat_missing_as_zero) if totals else None
    # Only an explicit Product Master supplier selection is displayed; never pick
    # the first supplier alphabetically or treat supplier absence as zero demand.
    master_suppliers = {(mapping.consumable_id, supplier.id): supplier for mapping, supplier in session.execute(
        select(SupplierConsumable, Supplier).join(Supplier, Supplier.id == SupplierConsumable.supplier_id)
        .where(SupplierConsumable.consumable_id.in_({row[0] for row in totals}),
               SupplierConsumable.is_active == True, Supplier.is_active == True))} if totals else {}
    records = []
    import math
    for material_id, code, name, unit_id, uom, required, count, created_at, updated_at in totals:
        previous = submitted.get((material_id, uom))
        approval, report, supplier = previous if previous else (None, {}, None)
        status = 'REQUIREMENT_REVIEW_REQUIRED' if not approved else 'ASSESSMENT_REQUIRED'
        remarks = 'Requirement: review issues, then use the Recalculate menu to approve the plan.' if not approved else 'Requirement: Recalculate menu, Stock and purchase assessment. Select verified stock and supplier rules.'
        
        gross_sch = _q4(required)
        material = inputs.masters.get(material_id, (None, None))[0] if inputs else None
        tool_life = material.output_per_unit if material else None
        rule_type = material.rule_type if material and material.rule_type else ('TOOL_LIFE' if (tool_life and tool_life > 1) else 'PRODUCTION_RATE')
        
        is_tool_life = rule_type == 'TOOL_LIFE' or (tool_life is not None and tool_life > 1)
        is_output_missing = False
        if is_tool_life:
            if tool_life is None or tool_life <= Decimal('0'):
                is_output_missing = True
                effective_required = None
            else:
                effective_required = _q4(math.ceil(gross_sch / tool_life))
        elif rule_type == 'AREA_COVERAGE':
            if tool_life is None or tool_life <= Decimal('0'):
                is_output_missing = True
                effective_required = None
            else:
                effective_required = _q4(round(gross_sch / tool_life))
        else:
            effective_required = gross_sch

        if approval:
            status = 'SUBMITTED'
            remarks = f'Latest traced purchase assessment is {approval.status}. Stock and incoming quantities are the saved assessment evidence.'
            calculated = dict(calculation_basis=approval.rule_version,
                calculation_details='Saved submitted assessment; original quantities and stock sources are retained.')
        elif is_output_missing:
            status = 'OUTPUT_PER_UNIT_MISSING'
            remarks = 'Output per Unit missing'
            calculated = dict(
                calculation_basis='TOOL_LIFE',
                calculation_details='Output per Unit is missing on TOOL_LIFE consumable.',
                raw_quantity=None,
                recommended_quantity=None,
                purchase_value=None,
                stock_qty=None,
                minimum_stock_level=None,
                minimum_order_qty=None,
                category=material.category if material else None,
                type_of_material=material.type_of_material if material else None,
                output_unit=None,
            )
        else:
            calculated = inputs.calculate(material_id=material_id, unit_id=unit_id, uom=uom, required=effective_required)
            supplier = master_suppliers.get((material_id, material.supplier_id)) if material else None
            if not supplier and material and material.supplier_id:
                supplier = session.get(Supplier, material.supplier_id)
            remarks = calculated['calculation_details']
            if approved and calculated['recommended_quantity'] is None:
                status = 'MONTHLY_INPUTS_REQUIRED'
            elif approved and calculated['recommended_quantity'] == 0:
                status = 'NO_PURCHASE_REQUIRED'
        stock_qty = calculated.pop('stock_qty', None)
        raw_qty = calculated.pop('raw_quantity', None)
        monthly_qty = calculated.pop('recommended_quantity', None)
        calc_out_unit = calculated.pop('output_unit', None)

        out_display = None
        if tool_life is not None:
            out_display = str(int(tool_life) if tool_life == int(tool_life) else tool_life)
        elif calc_out_unit:
            out_display = calc_out_unit
        elif material and material.output_unit:
            out_display = material.output_unit

        supplier_name_val = supplier.name if supplier else (material.supplier_name if material else None)
        supplier_code_val = supplier.code if supplier else None

        unit_val = material.purchasing_unit if material and material.purchasing_unit else uom

        records.append(PurchaseWorkspaceRecord(
            id=f'{version.id}:{material_id}:{unit_id}', planning_period=version.planning_period,
            planning_month=month, planning_year=year, plan_id=str(version.id), revision=version.revision_label,
            consumable_id=material_id, consumable_code=code, consumable_name=name, unit=unit_val,
            required_qty=effective_required if effective_required is not None else Decimal('0'),
            gross_sch=gross_sch,
            output_unit=out_display,
            output_per_unit=tool_life,
            source_row_count=count, created_at=created_at, updated_at=updated_at,
            supplier_id=supplier.id if supplier else None, supplier_code=supplier_code_val,
            supplier_name=supplier_name_val,
            stock_qty=(_q4(report['current_stock']) if report.get('current_stock') is not None else None) if approval else stock_qty,
            po_pending_qty=_q4(report['confirmed_incoming_before_receipt']) if report.get('confirmed_incoming_before_receipt') is not None else None,
            shortage_qty=approval.raw_calculated_qty if approval else raw_qty,
            system_recommended_qty=approval.system_recommended_qty if approval else monthly_qty,
            approval_id=approval.id if approval else None, approval_status=approval.status if approval else None,
            status=status, remarks=remarks,
            **calculated,
        ))
    if view == 'md' and records:
        by_material = {}
        for requirement, item, product, process in session.execute(
            select(CalculatedRequirement, PRDOrderItem, Product, Process)
            .join(PRDOrderItem, PRDOrderItem.id == CalculatedRequirement.prd_order_item_id)
            .join(Product, Product.id == CalculatedRequirement.product_id)
            .join(Process, Process.id == CalculatedRequirement.process_id)
            .where(CalculatedRequirement.planning_version_id == version.id)
            .order_by(CalculatedRequirement.consumable_id, PRDOrderItem.source_row_number)
        ):
            params = requirement.parameters or {}
            by_material.setdefault((requirement.consumable_id, requirement.uom), []).append({
                'part_number': product.part_number or product.code,
                'part_name': product.name,
                'production_order_part': item.product_code,
                'process_name': process.name,
                'part_thickness': params.get('part_thickness'),
                'process_count': params.get('process_count'),
                'production_qty': str(requirement.source_production_qty),
                'required_qty': str(requirement.calculated_qty),
            })
        for record in records:
            record.md_sources = by_material.get((record.consumable_id, record.unit), [])
    return PurchaseWorkspaceResponse(plan_metadata=meta,
        records=_filter_records(records, search, status_filter), notice=notice)


def _q4(value: Decimal | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0.0000")
    return Decimal(str(value)).quantize(Decimal("0.0001"))


def _latest_version(session: Session, planning_period: str) -> PlanningVersion | None:
    return session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
        .limit(1)
    )


def _find_active_consumable(session: Session, code: str) -> tuple[Consumable | None, Unit | None]:
    consumable = session.scalar(
        select(Consumable).where(
            func.upper(Consumable.code) == code.strip().upper(),
            Consumable.is_active == True,  # noqa: E712
        )
    )
    unit = session.get(Unit, consumable.unit_id) if consumable else None
    return consumable, unit


def _supplier_options(session: Session, consumable_id) -> list[tuple[SupplierConsumable, Supplier]]:
    rows = session.execute(
        select(SupplierConsumable, Supplier)
        .join(Supplier, SupplierConsumable.supplier_id == Supplier.id)
        .where(
            SupplierConsumable.consumable_id == consumable_id,
            SupplierConsumable.is_active == True,  # noqa: E712
            Supplier.is_active == True,  # noqa: E712
        )
        .order_by(Supplier.code)
    ).all()
    return list(rows)


def _approval_for(
    session: Session,
    *,
    planning_version_id,
    consumable_id,
    supplier_id,
) -> PurchaseApproval | None:
    return session.scalar(
        select(PurchaseApproval)
        .where(
            PurchaseApproval.planning_version_id == planning_version_id,
            PurchaseApproval.consumable_id == consumable_id,
            PurchaseApproval.supplier_id == supplier_id,
        )
        .order_by(PurchaseApproval.created_at.desc())
        .limit(1)
    )


def list_purchase_workspace(
    session: Session,
    *,
    month: int,
    year: int,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    category: Optional[str] = None,
    current_user: CurrentUser | None = None,
    view: str = 'normal',
    treat_missing_as_zero: bool = True,
) -> PurchaseWorkspaceResponse:
    planning_period = f"{year:04d}-{month:02d}"
    meta = get_monthly_plan_metadata(session, month, year)
    version = _latest_version(session, planning_period)

    if not version:
        return PurchaseWorkspaceResponse(plan_metadata=meta, records=[])

    if meta.source_workflow == 'BASIC_CENTRAL_V1':
        return _with_plan_edits(session, _central_workspace(session, version, meta, month=month, year=year,
            search=search, status_filter=status_filter, current_user=current_user, view=view,
            treat_missing_as_zero=treat_missing_as_zero))

    rows = session.scalars(
        select(MonthlyRequirementRecord).where(
            MonthlyRequirementRecord.planning_version_id == version.id,
            MonthlyRequirementRecord.is_deleted == False,  # noqa: E712
        )
    ).all()

    # Look up previous month's stock statement and current month's stock parameters
    prev_month = 12 if month == 1 else month - 1
    prev_year = year - 1 if month == 1 else year

    prev_statement_batch = session.scalar(
        select(StockStatementBatch).where(
            StockStatementBatch.statement_month == prev_month,
            StockStatementBatch.statement_year == prev_year,
            StockStatementBatch.status == "active",
        )
    )
    stmt_lines_map: dict[str, StockStatementLine] = {}
    if prev_statement_batch:
        lines = session.scalars(
            select(StockStatementLine).where(
                StockStatementLine.batch_id == prev_statement_batch.id,
                StockStatementLine.item_class == "CONSUMABLE",
            )
        ).all()
        for l in lines:
            stmt_lines_map[l.item_id.strip().upper()] = l

    current_param_batch = session.scalar(
        select(StockParameterBatch).where(
            StockParameterBatch.month == month,
            StockParameterBatch.year == year,
            StockParameterBatch.status == "active",
        )
    )
    params_by_item: dict[str, list[StockParameter]] = {}
    if current_param_batch:
        params = session.scalars(
            select(StockParameter)
            .where(StockParameter.batch_id == current_param_batch.id)
            .order_by(StockParameter.source_row)
        ).all()
        for p in params:
            params_by_item.setdefault(p.item_id.strip().upper(), []).append(p)

    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        key = row.consumable_code.strip().upper() or row.consumable_name.strip().upper()
        bucket = grouped.setdefault(
            key,
            {
                "code": row.consumable_code.strip(),
                "name": row.consumable_name.strip(),
                "unit": row.unit,
                "required": Decimal("0"),
                "stock": Decimal("0"),
                "po_pending": Decimal("0"),
                "shortage": Decimal("0"),
                "count": 0,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            },
        )
        bucket["required"] = bucket["required"] + row.scheduled_consumable_qty  # type: ignore[operator]
        bucket["stock"] = bucket["stock"] + row.stock_qty  # type: ignore[operator]
        bucket["po_pending"] = bucket["po_pending"] + row.po_pending_qty  # type: ignore[operator]
        bucket["shortage"] = bucket["shortage"] + row.shortage_qty  # type: ignore[operator]
        bucket["count"] = int(bucket["count"]) + 1
        if row.updated_at:
            bucket["updated_at"] = row.updated_at

    records: list[PurchaseWorkspaceRecord] = []
    for key, bucket in grouped.items():
        code = str(bucket["code"])
        consumable, stock_unit = _find_active_consumable(session, code)
        suppliers = _supplier_options(session, consumable.id) if consumable else []
        supplier = suppliers[0][1] if suppliers else None
        shortage = _q4(bucket["shortage"])  # type: ignore[arg-type]
        recommended = shortage if shortage > Decimal("0") else Decimal("0.0000")
        approval = (
            _approval_for(
                session,
                planning_version_id=version.id,
                consumable_id=consumable.id,
                supplier_id=supplier.id,
            )
            if consumable and supplier
            else None
        )

        if not consumable:
            status = "MASTER_REQUIRED"
            remarks = "No active consumable master matches this requirement code."
        elif not supplier:
            status = "SUPPLIER_REQUIRED"
            remarks = "No active supplier mapping exists for this consumable."
        elif recommended <= Decimal("0"):
            status = "NO_PURCHASE_REQUIRED"
            remarks = "No positive shortage is available for approval submission."
        elif approval:
            status = "SUBMITTED"
            remarks = f"Existing approval queue item is {approval.status}."
        else:
            status = "READY_FOR_APPROVAL"
            remarks = "Ready to submit to the existing purchase approval queue."

        item_key = code.strip().upper()
        flags: list[str] = []
        if prev_statement_batch:
            if item_key in stmt_lines_map:
                stmt_line = stmt_lines_map[item_key]
                if stmt_line.closing_qty is not None:
                    effective_stock = stmt_line.closing_qty
                else:
                    effective_stock = _q4(bucket["stock"])
            else:
                effective_stock = _q4(bucket["stock"])
                flags.append(f"Not in {prev_month:02d}/{prev_year} statement")
        else:
            effective_stock = _q4(bucket["stock"])
            flags.append(f"No stock statement for {prev_month:02d}/{prev_year}")

        if not current_param_batch:
            flags.append(f"No stock parameters for {month:02d}/{year}")
        else:
            item_params = params_by_item.get(item_key, [])
            resolved_param, param_flag = resolve_stock_parameter_for_item(
                item_params,
                category=category,
            )
            if param_flag:
                flags.append(param_flag)
            elif resolved_param is not None:
                if (
                    recommended > Decimal("0")
                    and resolved_param.min_order_qty is not None
                    and recommended < resolved_param.min_order_qty
                ):
                    recommended = _q4(resolved_param.min_order_qty)
                flags.append(
                    f"Limits ({resolved_param.category or 'Default'}): "
                    f"Min={_q4(resolved_param.min_stock_level)}, "
                    f"Max={_q4(resolved_param.max_stock_level)}, "
                    f"MOQ={_q4(resolved_param.min_order_qty)}, "
                    f"Lead={resolved_param.lead_time_days if resolved_param.lead_time_days is not None else 0}d"
                )

        if flags:
            remarks = f"{remarks} [{'; '.join(flags)}]" if remarks else "; ".join(flags)

        record = PurchaseWorkspaceRecord(
            id=f"{version.id}:{key}",
            planning_period=planning_period,
            planning_month=month,
            planning_year=year,
            plan_id=str(version.id),
            revision=version.revision_label,
            consumable_id=consumable.id if consumable else None,
            consumable_code=code,
            consumable_name=str(bucket["name"]),
            supplier_id=supplier.id if supplier else None,
            supplier_code=supplier.code if supplier else None,
            supplier_name=supplier.name if supplier else None,
            unit=stock_unit.code if stock_unit else str(bucket["unit"]),
            required_qty=_q4(bucket["required"]),  # type: ignore[arg-type]
            stock_qty=_q4(effective_stock),
            po_pending_qty=_q4(bucket["po_pending"]),  # type: ignore[arg-type]
            shortage_qty=shortage,
            system_recommended_qty=recommended,
            approval_status=approval.status if approval else None,
            approval_id=approval.id if approval else None,
            status=status,
            remarks=remarks,
            source_row_count=int(bucket["count"]),
            created_at=bucket["created_at"],  # type: ignore[arg-type]
            updated_at=bucket["updated_at"],  # type: ignore[arg-type]
        )
        records.append(record)

    records = _filter_records(records, search, status_filter)
    if view == 'md':
        by_code = {}
        for source in rows:
            by_code.setdefault(source.consumable_code.strip().upper(), []).append({
                'part_number': source.part_number, 'part_name': source.part_name,
                'production_order_part': source.part_number, 'process_name': source.process_name,
                'part_thickness': str(source.part_thickness), 'process_count': source.process_count,
                'production_qty': str(source.production_order_qty),
                'required_qty': str(source.scheduled_consumable_qty),
            })
        for record in records:
            record.md_sources = by_code.get(record.consumable_code.strip().upper(), [])
    return _with_plan_edits(session, PurchaseWorkspaceResponse(plan_metadata=meta, records=records))


def save_purchase_plan(session, *, month, year, request, current_user):
    from app.schemas.inventory_masters import ConsumableUpdate
    from app.services import inventory_masters
    elevated = current_user.is_super_admin or 'ADMIN' in current_user.roles
    if not (elevated or current_user.purchase_update or current_user.purchase_orders_update):
        raise ApplicationError('PERMISSION_DENIED', 'Purchase update permission is required to edit this plan.', 403)
    try:
        workspace = list_purchase_workspace(session, month=month, year=year, current_user=current_user)
        if not workspace.plan_metadata.plan_id:
            raise ApplicationError('PLAN_NOT_FOUND', 'Load an existing purchase plan before saving.', 404)
        version = session.scalar(select(PlanningVersion).where(PlanningVersion.id == UUID(workspace.plan_metadata.plan_id)).with_for_update())
        if version.id != _latest_version(session, version.planning_period).id:
            raise ApplicationError('LATEST_REVISION_REQUIRED', 'Reload the latest purchase planning revision.', 409)
        available = {row.id:row for row in workspace.records}
        seen = set()
        for edit in sorted(request.edits, key=lambda item: item.record_id):
            row = available.get(edit.record_id)
            if not row or not row.consumable_id or row.consumable_id in seen:
                raise ApplicationError('INVALID_PLAN_ROW', 'Select one valid row per consumable in the selected period.', 409)
            seen.add(row.consumable_id)
            draft = session.scalar(select(PurchasePlanDraft).where(PurchasePlanDraft.planning_version_id == version.id,
                PurchasePlanDraft.consumable_id == row.consumable_id).with_for_update())
            if (draft.version if draft else 0) != edit.expected_draft_version:
                raise ApplicationError('STALE_PURCHASE_EDIT', 'This row changed since it was loaded. Reload before editing again.', 409)
            material = session.scalar(select(Consumable).where(Consumable.id == row.consumable_id).with_for_update())
            unit = session.get(Unit, material.unit_id) if material.unit_id else None
            if material.name != edit.expected_name or (unit.code if unit else '') != edit.expected_master_unit:
                raise ApplicationError('STALE_PURCHASE_EDIT', 'The master details changed. Reload before saving.', 409)
            master_changes = {}
            if 'consumable_name' in edit.model_fields_set:
                if not edit.consumable_name or not edit.consumable_name.strip():
                    raise ApplicationError('INVALID_MASTER_NAME', 'Consumable name cannot be blank.', 422)
                master_changes['name'] = edit.consumable_name.strip()
                master_changes['description'] = master_changes['name']
            if 'master_unit' in edit.model_fields_set:
                chosen = session.scalar(select(Unit).where(func.upper(Unit.code) == (edit.master_unit or '').strip().upper(), Unit.is_active.is_(True)))
                if chosen is None:
                    raise ApplicationError('INVALID_UNIT', 'Choose an existing active stock unit, such as PCS or KG.', 422)
                master_changes['unit_id'] = chosen.id
            if master_changes:
                if not (elevated or current_user.masters_update or 'masters.consumables.write' in current_user.permissions):
                    raise ApplicationError('PERMISSION_DENIED', 'Master update permission is required to change consumable names or units.', 403)
                resource = next(item for item in inventory_masters.RESOURCES if item.model is Consumable)
                inventory_masters.apply_record_update(session, resource, material.id,
                    ConsumableUpdate(**master_changes, change_reason=request.reason), current_user.id)
            if {'requested_purchase_qty', 'purchase_notes'} & edit.model_fields_set:
                if session.scalar(select(PurchaseApproval.id).where(PurchaseApproval.planning_version_id == version.id,
                        PurchaseApproval.consumable_id == material.id).limit(1)):
                    raise ApplicationError('PURCHASE_REVIEW_PROTECTED', 'This material is already in the approval queue. Review its quantity there to preserve approval history.', 409)
                source_unit = session.scalar(select(Unit).where(Unit.code == row.unit))
                if not source_unit:
                    raise ApplicationError('INVALID_UNIT', 'Review this requirement stock unit before entering a purchase quantity.', 409)
                before = {'requested_qty': str(draft.requested_qty) if draft and draft.requested_qty is not None else None,
                    'notes': draft.notes if draft else None, 'version': draft.version if draft else 0}
                if not draft:
                    draft = PurchasePlanDraft(planning_version_id=version.id, consumable_id=material.id,
                        unit_id=source_unit.id, updated_by=current_user.id, version=0)
                    session.add(draft)
                if 'requested_purchase_qty' in edit.model_fields_set:
                    draft.requested_qty = edit.requested_purchase_qty
                    draft.unit_id = source_unit.id
                if 'purchase_notes' in edit.model_fields_set:
                    draft.notes = edit.purchase_notes.strip() if edit.purchase_notes else None
                draft.version += 1
                draft.updated_by = current_user.id
                session.flush()
                session.add(AuditLog(actor_id=current_user.id, action='EDIT_PURCHASE_PLAN', entity_type='purchase_plan_draft',
                    entity_id=draft.id, old_values=before, new_values={'requested_qty':str(draft.requested_qty) if draft.requested_qty is not None else None,
                    'notes':draft.notes, 'version':draft.version, 'unit_id':str(draft.unit_id)}, reason=request.reason))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return list_purchase_workspace(session, month=month, year=year, current_user=current_user)


def submit_purchase_workspace_records(
    session: Session,
    *,
    month: int,
    year: int,
    record_ids: list[str],
    reason: Optional[str],
    current_user: CurrentUser,
) -> PurchaseSubmitResponse:
    if not record_ids:
        raise ApplicationError("EMPTY_SUBMISSION", "Select at least one purchase recommendation.", 400)

    workspace = list_purchase_workspace(session, month=month, year=year, current_user=current_user)
    if workspace.plan_metadata.source_workflow == 'BASIC_CENTRAL_V1':
        raise ApplicationError('CENTRAL_PURCHASE_ASSESSMENT_REQUIRED',
            'Submit purchase demand through Stock and purchase assessment in Requirement after plan approval and stock/supplier review.', 409)
    selected = [row for row in workspace.records if row.id in set(record_ids)]
    if not selected:
        raise ApplicationError("NO_MATCHING_RECORDS", "No selected purchase records were found.", 404)

    submitted = 0
    skipped = 0
    for row in selected:
        if (
            row.status != "READY_FOR_APPROVAL"
            or not row.consumable_id
            or not row.supplier_id
            or row.system_recommended_qty is None
            or row.system_recommended_qty <= Decimal("0")
        ):
            skipped += 1
            continue

        submit_purchase_approval(
            session,
            SubmitPurchaseApprovalRequest(
                consumable_id=row.consumable_id,
                supplier_id=row.supplier_id,
                planning_version_id=UUID(row.plan_id) if row.plan_id else None,
                raw_calculated_qty=row.shortage_qty,
                system_recommended_qty=row.system_recommended_qty,
                uom=row.unit,
                reason=reason or "Submitted from monthly Purchase workspace.",
            ),
            current_user,
        )
        submitted += 1

    refreshed = list_purchase_workspace(session, month=month, year=year)
    return PurchaseSubmitResponse(
        message=f"Submitted {submitted} purchase recommendation(s) to approval queue.",
        submitted_count=submitted,
        skipped_count=skipped,
        records=refreshed.records,
        plan_metadata=refreshed.plan_metadata,
    )


def export_purchase_workspace_excel(
    session: Session,
    *,
    month: int,
    year: int,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    record_ids: Optional[list[str]] = None,
    current_user: CurrentUser | None = None,
    view: Optional[str] = None,
    treat_missing_as_zero: bool = True,
) -> bytes:
    workspace = list_purchase_workspace(
        session,
        month=month,
        year=year,
        search=search,
        status_filter=status_filter,
        current_user=current_user,
        view=view or 'normal',
        treat_missing_as_zero=treat_missing_as_zero,
    )
    records = workspace.records
    if record_ids:
        ids = set(record_ids)
        records = [r for r in records if r.id in ids]

    if view in ('normal', 'md'):
        return _export_purchase_view(records, month=month, year=year, view=view)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Purchase Recommendations"

    navy_fill = PatternFill(start_color="1B3A5C", end_color="1B3A5C", fill_type="solid")
    steel_fill = PatternFill(start_color="2E5B88", end_color="2E5B88", fill_type="solid")
    title_font = Font(name="Calibri", size=14, bold=True, color="1B3A5C")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    period_label = f"{calendar.month_name[month]} {year}"
    ws.cell(row=1, column=1, value="KNL PURCHASE RECOMMENDATIONS").font = title_font
    ws.cell(
        row=2,
        column=1,
        value=f"Planning Period: {period_label} | Revision: {workspace.plan_metadata.revision_label} | Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
    )
    if workspace.notice:
        ws.cell(row=3, column=1, value=workspace.notice)

    central = workspace.plan_metadata.source_workflow == 'BASIC_CENTRAL_V1'
    headers = [
        "Consumable Code",
        "Consumable Name",
        "Supplier Code",
        "Supplier Name",
        "Unit",
        "Required Qty",
        "Stock Qty (see calculation basis)" if central else "Stock Qty",
        "Incoming (assessment only)" if central else "PO Pending Qty",
        "Raw Purchase Need" if central else "Shortage Qty",
        "System Recommended Qty",
        "Status",
        "Approval Status",
        "Source Rows",
        "Remarks",
        "Stock Unit (Master)",
        "Requested Purchase Qty",
        "Requested Purchase Unit",
        "Purchase Remarks",
        "MSL",
        "MOQ",
        "Unit Rate (Product Master)",
        "Purchase Value",
        "Stock Period",
        "Calculation Basis",
        "Calculation Details",
        "Missing Inputs",
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col, value=header)
        cell.fill = navy_fill if col <= 5 else steel_fill
        cell.font = header_font
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row_idx, record in enumerate(records, start=5):
        values = [
            record.consumable_code,
            record.consumable_name,
            record.supplier_code or "Not selected",
            record.supplier_name or "Not selected",
            record.unit,
            record.required_qty,
            record.stock_qty if record.stock_qty is not None else "Unavailable",
            ("Not used by monthly formula" if record.calculation_basis == 'KNL_MONTHLY_V1' else
             record.po_pending_qty if record.po_pending_qty is not None else "Unavailable"),
            record.shortage_qty if record.shortage_qty is not None else "Unavailable",
            record.system_recommended_qty if record.system_recommended_qty is not None else "Unavailable",
            record.status,
            record.approval_status or "Not submitted",
            record.source_row_count,
            record.remarks or "",
            record.master_unit or "Not specified",
            record.requested_purchase_qty if record.requested_purchase_qty is not None else "Not entered",
            record.requested_purchase_unit or record.unit,
            record.purchase_notes or "",
            record.minimum_stock_level if record.minimum_stock_level is not None else "Unavailable",
            record.minimum_order_qty if record.minimum_order_qty is not None else "Unavailable",
            record.unit_rate if record.unit_rate is not None else "Unavailable",
            record.purchase_value if record.purchase_value is not None else "Unavailable",
            record.stock_period or "See saved assessment",
            record.calculation_basis or "LEGACY_MONTHLY",
            record.calculation_details or record.remarks or "",
            '; '.join(record.input_issues),
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col, value=value)
            if isinstance(value, str):
                cell.data_type = 's'
            cell.font = data_font
            cell.border = thin_border
            if col in (6, 7, 8, 9, 10, 16, 19, 20, 21, 22):
                cell.number_format = "#,##0.00000000" if col == 22 else "#,##0.0000"
                cell.alignment = Alignment(horizontal="right")
                if value == 'Unavailable':
                    reason = (('; '.join(record.input_issues) or 'No Product Master rate is available for the purchase value.')
                        if record.calculation_basis == 'KNL_MONTHLY_V1' else
                        'Requirement approval is pending. Stock and supplier assessment has not been completed.'
                        if record.status == 'REQUIREMENT_REVIEW_REQUIRED' else
                        'No saved stock and supplier assessment supplies this value.' if central else
                        'No calculated value is available for this field.')
                    cell.comment = Comment(reason, 'KNL ERP')
                    cell.font = Font(name='Calibri', size=10, color='9A6700')
            if col == 16 and value == 'Not entered':
                cell.comment = Comment('No requested purchase quantity has been entered. This is a separate proposal, not the system recommendation.', 'KNL ERP')

    # Size from actual headers/data; the long notice must not widen the item-code column.
    for col_idx in range(1, len(headers) + 1):
        width = max(len(str(ws.cell(row_idx, col_idx).value or '')) for row_idx in range(4, ws.max_row + 1))
        ws.column_dimensions[get_column_letter(col_idx)].width = max(12, min(width + 3, 48))
    ws.row_dimensions[4].height = 30
    if workspace.notice:
        ws.merge_cells('A3:J3')
        ws['A3'].alignment = Alignment(wrap_text=True, vertical='center')
        ws.row_dimensions[3].height = 45
    ws.freeze_panes = 'C5'
    ws.auto_filter.ref = f'A4:{get_column_letter(len(headers))}{ws.max_row}'

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _export_purchase_view(records, *, month: int, year: int, view: str) -> bytes:
    """Export the selected customer layout using saved sources only; blanks are not zeroes."""
    prev_month, prev_year = (12, year - 1) if month == 1 else (month - 1, year)
    prev_label = f"{calendar.month_abbr[prev_month]}-{str(prev_year)[-2:]}"
    month_label = f"{calendar.month_abbr[month]}-{str(year)[-2:]}"
    normal = [
        ('S. No.', '#'), ('Req. Type', 'category'), ('Item Id', 'consumable_code'),
        ('Description', 'consumable_name'), ('Unit', 'unit'), ('Output / Unit', 'output_unit'),
        ('MOQ.', 'minimum_order_qty'), ('Min. Stock. Level', 'minimum_stock_level'),
        ('Max. Stock Level', 'max_stock_level'), ('Rate', 'unit_rate'),
        (f'O/s. {prev_label}', 'opening_qty'), (f'Receipt {prev_label}', 'receipt_qty'),
        (f'Issues {prev_label}', 'issue_qty'), (f'C/s. {prev_label}', 'stock_qty'),
        (f'Prd. Qty. {prev_label}', None), (f'Sch. {month_label}', 'gross_sch'),
        (f'Req. Qty. {month_label}', 'required_qty'), ('Order Qty.', 'system_recommended_qty'),
        ('Order Value', 'purchase_value'), ('Pur. Qty.', None), ('Pur. Value', None),
        ('Bal. Pur. Qty', None), ('Bal. Pur. Value', None),
    ]
    md = [
        ('Supplier ID', 'supplier_code'), ('Supplier name', 'supplier_name'),
        ('Item Id', 'consumable_code'), ('Category', 'category'),
        ('Type of material', 'type_of_material'), ('S. No.', '#'),
        ('Description', 'consumable_name'), ('Part No. of saleable item', '@part_number'),
        ('Used for- Name of Saleable part', '@part_name'),
        ('Used Part no (prd order)', '@production_order_part'),
        ('Process name', '@process_name'), ('Material thickness in mm / Gsm', '@part_thickness'),
        ('No of process per part', '@process_count'), ('Output/ Unit', 'output_unit'),
        ('Rate', 'unit_rate'), (f"Opening Qty {calendar.month_abbr[prev_month]}'{str(prev_year)[-2:]}", 'opening_qty'),
        (f"Opening Value {calendar.month_abbr[prev_month]}'{str(prev_year)[-2:]}", 'opening_value'),
        (f"Receipt. Qty. {calendar.month_abbr[prev_month]}'{str(prev_year)[-2:]}", 'receipt_qty'),
        (f"Issue Qty. {calendar.month_abbr[prev_month]}'{str(prev_year)[-2:]}", 'issue_qty'),
        (f"Closing Qty {calendar.month_abbr[prev_month]}'{str(prev_year)[-2:]}", 'stock_qty'),
        (f"Closing Value {calendar.month_abbr[prev_month]}'{str(prev_year)[-2:]}", 'closing_value'),
        ('Rate', 'unit_rate'), ('Min stock level', 'minimum_stock_level'),
        ('Max stock level', 'max_stock_level'), ('Minimum order qty.', 'minimum_order_qty'),
        ('Lead time to supply in days', 'lead_time_days'),
        ('Sch. Qty. as per assy R1', '@production_qty'), ('Purchasing Unit', 'unit'),
        ('Sch. Qty. Cons. Itemwise R1', '@required_qty'),
        (f"Opening stock {calendar.month_abbr[month]}'{str(year)[-2:]}", 'stock_qty'),
        ('Req. Qty.', 'required_qty'), ('Order Qty R1', 'system_recommended_qty'),
        ('Order Value R1', 'purchase_value'),
    ]
    trailing = [
        'Receipt qty. R1', 'Receipt value R1', 'Sch. Qty. as per assy R2',
        'Sch. Qty. Cons. Itemwise R2', 'Req. R2', 'closing stock',
        'Req.qty lessed by issue qty', 'Issue Qty. till', 'Order Qty. R2',
        'Order Value R2', 'Receipt qty. R2', 'Receipt value R2',
        'Total Receipt Qty.', 'Total receipt value', 'P1', 'P2', 'P3', 'P4', 'P5',
        'tool room', 'Quality', 'PMD', 'NPD', 'HRD', 'Accounts',
        'Purchase ,Stores&admin', 'Sales', 'Req. given by users', 'Total Value.',
        'Avg.Monthly Consumption', 'Avg.Daily Consumption', 'Minimum order Quantity.',
        'Lead time to supply in days', 'Mini number of days to hold in production',
        'Min stock level', 'Max stock level', 'Lead time qty', 'Re-Order Level',
        'Cost of MSL', 'REORDER LEVEL(MSL+(Avg.reqd.con per dayxLead timr to supply in days))',
        'Avg. consumption per day', 'Previous month Plan value', 'Previous month Actual value',
    ]
    for position, label in enumerate(trailing, 34):
        md.append((label, {65: 'minimum_order_qty', 66: 'lead_time_days',
                           68: 'minimum_stock_level', 69: 'max_stock_level'}.get(position)))
    columns = md if view == 'md' else normal
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'MD View' if view == 'md' else 'Normal View'
    ws.append([f'KNL PURCHASE PLAN — {view.upper()} VIEW — {calendar.month_name[month]} {year}'])
    ws.append(['Blank cells indicate that no verified value is available; R1/R2 and purchase actuals are not inferred.'])
    ws.append([label for label, _ in columns])
    for index, record in enumerate(records, 1):
        sources = record.md_sources if view == 'md' and record.md_sources else [None]
        for source in sources:
            values = []
            for _label, key in columns:
                if key == '#':
                    value = index
                elif key and key.startswith('@'):
                    value = source.get(key[1:]) if source else None
                elif key in ('output_unit', 'output_per_unit'):
                    raw_val = getattr(record, 'output_per_unit', None)
                    if raw_val is None:
                        raw_val = getattr(record, 'output_unit', None)
                    if raw_val is not None:
                        try:
                            s = str(raw_val).strip()
                            if s:
                                f = float(s)
                                value = int(f) if f.is_integer() else f
                            else:
                                value = None
                        except (ValueError, TypeError):
                            value = raw_val
                    else:
                        value = None
                else:
                    value = getattr(record, key, None) if key else None
                values.append(value)
            ws.append(values)
    for cell in ws[3]:
        cell.fill = PatternFill(start_color='1B3A5C', end_color='1B3A5C', fill_type='solid')
        cell.font = Font(color='FFFFFF', bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical='center')
    ws.row_dimensions[3].height = 42
    for number, (label, _) in enumerate(columns, 1):
        ws.column_dimensions[get_column_letter(number)].width = min(40, max(15, len(label) + 2))
    ws.freeze_panes = 'D4' if view == 'md' else 'E4'
    ws.auto_filter.ref = f'A3:{get_column_letter(len(columns))}{max(ws.max_row, 3)}'
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()
