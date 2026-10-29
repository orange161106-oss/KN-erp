import calendar
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import io
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import aliased, joinedload

from app.core.errors import ApplicationError
from app.domain.rules import (
    RoundingPolicy,
    RuleCalculationInput,
    RuleDomainError,
    RuleType,
    evaluate_rule,
)
from app.models.audit import AuditLog
from app.models.auth import User
from app.models.inventory_masters import Consumable, Unit
from app.models.masters import Product
from app.models.prd import ImportBatch, PlanningVersion
from app.models.production import Plant, Process
from app.models.requirements import (
    CalculatedRequirement,
    MonthlyRequirementRecord,
    RequirementCalculationError,
)
from app.models.stock_statements import StockStatementBatch, StockStatementLine
from app.models.rules import ConsumptionNorm
from app.schemas.requirements_workspace import (
    DepartmentalRowCreateRequest,
    MonthlyPlanMetadata,
    RequirementBatchUpdateRequest,
    RequirementBatchUpdateResponse,
    RequirementDeleteBatchRequest,
    RequirementExcelInspectResponse,
    RequirementImportRequest,
    RequirementRecalculateResponse,
    RequirementRowError,
    RequirementWorkspaceRecord,
)


def get_t_minus_2_period(month: int, year: int) -> tuple[int, int]:
    """Calculate T-2 planning period (month, year) for physical inventory baseline.

    e.g. Oct 2026 (10, 2026) -> Aug 2026 (8, 2026)
    Feb 2026 (2, 2026) -> Dec 2025 (12, 2025)
    Jan 2026 (1, 2026) -> Nov 2025 (11, 2025)
    """
    if month == 1:
        return 11, year - 1
    elif month == 2:
        return 12, year - 1
    else:
        return month - 2, year

CORE_DEPARTMENTS = [
    "TOOL_ROOM",
    "PMD",
    "NPD",
    "HRD",
    "QAD",
]
SUPPORT_DEPARTMENTS = [
    "ACCOUNTS",
    "SALES",
]
ALL_DEPARTMENTS = CORE_DEPARTMENTS + SUPPORT_DEPARTMENTS

DEPARTMENT_DISPLAY_NAMES = {
    "TOOL_ROOM": "Tool Room",
    "PMD": "PMD",
    "NPD": "NPD",
    "HRD": "HRD",
    "QAD": "QAD",
    "ACCOUNTS": "Accounts",
    "SALES": "Sales",
    "DEPARTMENTAL": "Departmental",
}

DEPARTMENT_TAB_ALIASES: dict[str, list[str]] = {
    "TOOL_ROOM": ["tool room", "toolroom", "tool_room", "dept tool room", "dept: tool room"],
    "PMD": ["pmd", "plant maintenance", "maintenance", "pmd & tool maintenance", "pmd tool maintenance"],
    "NPD": ["npd", "new product development"],
    "HRD": ["hrd", "hr & admin", "hr admin", "safety", "hr"],
    "QAD": ["qad", "quality", "qa", "quality assurance"],
    "ACCOUNTS": ["accounts", "account", "finance"],
    "SALES": ["sales", "purchase ,stores&admin", "stores&admin", "stores admin", "stores and admin", "purchase stores admin"],
    "DEPARTMENTAL": [
        "departmental",
        "departmental consumables",
        "department indents",
        "departmental indents",
        "departments",
    ],
}


def _normalize_header(hdr: Any) -> str:
    if hdr is None:
        return ""
    text = str(hdr).strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _normalize_plant_identifier(val: Optional[str]) -> str:
    if not val:
        return ""
    cleaned = str(val).strip().upper().replace(" ", "_").replace("-", "_")
    roman_map = {
        "PLANT_I": "PLANT_1",
        "PLANT_II": "PLANT_2",
        "PLANT_III": "PLANT_3",
        "PLANT_IV": "PLANT_4",
        "PLANT_V": "PLANT_5",
        "PLANT_1": "PLANT_1",
        "PLANT_2": "PLANT_2",
        "PLANT_3": "PLANT_3",
        "PLANT_4": "PLANT_4",
        "PLANT_5": "PLANT_5",
        "P1": "PLANT_1",
        "P2": "PLANT_2",
        "P3": "PLANT_3",
        "P4": "PLANT_4",
        "P5": "PLANT_5",
        "TOOL_ROOM": "TOOL_ROOM",
        "TOOLROOM": "TOOL_ROOM",
        "DEPT:_TOOL_ROOM": "TOOL_ROOM",
        "DEPT_TOOL_ROOM": "TOOL_ROOM",
        "PMD": "PMD",
        "PMD_&_TOOL_MAINTENANCE": "PMD",
        "PMD_TOOL_MAINTENANCE": "PMD",
        "MAINTENANCE": "PMD",
        "NPD": "NPD",
        "HRD": "HRD",
        "HR_&_ADMIN": "HRD",
        "QAD": "QAD",
        "QUALITY": "QAD",
        "QA": "QAD",
        "ACCOUNTS": "ACCOUNTS",
        "SALES": "SALES",
        "DEPARTMENTAL": "DEPARTMENTAL",
        "DEPARTMENTAL_CONSUMABLES": "DEPARTMENTAL",
    }
    return roman_map.get(cleaned, cleaned)


def _match_department_tab(title: Optional[str]) -> Optional[str]:
    """Matches sheet title against known departmental aliases."""
    if not title:
        return None
    raw = _normalize_header(title)
    for dept_key, aliases in DEPARTMENT_TAB_ALIASES.items():
        if any(alias == raw or alias in raw for alias in aliases):
            return dept_key
    return None


def is_department_unit(val: Optional[str]) -> bool:
    """Checks whether a string represents a maintenance or support department."""
    if not val:
        return False
    norm = _normalize_plant_identifier(val)
    if norm in ALL_DEPARTMENTS:
        return True
    matched = _match_department_tab(val)
    return matched is not None


def ensure_operational_units(session) -> None:
    """Idempotently seeds department cost centers into the plants table."""
    try:
        existing_plants = {
            name.strip().upper()
            for name in session.scalars(select(Plant.name)).all()
            if name
        }
        to_create = []
        for dept_key, display_name in DEPARTMENT_DISPLAY_NAMES.items():
            if display_name.upper() not in existing_plants and dept_key not in existing_plants:
                to_create.append(
                    Plant(
                        id=uuid4(),
                        name=display_name,
                        location="Department",
                        is_active=True,
                    )
                )
        if to_create:
            session.add_all(to_create)
            session.flush()
    except Exception:
        # Ignore if tables not yet populated or session in read-only transaction
        pass


def get_monthly_plan_metadata(
    session, month: int, year: int
) -> MonthlyPlanMetadata:
    planning_period = f"{year:04d}-{month:02d}"
    creator, updater = aliased(User), aliased(User)
    batch_metadata = select(ImportBatch.validation_summary).where(
        ImportBatch.planning_version_id == PlanningVersion.id).limit(1).scalar_subquery()
    row = session.execute(
        select(PlanningVersion, batch_metadata, creator.full_name, creator.username,
            updater.full_name, updater.username)
        .outerjoin(creator, creator.id == PlanningVersion.created_by)
        .outerjoin(updater, updater.id == PlanningVersion.updated_by)
        .where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
        .limit(1)
    ).first()

    if not row:
        rec_stats = session.execute(
            select(
                func.count(MonthlyRequirementRecord.id),
                func.count(MonthlyRequirementRecord.id).filter(
                    or_(
                        MonthlyRequirementRecord.grn_received_qty > 0,
                        MonthlyRequirementRecord.last_synced_at.is_not(None),
                        MonthlyRequirementRecord.grn_source_file.is_not(None),
                    )
                ),
                func.max(MonthlyRequirementRecord.last_synced_at),
            ).where(
                MonthlyRequirementRecord.planning_period == planning_period,
                MonthlyRequirementRecord.is_deleted == False,  # noqa: E712
            )
        ).one()
        rec_count = rec_stats[0] or 0
        reconciled_count = rec_stats[1] or 0
        last_synced = rec_stats[2]
        return MonthlyPlanMetadata(
            has_plan=rec_count > 0,
            planning_month=month,
            planning_year=year,
            planning_period=planning_period,
            record_count=rec_count,
            issue_count=0,
            source_workflow=None,
            grn_reconciled=bool(reconciled_count > 0),
            last_grn_synced_at=last_synced,
        )

    version, metadata, creator_name, creator_username, updater_name, updater_username = row
    from app.services import basic_planning
    central = (metadata or {}).get('workflow') == basic_planning.WORKFLOW
    # A production-based monthly view reads the same saved rows as Central.
    issues_cnt = 0
    reconciled_count = 0
    last_synced = None

    grn_cnt_sq = select(func.count(MonthlyRequirementRecord.id)).where(
        MonthlyRequirementRecord.planning_period == planning_period,
        MonthlyRequirementRecord.is_deleted == False,
        or_(
            MonthlyRequirementRecord.grn_received_qty > 0,
            MonthlyRequirementRecord.last_synced_at.is_not(None),
            MonthlyRequirementRecord.grn_source_file.is_not(None),
        ),
    ).scalar_subquery()

    grn_max_sq = select(func.max(MonthlyRequirementRecord.last_synced_at)).where(
        MonthlyRequirementRecord.planning_period == planning_period,
        MonthlyRequirementRecord.is_deleted == False,
        or_(
            MonthlyRequirementRecord.grn_received_qty > 0,
            MonthlyRequirementRecord.last_synced_at.is_not(None),
            MonthlyRequirementRecord.grn_source_file.is_not(None),
        ),
    ).scalar_subquery()

    if central:
        counts = [select(func.count(model.id)).where(model.planning_version_id == version.id).scalar_subquery()
            for model in (CalculatedRequirement, RequirementCalculationError)]
        extra_grn_sq = select(func.count(MonthlyRequirementRecord.id)).where(
            MonthlyRequirementRecord.planning_period == planning_period,
            MonthlyRequirementRecord.is_deleted == False,
            or_(
                MonthlyRequirementRecord.grn_source_file.is_not(None),
                MonthlyRequirementRecord.process_name == "Store Receipt",
            ),
        ).scalar_subquery()

        calc_cnt, issues_cnt, extra_grn_cnt, reconciled_count, last_synced = session.execute(
            select(counts[0], counts[1], extra_grn_sq, grn_cnt_sq, grn_max_sq)
        ).one()
        rec_count = (calc_cnt or 0) + (issues_cnt or 0) + (extra_grn_cnt or 0)
    else:
        mrr_cnt_sq = select(func.count(MonthlyRequirementRecord.id)).where(
            MonthlyRequirementRecord.planning_version_id == version.id,
            MonthlyRequirementRecord.is_deleted == False,
        ).scalar_subquery()

        rec_count, reconciled_count, last_synced = session.execute(
            select(mrr_cnt_sq, grn_cnt_sq, grn_max_sq)
        ).one()
        rec_count = rec_count or 0

    reconciled_count = reconciled_count or 0

    return MonthlyPlanMetadata(
        has_plan=True,
        plan_id=str(version.id),
        planning_month=month,
        planning_year=year,
        planning_period=planning_period,
        status=version.status,
        revision_label=version.revision_label,
        source_filename=version.source_filename,
        created_at=version.created_at,
        created_by=str(version.created_by) if version.created_by else None,
        created_by_name=creator_name or creator_username,
        updated_at=version.updated_at,
        updated_by=str(version.updated_by) if version.updated_by else None,
        updated_by_name=updater_name or updater_username,
        record_count=rec_count,
        issue_count=issues_cnt,
        source_workflow=basic_planning.WORKFLOW if central else None,
        grn_reconciled=bool(reconciled_count > 0),
        last_grn_synced_at=last_synced,
    )


def calculate_workspace_requirements(
    session,
    month: Optional[int] = None,
    year: Optional[int] = None,
    planning_period: Optional[str] = None,
    plant_filter: Optional[str] = None,
    consumable_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> list[RequirementWorkspaceRecord]:
    """Retrieve requirements for the given planning month and year.

    Production-based periods share Central's saved calculated_requirements.
    Other periods retain the manual spreadsheet plan and its existing fallback.
    """
    target_period = planning_period
    if month and year:
        target_period = f"{year:04d}-{month:02d}"

    t_month, t_year = month, year
    if not (t_month and t_year) and target_period and "-" in target_period:
        try:
            parts = target_period.split("-")
            t_year, t_month = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass

    t2_month, t2_year = get_t_minus_2_period(t_month, t_year) if (t_month and t_year) else (None, None)

    dept_names_upper = [d.upper() for d in ALL_DEPARTMENTS] + [v.upper() for v in DEPARTMENT_DISPLAY_NAMES.values()]
    target_seq = (t_year * 12 + t_month) if (t_month and t_year) else None

    # 1. Query dedicated monthly planning records
    query = select(MonthlyRequirementRecord).options(joinedload(MonthlyRequirementRecord.planning_version)).where(MonthlyRequirementRecord.is_deleted == False)  # noqa: E712
    if target_period:
        if target_seq:
            query = query.where(
                or_(
                    MonthlyRequirementRecord.planning_period == target_period,
                    and_(
                        func.upper(MonthlyRequirementRecord.plant).in_(dept_names_upper),
                        (MonthlyRequirementRecord.planning_year * 12 + MonthlyRequirementRecord.planning_month) <= target_seq,
                    ),
                )
            )
        else:
            query = query.where(MonthlyRequirementRecord.planning_period == target_period)

    from app.services import basic_planning
    batch_metadata = select(ImportBatch.validation_summary).where(
        ImportBatch.planning_version_id == PlanningVersion.id).limit(1).scalar_subquery()
    mrr_count_subquery = select(func.count(MonthlyRequirementRecord.id)).where(
        MonthlyRequirementRecord.is_deleted == False,
        or_(
            MonthlyRequirementRecord.planning_period == target_period,
            func.upper(MonthlyRequirementRecord.plant).in_(dept_names_upper),
        ) if target_period else MonthlyRequirementRecord.is_deleted == False,
    ).limit(1).scalar_subquery() if target_period else None

    t2_batch_id_subquery = select(StockStatementBatch.id).where(
        StockStatementBatch.statement_month == t2_month,
        StockStatementBatch.statement_year == t2_year,
        StockStatementBatch.status == "active",
    ).limit(1).scalar_subquery() if (t2_month and t2_year) else None

    period_row = session.execute(
        select(PlanningVersion, batch_metadata, mrr_count_subquery, t2_batch_id_subquery)
        .where(PlanningVersion.planning_period == target_period)
        .order_by(PlanningVersion.version_number.desc()).limit(1)
    ).first() if target_period else None
    period_version = period_row[0] if period_row else None
    central = bool(period_row and (period_row[1] or {}).get('workflow') == basic_planning.WORKFLOW)
    has_mrr = bool(period_row and (period_row[2] or 0) > 0)
    t2_batch_id = period_row[3] if period_row else None

    if not t2_batch_id and not period_row and t2_month and t2_year:
        t2_batch_id = session.scalar(
            select(StockStatementBatch.id).where(
                StockStatementBatch.statement_month == t2_month,
                StockStatementBatch.statement_year == t2_year,
                StockStatementBatch.status == "active",
            ).limit(1)
        )

    t2_stock_by_code: dict[str, Decimal] = {}
    if t2_batch_id:
        t2_lines = session.execute(
            select(StockStatementLine.item_id, StockStatementLine.closing_qty).where(
                StockStatementLine.batch_id == t2_batch_id,
                StockStatementLine.item_class == "CONSUMABLE",
            )
        ).all()
        for item_id, closing_qty in t2_lines:
            if item_id:
                t2_stock_by_code[item_id.strip().upper()] = closing_qty or Decimal("0.0")

    history_dept_mrrs: dict[tuple[str, str], list[MonthlyRequirementRecord]] = {}
    monthly_rows_all = [] if central else session.scalars(query.order_by(MonthlyRequirementRecord.row_index, MonthlyRequirementRecord.created_at)).all()
    monthly_rows = [r for r in monthly_rows_all if r.planning_period == target_period]
    for r in monthly_rows_all:
        if is_department_unit(r.plant) or is_department_unit(r.plant_id):
            k = (_normalize_plant_identifier(r.plant), (r.consumable_code or "").strip().upper())
            history_dept_mrrs.setdefault(k, []).append(r)

    results: list[RequirementWorkspaceRecord] = []

    if monthly_rows:
        for r in monthly_rows:
            code_upper = r.consumable_code.strip().upper() if r.consumable_code else ""
            if code_upper in t2_stock_by_code:
                op_stock = t2_stock_by_code[code_upper]
            else:
                op_stock = getattr(r, "opening_stock", Decimal("0.0")) or Decimal("0.0")

            grn_rec = getattr(r, "grn_received_qty", Decimal("0.0")) or Decimal("0.0")
            consumed = getattr(r, "consumed_qty", Decimal("0.0")) or Decimal("0.0")
            cls_stk = (op_stock + grn_rec) - consumed
            gross_req = getattr(r, "gross_requirement", Decimal("0.0")) or (r.scheduled_consumable_qty or Decimal("0.0"))
            msl_qty = getattr(r, "msl", Decimal("0.0")) or Decimal("0.0")
            net_order = max(Decimal("0.0000"), (gross_req + msl_qty) - cls_stk)

            has_stock_data = (code_upper in t2_stock_by_code) or (grn_rec > Decimal("0")) or (op_stock > Decimal("0"))
            stock_qty_val = format(cls_stk, ".4f") if has_stock_data else format(r.stock_qty, ".4f")
            shortage_qty_val = format(net_order, ".4f") if has_stock_data else format(r.shortage_qty, ".4f")

            is_dept = is_department_unit(r.plant) or is_department_unit(r.plant_id) or r.part_number == "DEPARTMENT_INDENT" or r.process_name in ("DEPARTMENT_INDENT", "MAINTENANCE")
            row_rule_type = "PLANT_REQUEST" if is_dept else "PRODUCTION_RATE"
            row_status = r.status
            if is_dept:
                if row_status in ("Configuration required", "DRAFT"):
                    row_status = "Calculated"
                if net_order > Decimal("0"):
                    row_status = "Critical shortage" if cls_stk <= Decimal("0") else "Low"
                elif cls_stk > Decimal("0") or has_stock_data:
                    row_status = "Normal"
                k = (_normalize_plant_identifier(r.plant), code_upper)
                hist_list = history_dept_mrrs.get(k, [r])
                avg_qty, active_count = compute_non_zero_rolling_average(
                    hist_list, t_month or r.planning_month or 1, t_year or r.planning_year or 2026
                )
                row_hist_avg = format(avg_qty, ".4f")
                row_active_count = active_count
                row_doc_ref = r.part_number if r.part_number != "DEPARTMENT_INDENT" else None
            else:
                row_hist_avg = "0.0000"
                row_active_count = 0
                row_doc_ref = None

            results.append(
                RequirementWorkspaceRecord(
                    id=str(r.id),
                    plan_id=str(r.planning_version_id) if r.planning_version_id else None,
                    planning_period=r.planning_period,
                    planning_month=r.planning_month,
                    planning_year=r.planning_year,
                    revision=r.planning_version.revision_label if r.planning_version else "R0",
                    # Group 1: Component
                    part_name=r.part_name,
                    part_number=r.part_number,
                    # Group 2: Consumables
                    consumable_code=r.consumable_code,
                    consumable_name=r.consumable_name,
                    process_name=r.process_name,
                    part_thickness=format(r.part_thickness, ".4f"),
                    process_count=r.process_count,
                    production_order_qty=format(r.production_order_qty, ".4f"),
                    scheduled_consumable_qty=format(r.scheduled_consumable_qty, ".4f"),
                    # Group 3: Operational fields
                    plant=r.plant,
                    process=r.process_name,
                    description=r.consumable_name,
                    unit=r.unit,
                    rule_type=row_rule_type,
                    required_qty=format(r.scheduled_consumable_qty, ".4f"),
                    stock_qty=stock_qty_val,
                    shortage_qty=shortage_qty_val,
                    po_pending_qty=format(r.po_pending_qty, ".4f"),
                    msl=format(msl_qty, ".4f"),
                    status=row_status,
                    remarks=r.remarks,
                    # Month-End Overwrite & MRP Balance Tracking
                    opening_stock=format(op_stock, ".4f"),
                    grn_received_qty=format(grn_rec, ".4f"),
                    consumed_qty=format(consumed, ".4f"),
                    closing_stock=format(cls_stk, ".4f"),
                    gross_requirement=format(gross_req, ".4f"),
                    net_order_requirement=format(net_order, ".4f"),
                    historical_avg_qty=row_hist_avg,
                    active_month_count=row_active_count,
                    doc_ref=row_doc_ref,
                    last_synced_at=r.last_synced_at,
                    grn_source_file=r.grn_source_file,
                    invoice_no=r.invoice_no,
                    grn_date=r.grn_date,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
            )

    else:
        # Fallback to existing CalculatedRequirement records
        versions_query = select(PlanningVersion).order_by(PlanningVersion.planning_period, PlanningVersion.version_number.desc())
        if target_period:
            versions_query = versions_query.where(PlanningVersion.planning_period == target_period)
        versions = [period_version] if central else session.scalars(versions_query).all()
        latest: dict[str, PlanningVersion] = {}
        for version in versions:
            latest.setdefault(version.planning_period, version)

        # Build index of MonthlyRequirementRecord for this period
        mrr_query = select(MonthlyRequirementRecord).options(joinedload(MonthlyRequirementRecord.planning_version)).where(
            MonthlyRequirementRecord.is_deleted == False,
        )
        if target_period:
            if target_seq:
                mrr_query = mrr_query.where(
                    or_(
                        MonthlyRequirementRecord.planning_period == target_period,
                        and_(
                            func.upper(MonthlyRequirementRecord.plant).in_(dept_names_upper),
                            (MonthlyRequirementRecord.planning_year * 12 + MonthlyRequirementRecord.planning_month) <= target_seq,
                        ),
                    )
                )
            else:
                mrr_query = mrr_query.where(MonthlyRequirementRecord.planning_period == target_period)

        all_mrr_records = session.scalars(mrr_query).all() if (target_period and has_mrr) else []
        mrr_records = [r for r in all_mrr_records if r.planning_period == target_period]
        for r in all_mrr_records:
            if is_department_unit(r.plant) or is_department_unit(r.plant_id):
                k = (_normalize_plant_identifier(r.plant), (r.consumable_code or "").strip().upper())
                history_dept_mrrs.setdefault(k, []).append(r)

        mrr_by_code: dict[str, list[MonthlyRequirementRecord]] = {}
        for m in mrr_records:
            mrr_by_code.setdefault(m.consumable_code.strip().upper(), []).append(m)

        for version in latest.values():
            requirements = session.scalars(
                select(CalculatedRequirement).options(joinedload(CalculatedRequirement.consumable),
                    joinedload(CalculatedRequirement.plant), joinedload(CalculatedRequirement.process),
                    joinedload(CalculatedRequirement.product))
                .where(CalculatedRequirement.planning_version_id == version.id)
            ).all()
            errors = session.scalars(
                select(RequirementCalculationError).options(joinedload(RequirementCalculationError.plant),
                    joinedload(RequirementCalculationError.product), joinedload(RequirementCalculationError.consumable),
                    joinedload(RequirementCalculationError.prd_order_item))
                .where(RequirementCalculationError.planning_version_id == version.id)
            ).all()
            errors = [
                err for err in errors
                if not (is_department_unit(err.plant.name if err.plant else None)
                        or (getattr(err, "context_data", None) or {}).get("rule_type") == "PLANT_REQUEST"
                        or getattr(err, "product_code", "") == "DEPARTMENT_INDENT")
            ]

            from app.services.rules import norm_reference_data
            references = norm_reference_data(session, list({row.rule_id for row in requirements}))
            for row in requirements:
                material, plant, process, product = row.consumable, row.plant, row.process, row.product

                p_thick = "0.0000"
                p_count = 1
                if isinstance(row.parameters, dict):
                    reference = references.get(row.rule_id) or {}
                    p_thick = str(reference.get("thickness") or row.parameters.get("thickness", "0.0000"))
                    p_count = int(Decimal(str(reference.get("process_count") or row.parameters.get("process_count", row.parameters.get("processes", 1)))))

                mat_code = material.code.strip().upper() if material and material.code else ""
                matching_mrrs = mrr_by_code.get(mat_code, [])
                grn_rec_qty = Decimal("0.0")
                mrr_file = None
                mrr_inv = None
                mrr_dt = None
                mrr_sync = None
                matched_mrr = None
                if matching_mrrs:
                    plant_k = _normalize_plant_identifier(plant.name if plant else None)
                    matched_mrr = next((m for m in matching_mrrs if _normalize_plant_identifier(m.plant_id or m.plant) == plant_k), matching_mrrs[0])
                    grn_rec_qty = matched_mrr.grn_received_qty or Decimal("0.0")
                    mrr_file = matched_mrr.grn_source_file
                    mrr_inv = matched_mrr.invoice_no
                    mrr_dt = matched_mrr.grn_date
                    mrr_sync = matched_mrr.last_synced_at

                if mat_code in t2_stock_by_code:
                    op_stock = t2_stock_by_code[mat_code]
                elif matched_mrr:
                    op_stock = getattr(matched_mrr, "opening_stock", Decimal("0.0")) or Decimal("0.0")
                else:
                    op_stock = Decimal("0.0")

                consumed = (getattr(matched_mrr, "consumed_qty", Decimal("0.0")) or Decimal("0.0")) if matched_mrr else Decimal("0.0")
                cls_stk = (op_stock + grn_rec_qty) - consumed
                gross_req = row.calculated_qty or Decimal("0.0")
                msl_qty = (getattr(matched_mrr, "msl", Decimal("0.0")) or Decimal("0.0")) if matched_mrr else Decimal("0.0")
                net_order = max(Decimal("0.0000"), (gross_req + msl_qty) - cls_stk)

                has_stock_data = (mat_code in t2_stock_by_code) or bool(matched_mrr and (grn_rec_qty > Decimal("0") or op_stock > Decimal("0")))
                stock_display = format(cls_stk, ".4f") if has_stock_data else "Unavailable"
                shortage_display = format(net_order, ".4f") if has_stock_data else "Unavailable"

                results.append(
                    RequirementWorkspaceRecord(
                        id=str(row.id),
                        plan_id=str(version.id),
                        planning_period=version.planning_period,
                        revision=version.revision_label,
                        part_name=product.name if product else "Component",
                        part_number=(product.part_number or product.code) if product else "PROD-ITEM",
                        consumable_code=material.code if material else "",
                        consumable_name=material.name if material else "",
                        process_name=process.name if process else "",
                        part_thickness=p_thick,
                        process_count=p_count,
                        production_order_qty=format(row.source_production_qty, ".4f"),
                        scheduled_consumable_qty=format(row.calculated_qty, ".4f"),
                        plant=plant.name if plant else "Central / unassigned",
                        process=process.name if process else "",
                        description=material.name if material else "",
                        unit=row.uom,
                        required_qty=format(row.calculated_qty, ".4f"),
                        stock_qty=stock_display,
                        shortage_qty=shortage_display,
                        po_pending_qty="Unavailable",
                        msl="Unavailable" if not has_stock_data else format(msl_qty, ".4f"),
                        status="Calculated",
                        remarks=row.rounding_policy,
                        opening_stock=format(op_stock, ".4f"),
                        grn_received_qty=format(grn_rec_qty, ".4f"),
                        consumed_qty=format(consumed, ".4f"),
                        closing_stock=format(cls_stk, ".4f"),
                        gross_requirement=format(gross_req, ".4f"),
                        net_order_requirement=format(net_order, ".4f"),
                        last_synced_at=mrr_sync,
                        grn_source_file=mrr_file,
                        invoice_no=mrr_inv,
                        grn_date=mrr_dt,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                    )
                )

            for error in errors:
                plant, product, material = error.plant, error.product, error.consumable
                mat_code = material.code.strip().upper() if material and material.code else ""
                matching_mrrs = mrr_by_code.get(mat_code, [])
                grn_rec_qty = Decimal("0.0")
                mrr_file = None
                mrr_inv = None
                mrr_dt = None
                mrr_sync = None
                matched_mrr = None
                if matching_mrrs:
                    plant_k = _normalize_plant_identifier(plant.name if plant else None)
                    matched_mrr = next((m for m in matching_mrrs if _normalize_plant_identifier(m.plant_id or m.plant) == plant_k), matching_mrrs[0])
                    grn_rec_qty = matched_mrr.grn_received_qty or Decimal("0.0")
                    mrr_file = matched_mrr.grn_source_file
                    mrr_inv = matched_mrr.invoice_no
                    mrr_dt = matched_mrr.grn_date
                    mrr_sync = matched_mrr.last_synced_at

                if mat_code in t2_stock_by_code:
                    op_stock = t2_stock_by_code[mat_code]
                elif matched_mrr:
                    op_stock = getattr(matched_mrr, "opening_stock", Decimal("0.0")) or Decimal("0.0")
                else:
                    op_stock = Decimal("0.0")

                consumed = (getattr(matched_mrr, "consumed_qty", Decimal("0.0")) or Decimal("0.0")) if matched_mrr else Decimal("0.0")
                cls_stk = (op_stock + grn_rec_qty) - consumed

                has_stock_data = (mat_code in t2_stock_by_code) or bool(matched_mrr and (grn_rec_qty > Decimal("0") or op_stock > Decimal("0")))
                stock_display = format(cls_stk, ".4f") if has_stock_data else "Unavailable"

                results.append(
                    RequirementWorkspaceRecord(
                        id=str(error.id),
                        plan_id=str(version.id),
                        planning_period=version.planning_period,
                        revision=version.revision_label,
                        part_name=product.name if product else "Unresolved",
                        part_number=(product.part_number or product.code) if product else "Unresolved",
                        consumable_code=material.code if material else "",
                        consumable_name=material.name if material else error.error_message,
                        process_name="Unresolved",
                        part_thickness="0.0000",
                        process_count=1,
                        production_order_qty=format(error.prd_order_item.planned_quantity, '.4f') if error.prd_order_item else "Unavailable",
                        scheduled_consumable_qty="Unavailable",
                        plant=plant.name if plant else "Unresolved",
                        process="Unresolved",
                        description=error.error_message,
                        unit="",
                        required_qty="Unavailable",
                        stock_qty=stock_display,
                        shortage_qty="Unavailable",
                        po_pending_qty="Unavailable",
                        msl="Unavailable",
                        status="Configuration required",
                        remarks=error.error_code,
                        opening_stock=format(op_stock, ".4f"),
                        grn_received_qty=format(grn_rec_qty, ".4f"),
                        consumed_qty=format(consumed, ".4f"),
                        closing_stock=format(cls_stk, ".4f"),
                        gross_requirement="0.0000",
                        net_order_requirement="0.0000",
                        last_synced_at=mrr_sync,
                        grn_source_file=mrr_file,
                        invoice_no=mrr_inv,
                        grn_date=mrr_dt,
                        created_at=error.created_at,
                    )
                )

            # Include departmental indents, store receipts, and standalone GRN intake items from MonthlyRequirementRecord
            added_keys = {(r.consumable_code.strip().upper(), _normalize_plant_identifier(r.plant)) for r in results if r.consumable_code}
            added_codes = {r.consumable_code.strip().upper() for r in results if r.consumable_code}
            for m in mrr_records:
                is_dept = (
                    is_department_unit(m.plant)
                    or is_department_unit(m.plant_id)
                    or m.part_number == "DEPARTMENT_INDENT"
                    or m.process_name in ("DEPARTMENT_INDENT", "MAINTENANCE")
                )
                is_store_receipt = (
                    m.process_name == "Store Receipt"
                    or bool(m.grn_source_file)
                    or (m.grn_received_qty and m.grn_received_qty > Decimal("0"))
                )
                m_code = m.consumable_code.strip().upper()
                m_plant_norm = _normalize_plant_identifier(m.plant_id or m.plant)
                should_splice = False
                if is_dept and (m_code, m_plant_norm) not in added_keys:
                    should_splice = True
                elif is_store_receipt and m_code not in added_codes:
                    should_splice = True

                if should_splice:
                    if m_code in t2_stock_by_code:
                        m_op = t2_stock_by_code[m_code]
                    else:
                        m_op = getattr(m, "opening_stock", Decimal("0.0")) or Decimal("0.0")

                    m_grn = getattr(m, "grn_received_qty", Decimal("0.0")) or Decimal("0.0")
                    m_con = getattr(m, "consumed_qty", Decimal("0.0")) or Decimal("0.0")
                    m_cls = (m_op + m_grn) - m_con
                    m_gross = getattr(m, "gross_requirement", Decimal("0.0")) or (m.scheduled_consumable_qty or Decimal("0.0"))
                    m_msl = getattr(m, "msl", Decimal("0.0")) or Decimal("0.0")
                    m_net = max(Decimal("0.0000"), (m_gross + m_msl) - m_cls)

                    has_stock_data = (m_code in t2_stock_by_code) or (m_grn > Decimal("0")) or (m_op > Decimal("0"))
                    m_stk = m_cls if has_stock_data else m.stock_qty
                    m_short = m_net if has_stock_data else m.shortage_qty

                    m_status = m.status
                    if is_dept:
                        if m_status in ("Configuration required", "DRAFT"):
                            m_status = "Calculated"
                        if m_net > Decimal("0"):
                            m_status = "Critical shortage" if m_cls <= Decimal("0") else "Low"
                        elif m_cls > Decimal("0") or has_stock_data:
                            m_status = "Normal"
                        k = (_normalize_plant_identifier(m.plant), m_code)
                        hist_list = history_dept_mrrs.get(k, [m])
                        avg_qty, active_count = compute_non_zero_rolling_average(
                            hist_list, t_month or m.planning_month or 1, t_year or m.planning_year or 2026
                        )
                        m_hist_avg = format(avg_qty, ".4f")
                        m_active_count = active_count
                        m_doc_ref = m.part_number if m.part_number != "DEPARTMENT_INDENT" else None
                    else:
                        m_hist_avg = "0.0000"
                        m_active_count = 0
                        m_doc_ref = None

                    results.append(
                        RequirementWorkspaceRecord(
                            id=str(m.id),
                            plan_id=str(m.planning_version_id) if m.planning_version_id else str(version.id),
                            planning_period=m.planning_period,
                            planning_month=m.planning_month,
                            planning_year=m.planning_year,
                            revision=m.planning_version.revision_label if m.planning_version else version.revision_label,
                            part_name=m.part_name,
                            part_number=m.part_number,
                            consumable_code=m.consumable_code,
                            consumable_name=m.consumable_name,
                            process_name=m.process_name,
                            part_thickness=format(m.part_thickness, ".4f"),
                            process_count=m.process_count,
                            production_order_qty=format(m.production_order_qty, ".4f"),
                            scheduled_consumable_qty=format(m.scheduled_consumable_qty, ".4f"),
                            plant=m.plant,
                            process=m.process_name,
                            description=m.consumable_name,
                            unit=m.unit,
                            rule_type="PLANT_REQUEST" if is_dept else "PRODUCTION_RATE",
                            required_qty=format(m.scheduled_consumable_qty, ".4f"),
                            stock_qty=format(m_stk, ".4f"),
                            shortage_qty=format(m_short, ".4f"),
                            po_pending_qty=format(m.po_pending_qty, ".4f"),
                            msl=format(m_msl, ".4f"),
                            status=m_status,
                            remarks=m.remarks,
                            opening_stock=format(m_op, ".4f"),
                            grn_received_qty=format(m_grn, ".4f"),
                            consumed_qty=format(m_con, ".4f"),
                            closing_stock=format(m_cls, ".4f"),
                            gross_requirement=format(m_gross, ".4f"),
                            net_order_requirement=format(m_net, ".4f"),
                            historical_avg_qty=m_hist_avg,
                            active_month_count=m_active_count,
                            doc_ref=m_doc_ref,
                            last_synced_at=m.last_synced_at,
                            grn_source_file=m.grn_source_file,
                            invoice_no=m.invoice_no,
                            grn_date=m.grn_date,
                            created_at=m.created_at,
                            updated_at=m.updated_at,
                        )
                    )
                    added_codes.add(m_code)
                    added_keys.add((m_code, m_plant_norm))

    # Auto-populate uninitialized departmental items from historical baseline
    if target_period and t_month and t_year and history_dept_mrrs:
        existing_dept_keys = {
            (_normalize_plant_identifier(res.plant), (res.consumable_code or "").strip().upper())
            for res in results
            if res.consumable_code and (is_department_unit(res.plant) or res.rule_type == "PLANT_REQUEST")
        }
        for (dept_key, code_upper), hist_records in history_dept_mrrs.items():
            if (dept_key, code_upper) not in existing_dept_keys:
                sorted_hist = sorted(
                    hist_records,
                    key=lambda x: ((x.planning_year or 0) * 12 + (x.planning_month or 0)),
                    reverse=True,
                )
                sample = sorted_hist[0]
                avg_qty, active_count = compute_non_zero_rolling_average(hist_records, t_month, t_year)
                dept_disp = DEPARTMENT_DISPLAY_NAMES.get(dept_key, sample.plant)
                proc_name = "MAINTENANCE" if dept_key == "PMD" else "DEPARTMENT_INDENT"
                part_no = sample.part_number or "DEPARTMENT_INDENT"
                doc_ref_val = part_no if part_no != "DEPARTMENT_INDENT" else None

                op_stock = t2_stock_by_code.get(code_upper, Decimal("0.0"))
                cls_stk = op_stock
                net_order = max(Decimal("0.0000"), avg_qty - cls_stk)
                has_stock_data = (code_upper in t2_stock_by_code) or (op_stock > Decimal("0"))
                stk_str = format(cls_stk, ".4f") if has_stock_data else "0.0000"
                shortage_str = format(net_order, ".4f")
                status_str = "Critical shortage" if cls_stk <= Decimal("0") and avg_qty > Decimal("0") else "Normal"

                results.append(
                    RequirementWorkspaceRecord(
                        id=f"auto-{dept_disp}-{code_upper}",
                        plan_id=str(period_version.id) if period_version else None,
                        planning_period=target_period,
                        planning_month=t_month,
                        planning_year=t_year,
                        revision=period_version.revision_label if period_version else "R0",
                        part_name=dept_disp,
                        part_number=part_no,
                        consumable_code=code_upper,
                        consumable_name=sample.consumable_name,
                        process_name=proc_name,
                        part_thickness="0.0000",
                        process_count=1,
                        production_order_qty="0.0000",
                        scheduled_consumable_qty=format(avg_qty, ".4f"),
                        plant=dept_disp,
                        process=proc_name,
                        description=sample.consumable_name,
                        unit=sample.unit or "NOS",
                        rule_type="PLANT_REQUEST",
                        required_qty=format(avg_qty, ".4f"),
                        stock_qty=stk_str,
                        shortage_qty=shortage_str,
                        po_pending_qty="0.0000",
                        msl="0.0000",
                        status=status_str,
                        remarks=sample.remarks or f"Departmental indent: {dept_disp}",
                        opening_stock=format(op_stock, ".4f"),
                        grn_received_qty="0.0000",
                        consumed_qty="0.0000",
                        closing_stock=format(cls_stk, ".4f"),
                        gross_requirement=format(avg_qty, ".4f"),
                        net_order_requirement=format(net_order, ".4f"),
                        historical_avg_qty=format(avg_qty, ".4f"),
                        active_month_count=active_count,
                        doc_ref=doc_ref_val,
                    )
                )

    # Filter predicate
    def matches(record: RequirementWorkspaceRecord) -> bool:
        if plant_filter and plant_filter.upper() != "ALL":
            pf = plant_filter.strip().lower().replace("_", " ")
            rp = record.plant.strip().lower().replace("_", " ")
            if pf not in rp and rp not in pf:
                return False
        if consumable_filter and consumable_filter.upper() != "ALL":
            if (
                consumable_filter.lower() not in record.consumable_code.lower()
                and consumable_filter.lower() not in record.consumable_name.lower()
            ):
                return False
        if status_filter and status_filter.upper() != "ALL" and status_filter.lower() not in record.status.lower():
            return False
        if search:
            q = search.lower()
            fields = [
                record.part_name,
                record.part_number,
                record.consumable_code,
                record.consumable_name,
                record.process_name,
                record.plant,
                record.status,
                record.remarks or "",
            ]
            if not any(q in f.lower() for f in fields):
                return False
        return True

    return [r for r in results if matches(r)]


def load_workspace_view(session, month, year, *, plant=None, consumable=None, status=None, search=None):
    """Use one authenticated request/connection for a period's metadata and rows."""
    return {'plan_metadata': get_monthly_plan_metadata(session, month, year),
        'records': calculate_workspace_requirements(session, month=month, year=year,
            plant_filter=plant, consumable_filter=consumable, status_filter=status, search=search)}


def _normalize_header(hdr: Any) -> str:
    if hdr is None:
        return ""
    text = str(hdr).strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


MONTH_MAP: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _parse_month_col_header(val: Any) -> Optional[tuple[int, int]]:
    """Extract (month, year) from month header text like Oct'26, Sept'26, April'2026."""
    if not val:
        return None
    s = str(val).strip().lower()
    m = re.search(r"([a-z]+)[\'\s\-]*([0-9]{2,4})", s)
    if m:
        mon_str, yr_str = m.group(1), m.group(2)
        if mon_str in MONTH_MAP:
            mon = MONTH_MAP[mon_str]
            yr = int(yr_str)
            if yr < 100:
                yr += 2000
            return (mon, yr)
    return None


def compute_non_zero_rolling_average(
    records: list[Any],
    target_month: int,
    target_year: int,
) -> tuple[Decimal, int]:
    """Calculates active month rolling average excluding zero/blank months.

    Evaluates records prior to target period (year * 12 + month).
    If no prior records exist, falls back to records <= target period.
    Only counts months where scheduled_consumable_qty > 0.
    Returns (average_qty, active_month_count).
    """
    target_seq = target_year * 12 + target_month
    prior_records = [
        r for r in records
        if ((getattr(r, "planning_year", 0) or 0) * 12 + (getattr(r, "planning_month", 0) or 0)) < target_seq
    ]
    if not prior_records:
        prior_records = [
            r for r in records
            if ((getattr(r, "planning_year", 0) or 0) * 12 + (getattr(r, "planning_month", 0) or 0)) <= target_seq
        ]

    active_qtys: list[Decimal] = []
    for r in prior_records:
        qty_val = getattr(r, "scheduled_consumable_qty", None)
        if qty_val is not None:
            try:
                dec = Decimal(str(qty_val))
                if dec > Decimal("0"):
                    active_qtys.append(dec)
            except Exception:
                pass

    n_active = len(active_qtys)
    if n_active == 0:
        return Decimal("0.0000"), 0

    avg_qty = (sum(active_qtys) / Decimal(str(n_active))).quantize(Decimal("0.0001"))
    return avg_qty, n_active


def _parse_departmental_sheet_all_months(
    ws, dept_key: str
) -> dict[tuple[int, int], list[dict[str, Any]]]:
    """Dynamically parses a departmental consumable indent worksheet across all historical months.

    Detects all month/year columns present alongside Item Id., Item Description,
    Part No. (doc ref), and Unit using memory-efficient streaming.
    """
    dept_display = DEPARTMENT_DISPLAY_NAMES.get(dept_key, dept_key)
    proc_name = "MAINTENANCE" if dept_key == "PMD" else "DEPARTMENT_INDENT"

    if hasattr(ws, "iter_rows"):
        header_rows = list(ws.iter_rows(min_row=1, max_row=10, values_only=True))
    else:
        header_rows = [
            [ws.cell(r, c).value for c in range(1, min(40, (ws.max_column or 0) + 1))]
            for r in range(1, min(10, (ws.max_row or 0)) + 1)
        ]

    month_cols: dict[int, tuple[int, int]] = {}
    header_row_idx: Optional[int] = None
    col_map: dict[str, int] = {}

    for r_idx_0, row_cells in enumerate(header_rows):
        for c_idx, val in enumerate(row_cells):
            if val is None:
                continue
            norm_val = str(val).strip().lower()
            if "planning period" in norm_val or "exported" in norm_val or "knl" in norm_val:
                continue
            parsed_m = _parse_month_col_header(val)
            if parsed_m and c_idx not in month_cols:
                month_cols[c_idx] = parsed_m

        norm_row = [_normalize_header(v) for v in row_cells]
        row_map: dict[str, int] = {}
        for c_idx, text in enumerate(norm_row):
            if not text:
                continue
            if any(k in text for k in ["item id", "item code", "consumable id", "consumable code", "itemid"]):
                row_map.setdefault("item_id", c_idx)
            elif any(k in text for k in ["description", "material name", "item description"]):
                row_map.setdefault("description", c_idx)
            elif any(k == text or k in text for k in ["unit", "uom"]):
                row_map.setdefault("unit", c_idx)
            elif any(k in text for k in ["part no", "part number", "doc ref", "partno", "part doc ref"]):
                row_map.setdefault("part_no", c_idx)
            elif any(k in text for k in ["location", "department", "dept"]):
                row_map.setdefault("dept", c_idx)

        if "item_id" in row_map or "description" in row_map:
            header_row_idx = r_idx_0
            col_map = row_map

    item_col = col_map.get("item_id", 0)
    desc_col = col_map.get("description", 1)
    unit_col = col_map.get("unit", 2)
    part_col = col_map.get("part_no", None)
    dept_col = col_map.get("dept", None)

    start_row_1based = (header_row_idx + 2) if header_row_idx is not None else 4
    results_by_period: dict[tuple[int, int], list[dict[str, Any]]] = {
        period: [] for period in month_cols.values()
    }

    if hasattr(ws, "iter_rows"):
        row_stream = ws.iter_rows(min_row=start_row_1based, values_only=True)
    else:
        row_stream = (
            [ws.cell(r, c).value for c in range(1, min(40, (ws.max_column or 0) + 1))]
            for r in range(start_row_1based, (ws.max_row or 0) + 1)
        )

    for r_offset, row_vals in enumerate(row_stream):
        r_idx_0 = (start_row_1based - 1) + r_offset
        if not any(v is not None and str(v).strip() != "" for v in row_vals):
            continue

        raw_item = row_vals[item_col] if item_col < len(row_vals) else None
        raw_desc = row_vals[desc_col] if desc_col < len(row_vals) else None
        raw_unit = row_vals[unit_col] if unit_col < len(row_vals) else None
        raw_part = row_vals[part_col] if (part_col is not None and part_col < len(row_vals)) else None
        raw_dept = row_vals[dept_col] if (dept_col is not None and dept_col < len(row_vals)) else None

        item_str = str(raw_item or "").strip()
        desc_str = str(raw_desc or "").strip()
        part_str = str(raw_part or "").strip() if raw_part else ""
        dept_str = str(raw_dept or "").strip() if raw_dept else ""

        if not item_str and not desc_str:
            continue
        item_lower = item_str.lower()
        if item_lower in ("item id", "item id.", "s.no", "to location", "location", "dept:", "total"):
            continue
        if "total" in desc_str.lower() or "summary" in desc_str.lower():
            continue

        code_val = item_str if item_str else desc_str
        name_val = desc_str if desc_str else item_str
        unit_str = str(raw_unit or "NOS").strip() or "NOS"
        part_no = part_str if part_str and part_str != "DEPARTMENT_INDENT" else "DEPARTMENT_INDENT"
        doc_ref = part_str if part_str and part_str != "DEPARTMENT_INDENT" else None

        if dept_str and (dept_key == "DEPARTMENTAL" or not dept_key):
            norm_dept = _normalize_plant_identifier(dept_str)
            row_dept_display = DEPARTMENT_DISPLAY_NAMES.get(norm_dept, dept_str)
        else:
            row_dept_display = dept_display

        row_proc_name = "MAINTENANCE" if _normalize_plant_identifier(row_dept_display) == "PMD" else "DEPARTMENT_INDENT"

        for c_idx, (m, y) in month_cols.items():
            raw_qty = row_vals[c_idx] if c_idx < len(row_vals) else None
            try:
                qty_dec = Decimal(str(raw_qty).replace(",", "").strip()) if raw_qty is not None else Decimal("0")
            except Exception:
                qty_dec = Decimal("0")

            rec = {
                "row_index": r_idx_0 + 1,
                "planning_month": m,
                "planning_year": y,
                "planning_period": f"{y:04d}-{m:02d}",
                "part_name": row_dept_display,
                "part_number": part_no,
                "doc_ref": doc_ref,
                "consumable_code": code_val,
                "consumable_name": name_val,
                "process_name": row_proc_name,
                "part_thickness": "0.0000",
                "process_count": 1,
                "production_order_qty": "0.0000",
                "scheduled_consumable_qty": format(qty_dec, ".4f"),
                "plant": row_dept_display,
                "unit": unit_str,
                "required_qty": format(qty_dec, ".4f"),
                "gross_requirement": format(qty_dec, ".4f"),
                "rule_type": "PLANT_REQUEST",
                "status": "Normal",
                "remarks": f"Departmental indent: {row_dept_display}",
            }
            results_by_period[(m, y)].append(rec)

    return results_by_period


def _parse_departmental_sheet(
    ws, dept_key: str, month: int, year: int
) -> list[dict[str, Any]]:
    """Dynamically parses a departmental consumable indent worksheet.

    Scans first 10 rows for target month column and item/description/unit/qty headers
    using memory-efficient streaming.
    """
    month_abbr = calendar.month_abbr[month].lower()
    month_full = calendar.month_name[month].lower()
    year_str = str(year)
    year_short = year_str[2:]
    month_targets = [
        f"{month_abbr}'{year_short}",
        f"{month_abbr} {year_short}",
        f"{month_abbr}-{year_short}",
        f"{month_abbr}{year_short}",
        f"{month_abbr}'{year_str}",
        f"{month_abbr} {year_str}",
        f"{month_abbr}-{year_str}",
    ]

    target_month_col: Optional[int] = None
    header_row_idx: Optional[int] = None
    col_map: dict[str, int] = {}

    if hasattr(ws, "iter_rows"):
        header_rows = [list(r[:40]) for r in ws.iter_rows(min_row=1, max_row=10, values_only=True)]
    else:
        header_rows = [
            [ws.cell(r, c).value for c in range(1, min(40, (ws.max_column or 0) + 1))]
            for r in range(1, min(10, (ws.max_row or 0)) + 1)
        ]

    for r_idx_0, row_cells in enumerate(header_rows):
        r = r_idx_0 + 1

        # 1. Target month column search
        if target_month_col is None:
            for c_idx, val in enumerate(row_cells):
                if val is None:
                    continue
                norm_val = str(val).strip().lower()
                if "planning period" in norm_val or "exported" in norm_val or "knl" in norm_val:
                    continue
                if any(t in norm_val for t in month_targets) or (month_abbr in norm_val and year_short in norm_val):
                    target_month_col = c_idx
                    break

        # 2. Check for column headers
        norm_row = [_normalize_header(v) for v in row_cells]
        row_map = {}
        for c_idx, text in enumerate(norm_row):
            if not text:
                continue
            if any(k in text for k in ["item id", "item code", "consumable id", "consumable code", "itemid"]):
                row_map.setdefault("item_id", c_idx)
            elif any(k in text for k in ["description", "material name", "item description"]):
                row_map.setdefault("description", c_idx)
            elif any(k == text or k in text for k in ["unit", "uom"]):
                row_map.setdefault("unit", c_idx)
            elif any(k in text for k in ["part no", "part number", "doc ref", "partno", "part doc ref"]):
                row_map.setdefault("part_no", c_idx)
            elif any(k in text for k in ["location", "department", "dept"]):
                row_map.setdefault("dept", c_idx)
            elif any(k == text or k in text for k in ["qty", "quantity", "req qty", "requested qty"]):
                row_map.setdefault("qty", c_idx)

        if "item_id" in row_map or "description" in row_map:
            header_row_idx = r
            col_map = row_map
            if target_month_col is not None:
                break

    if header_row_idx is None:
        header_row_idx = 2
        col_map = {"item_id": 1, "description": 2, "unit": 3, "qty": 4}

    if target_month_col is not None:
        col_map["qty"] = target_month_col
    elif "qty" not in col_map:
        col_map["qty"] = 4

    item_col = col_map.get("item_id", 0)
    desc_col = col_map.get("description", 1)
    unit_col = col_map.get("unit", 2)
    qty_col = col_map.get("qty", 3)
    part_col = col_map.get("part_no", None)
    dept_col = col_map.get("dept", None)

    dept_display = DEPARTMENT_DISPLAY_NAMES.get(dept_key, dept_key)

    start_row_1based = header_row_idx + 1
    if hasattr(ws, "iter_rows"):
        row_stream = ws.iter_rows(min_row=start_row_1based, values_only=True)
    else:
        row_stream = (
            [ws.cell(r, c).value for c in range(1, min(40, (ws.max_column or 0) + 1))]
            for r in range(start_row_1based, (ws.max_row or 0) + 1)
        )

    parsed_rows: list[dict[str, Any]] = []
    for r_offset, row_tuple in enumerate(row_stream):
        r_idx = start_row_1based + r_offset
        row_vals = list(row_tuple[:40]) if row_tuple else []
        if not any(v is not None and str(v).strip() != "" for v in row_vals):
            continue

        raw_item = row_vals[item_col] if item_col < len(row_vals) else None
        raw_desc = row_vals[desc_col] if desc_col < len(row_vals) else None
        raw_unit = row_vals[unit_col] if unit_col < len(row_vals) else None
        raw_qty = row_vals[qty_col] if qty_col < len(row_vals) else None
        raw_part = row_vals[part_col] if (part_col is not None and part_col < len(row_vals)) else None
        raw_dept = row_vals[dept_col] if (dept_col is not None and dept_col < len(row_vals)) else None

        item_str = str(raw_item or "").strip()
        desc_str = str(raw_desc or "").strip()
        part_str = str(raw_part or "").strip() if raw_part else ""
        dept_str = str(raw_dept or "").strip() if raw_dept else ""

        # Skip headers or summary lines
        item_lower = item_str.lower()
        if not item_str and not desc_str:
            continue
        if item_lower in ("item id", "item id.", "s.no", "to location", "location", "dept:", "total"):
            continue
        if "total" in desc_str.lower() or "summary" in desc_str.lower():
            continue

        try:
            qty_dec = Decimal(str(raw_qty).replace(",", "").strip()) if raw_qty is not None else Decimal("0")
        except Exception:
            qty_dec = Decimal("0")

        unit_str = str(raw_unit or "NOS").strip() or "NOS"
        code_val = item_str if item_str else desc_str
        name_val = desc_str if desc_str else item_str

        if dept_str and (dept_key == "DEPARTMENTAL" or not dept_key):
            norm_dept = _normalize_plant_identifier(dept_str)
            row_dept_display = DEPARTMENT_DISPLAY_NAMES.get(norm_dept, dept_str)
        else:
            row_dept_display = dept_display

        row_proc_name = "MAINTENANCE" if _normalize_plant_identifier(row_dept_display) == "PMD" else "DEPARTMENT_INDENT"
        part_no = part_str if part_str and part_str != "DEPARTMENT_INDENT" else "DEPARTMENT_INDENT"
        doc_ref = part_str if part_str and part_str != "DEPARTMENT_INDENT" else None

        parsed_rows.append(
            {
                "row_index": r_idx,
                "part_name": row_dept_display,
                "part_number": part_no,
                "doc_ref": doc_ref,
                "consumable_code": code_val,
                "consumable_name": name_val,
                "process_name": row_proc_name,
                "part_thickness": "0.0000",
                "process_count": 1,
                "production_order_qty": "0.0000",
                "scheduled_consumable_qty": format(qty_dec, ".4f"),
                "plant": row_dept_display,
                "unit": unit_str,
                "required_qty": format(qty_dec, ".4f"),
                "gross_requirement": format(qty_dec, ".4f"),
                "rule_type": "PLANT_REQUEST",
                "status": "Normal",
                "remarks": f"Departmental indent: {row_dept_display}",
                "is_valid": True,
                "errors": [],
            }
        )
    return parsed_rows


def inspect_excel_file(
    file_bytes: bytes, filename: str, month: int, year: int, session
) -> RequirementExcelInspectResponse:
    planning_period = f"{year:04d}-{month:02d}"

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        raise ApplicationError("INVALID_EXCEL_FILE", f"Could not read Excel file: {str(e)}", 400)

    try:
        return _inspect_excel_file_core(wb, filename, month, year, planning_period, session)
    finally:
        try:
            wb.close()
        except Exception:
            pass


def _inspect_excel_file_core(
    wb, filename: str, month: int, year: int, planning_period: str, session
) -> RequirementExcelInspectResponse:

    # 1. Scan for departmental worksheets across the workbook
    dept_preview_rows: list[dict[str, Any]] = []
    dept_sheet_titles: set[str] = set()
    for sheet in wb.worksheets:
        if getattr(sheet, "sheet_type", "worksheet") == "chartsheet":
            continue
        dk = _match_department_tab(sheet.title)
        if dk:
            dept_sheet_titles.add(sheet.title)
            dept_preview_rows.extend(_parse_departmental_sheet(sheet, dk, month, year))

    # 2. Pick candidate component worksheet (skip chartsheets, empty sheets, and matched departmental sheets)
    ws = None
    for sheet in wb.worksheets:
        if getattr(sheet, "sheet_type", "worksheet") == "chartsheet":
            continue
        if sheet.title in dept_sheet_titles:
            continue
        if sheet.max_row and sheet.max_row > 1:
            ws = sheet
            break

    if ws is None:
        if dept_preview_rows:
            # Standalone departmental workbook with no separate component sheet
            existing_plan = session.scalar(
                select(PlanningVersion)
                .where(PlanningVersion.planning_period == planning_period)
                .limit(1)
            ) if session else None

            return RequirementExcelInspectResponse(
                filename=filename,
                total_rows=len(dept_preview_rows),
                valid_rows=len([r for r in dept_preview_rows if r.get("is_valid", True)]),
                error_count=0,
                planning_month=month,
                planning_year=year,
                planning_period=planning_period,
                plan_already_exists=existing_plan is not None,
                errors=[],
                preview_rows=dept_preview_rows,
            )
        ws = wb.active

    if not ws:
        raise ApplicationError("EMPTY_WORKBOOK", "The Excel workbook has no usable worksheets.", 400)

    # Column mapping aliases (matched against normalized lowercase strings)
    ALIAS_MAP = {
        "part_name": [
            "used for part name",
            "used for part",
            "used for",
            "part name",
            "component name",
            "product name",
        ],
        "part_number": [
            "used part no production order",
            "used part no",
            "used part number",
            "part no",
            "part number",
            "production order",
            "product code",
        ],
        "consumable_code": [
            "consumable item id",
            "consumable item code",
            "consumable code",
            "item id",
            "item code",
            "consumable id",
        ],
        "consumable_name": [
            "consumable name",
            "description",
            "item description",
            "material name",
            "consumable description",
        ],
        "process_name": [
            "process name",
            "process",
            "operation",
            "operation name",
        ],
        "part_thickness": [
            "part thickness mm",
            "part thickness",
            "thickness mm",
            "thickness",
            "thk",
        ],
        "process_count": [
            "number of processes",
            "number of process",
            "no of processes",
            "process count",
            "processes",
        ],
        "production_order_qty": [
            "production order for selected month",
            "production order qty",
            "production order quantity",
            "production order",
            "monthly production order",
            "planned quantity",
            "planned qty",
            "production qty",
        ],
        "scheduled_consumable_qty": [
            "scheduled consumable quantity for selected month",
            "scheduled consumable qty",
            "scheduled quantity",
            "scheduled qty",
            "required qty",
            "calculated qty",
        ],
    }

    # Locate the header row (search rows 1 to 5)
    header_row_idx = None
    col_mapping: dict[str, int] = {}  # field_name -> 0-indexed column

    for r_idx in range(1, min(6, ws.max_row + 1)):
        row_vals = [_normalize_header(cell.value) for cell in ws[r_idx]]
        # Pass 1: exact matches
        matches: dict[str, int] = {}
        for c_idx, val in enumerate(row_vals):
            if not val:
                continue
            for field, aliases in ALIAS_MAP.items():
                if field in matches:
                    continue
                if any(alias == val for alias in aliases):
                    matches[field] = c_idx

        # Pass 2: substring matches for remaining fields
        for c_idx, val in enumerate(row_vals):
            if not val:
                continue
            for field, aliases in ALIAS_MAP.items():
                if field in matches:
                    continue
                if any(alias in val for alias in aliases if len(alias) >= 10):
                    matches[field] = c_idx

        # If we matched at least 2 distinct primary columns, consider this the header row
        if len(matches) >= 3 or ("part_name" in matches and "consumable_code" in matches):
            header_row_idx = r_idx
            col_mapping = matches
            break

    errors: list[RequirementRowError] = []
    if not header_row_idx:
        # Check row 1 directly as fallback with exact then substring
        row_vals = [_normalize_header(cell.value) for cell in ws[1]]
        for c_idx, val in enumerate(row_vals):
            for field, aliases in ALIAS_MAP.items():
                if field not in col_mapping and any(alias == val for alias in aliases):
                    col_mapping[field] = c_idx
        for c_idx, val in enumerate(row_vals):
            for field, aliases in ALIAS_MAP.items():
                if field not in col_mapping and any(alias in val for alias in aliases if len(alias) >= 10):
                    col_mapping[field] = c_idx
        header_row_idx = 1

    # Validate essential headers (exempt if departmental rows already captured or sheet is standalone departmental indent)
    has_comp_headers = ("part_name" in col_mapping or "part_number" in col_mapping) and ("production_order_qty" in col_mapping)
    if not has_comp_headers:
        if dept_preview_rows:
            # Component headers missing on this sheet, but valid departmental sheets exist: ignore component errors
            pass
        elif ("consumable_code" in col_mapping or "consumable_name" in col_mapping):
            # Standalone sheet in departmental indent format
            dk_fallback = _match_department_tab(ws.title) or "TOOL_ROOM"
            dept_parsed = _parse_departmental_sheet(ws, dk_fallback, month, year)
            if dept_parsed:
                dept_preview_rows.extend(dept_parsed)
        else:
            if "part_name" not in col_mapping and "part_number" not in col_mapping:
                errors.append(
                    RequirementRowError(
                        row_number=header_row_idx,
                        column_name="Used For – Part Name / Part Number",
                        error_description="Missing component header ('Used For – Part Name' or 'Used Part No.')",
                    )
                )
            if "consumable_code" not in col_mapping and "consumable_name" not in col_mapping:
                errors.append(
                    RequirementRowError(
                        row_number=header_row_idx,
                        column_name="Consumable Item ID / Name",
                        error_description="Missing consumable header ('Consumable Item ID' or 'Consumable Name')",
                    )
                )
            if "production_order_qty" not in col_mapping:
                errors.append(
                    RequirementRowError(
                        row_number=header_row_idx,
                        column_name="Production Order for Selected Month",
                        error_description="Missing production order quantity header ('Production Order for Selected Month')",
                    )
                )

    # Read and validate rows
    preview_rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    total_data_rows = 0
    valid_data_rows = 0

    for r_idx in range(header_row_idx + 1, ws.max_row + 1):
        raw_row = [cell.value for cell in ws[r_idx]]
        if not any(v is not None and str(v).strip() != "" for v in raw_row):
            continue  # skip completely blank rows

        total_data_rows += 1
        row_errors: list[str] = []

        def get_val(field: str, default: Any = "") -> Any:
            c = col_mapping.get(field)
            if c is not None and c < len(raw_row):
                val = raw_row[c]
                return val if val is not None else default
            return default

        p_name = str(get_val("part_name", "")).strip()
        p_num = str(get_val("part_number", "")).strip()
        c_code = str(get_val("consumable_code", "")).strip()
        c_name = str(get_val("consumable_name", "")).strip()
        proc_name = str(get_val("process_name", "")).strip() or "Standard Process"
        raw_thick = get_val("part_thickness", 0)
        raw_proc_count = get_val("process_count", 1)
        raw_prod_qty = get_val("production_order_qty", 0)
        raw_sched_qty = get_val("scheduled_consumable_qty", 0)

        # 1. Component validation
        if not p_name and not p_num:
            row_errors.append("Both Part Name and Part Number are empty.")
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Used For – Part Name",
                    error_description="Part Name or Part Number is required.",
                )
            )
        if not p_name:
            p_name = p_num
        if not p_num:
            p_num = p_name

        # 2. Consumable validation
        if not c_code and not c_name:
            row_errors.append("Both Consumable ID and Consumable Name are empty.")
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Consumable Item ID",
                    error_description="Consumable Item ID or Consumable Name is required.",
                )
            )
        if not c_code:
            c_code = c_name
        if not c_name:
            c_name = c_code

        # 3. Production Order Qty validation
        try:
            prod_qty_dec = Decimal(str(raw_prod_qty).replace(",", "").strip() or "0")
            if prod_qty_dec <= Decimal("0"):
                row_errors.append("Production Order quantity must be greater than zero.")
                errors.append(
                    RequirementRowError(
                        row_number=r_idx,
                        column_name="Production Order for Selected Month",
                        error_description=f"Quantity must be positive (got '{raw_prod_qty}').",
                    )
                )
        except (InvalidOperation, ValueError):
            prod_qty_dec = Decimal("0")
            row_errors.append(f"Invalid numeric value '{raw_prod_qty}' for Production Order quantity.")
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Production Order for Selected Month",
                    error_description=f"Cannot parse '{raw_prod_qty}' as a number.",
                )
            )

        # 4. Thickness validation
        try:
            thick_dec = Decimal(str(raw_thick).replace(",", "").strip() or "0")
            if thick_dec < Decimal("0"):
                row_errors.append("Part thickness cannot be negative.")
                errors.append(
                    RequirementRowError(
                        row_number=r_idx,
                        column_name="Part Thickness (mm)",
                        error_description="Thickness cannot be negative.",
                    )
                )
        except (InvalidOperation, ValueError):
            thick_dec = Decimal("0")
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Part Thickness (mm)",
                    error_description=f"Cannot parse thickness '{raw_thick}' as a number.",
                )
            )

        # 5. Process count validation
        try:
            p_count_int = int(Decimal(str(raw_proc_count).replace(",", "").strip() or "1"))
            if p_count_int < 1:
                row_errors.append("Process count must be at least 1.")
                errors.append(
                    RequirementRowError(
                        row_number=r_idx,
                        column_name="Number of Processes",
                        error_description="Number of Processes must be 1 or more.",
                    )
                )
        except (InvalidOperation, ValueError):
            p_count_int = 1
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Number of Processes",
                    error_description=f"Cannot parse '{raw_proc_count}' as an integer.",
                )
            )

        # 6. Scheduled quantity validation (optional)
        try:
            sched_qty_dec = Decimal(str(raw_sched_qty).replace(",", "").strip() or "0")
        except (InvalidOperation, ValueError):
            sched_qty_dec = Decimal("0")

        # 7. Duplicate row check
        dup_key = f"{p_num.upper()}:{c_code.upper()}:{proc_name.upper()}"
        if dup_key in seen_keys:
            errors.append(
                RequirementRowError(
                    row_number=r_idx,
                    column_name="Row Duplicate",
                    error_description=f"Duplicate entry for Part '{p_num}', Consumable '{c_code}', and Process '{proc_name}'.",
                )
            )
        else:
            seen_keys.add(dup_key)

        is_valid = len(row_errors) == 0
        if is_valid:
            valid_data_rows += 1

        preview_rows.append(
            {
                "row_index": r_idx,
                "part_name": p_name,
                "part_number": p_num,
                "consumable_code": c_code,
                "consumable_name": c_name,
                "process_name": proc_name,
                "part_thickness": format(thick_dec, ".4f"),
                "process_count": p_count_int,
                "production_order_qty": format(prod_qty_dec, ".4f"),
                "scheduled_consumable_qty": format(sched_qty_dec, ".4f"),
                "is_valid": is_valid,
                "errors": row_errors,
            }
        )

    # Check if plan already exists for this period
    existing_plan = session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .limit(1)
    ) if session else None

    # Combine component preview rows and departmental preview rows
    if dept_preview_rows:
        preview_rows = preview_rows + dept_preview_rows
        total_data_rows = len(preview_rows)
        valid_data_rows = len([r for r in preview_rows if r.get("is_valid", True)])
        if not has_comp_headers:
            errors = []

    return RequirementExcelInspectResponse(
        filename=filename,
        total_rows=total_data_rows,
        valid_rows=valid_data_rows,
        error_count=len(errors),
        planning_month=month,
        planning_year=year,
        planning_period=planning_period,
        plan_already_exists=existing_plan is not None,
        errors=errors,
        preview_rows=preview_rows,
    )


def import_monthly_requirements(
    session, current_user_id: UUID, req: RequirementImportRequest
) -> tuple[int, MonthlyPlanMetadata]:
    """Saves inspected monthly requirement records in a single transactional unit."""
    planning_period = f"{req.planning_year:04d}-{req.planning_month:02d}"

    # Check existing version
    existing_version = session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
        .with_for_update()
    )

    has_dept_records = any(
        is_department_unit(item.get("plant"))
        or is_department_unit(item.get("plant_id"))
        or item.get("rule_type") == "PLANT_REQUEST"
        or str(item.get("part_number", "")).strip() == "DEPARTMENT_INDENT"
        for item in req.records
    )
    has_prod_records = any(
        not (
            is_department_unit(item.get("plant"))
            or is_department_unit(item.get("plant_id"))
            or item.get("rule_type") == "PLANT_REQUEST"
            or str(item.get("part_number", "")).strip() == "DEPARTMENT_INDENT"
        )
        for item in req.records
    )

    from app.services import basic_planning
    is_central = bool(existing_version and basic_planning.is_central_version(session, existing_version.id))

    if existing_version and is_central and has_prod_records and not has_dept_records:
        raise ApplicationError('CENTRAL_PRODUCTION_PLAN',
            'This month uses production-based requirements. Update Production for sale or Consumption Norms, then recalculate; do not replace it with a separate requirement upload.', 409)

    # Departmental upload mode: merge without wiping production plants or store receipts
    if has_dept_records and (not has_prod_records or is_central):
        version = existing_version
        if not version:
            version = PlanningVersion(
                planning_period=planning_period,
                version_number=0,
                revision_label="R0",
                source_filename=req.source_filename,
                status="DRAFT",
                created_by=current_user_id,
                created_at=datetime.now(timezone.utc),
                updated_at=None,
                updated_by=None,
                planning_month=req.planning_month,
                planning_year=req.planning_year,
            )
            session.add(version)
            session.flush()

        target_depts = {
            str(item.get("plant", "")).strip() for item in req.records
            if is_department_unit(item.get("plant")) or is_department_unit(item.get("plant_id"))
        }
        target_plant_ids = {_normalize_plant_identifier(d) for d in target_depts if d}

        # Selectively soft-delete previous rows for ONLY the target uploaded departments
        if target_depts or target_plant_ids:
            session.query(MonthlyRequirementRecord).filter(
                MonthlyRequirementRecord.planning_period == planning_period,
                MonthlyRequirementRecord.is_deleted == False,
                or_(
                    MonthlyRequirementRecord.plant.in_(target_depts),
                    MonthlyRequirementRecord.plant_id.in_(target_plant_ids),
                ),
                or_(
                    MonthlyRequirementRecord.part_number == "DEPARTMENT_INDENT",
                    MonthlyRequirementRecord.process_name.in_(["DEPARTMENT_INDENT", "MAINTENANCE"]),
                ),
            ).update({"is_deleted": True}, synchronize_session=False)

    elif existing_version and not req.overwrite:
        raise ApplicationError(
            "PLAN_ALREADY_EXISTS",
            f"A monthly requirement plan already exists for {planning_period}. Please confirm to replace/update.",
            status_code=409,
        )
    elif existing_version and req.overwrite:
        new_version_num = existing_version.version_number + 1
        new_revision_label = f"R{new_version_num}"
        session.query(MonthlyRequirementRecord).filter(
            MonthlyRequirementRecord.planning_version_id == existing_version.id
        ).update({"is_deleted": True}, synchronize_session=False)

        version = PlanningVersion(
            planning_period=planning_period,
            version_number=new_version_num,
            revision_label=new_revision_label,
            source_filename=req.source_filename,
            status="DRAFT",
            created_by=existing_version.created_by,
            created_at=existing_version.created_at,
            updated_at=datetime.now(timezone.utc),
            updated_by=current_user_id,
            planning_month=req.planning_month,
            planning_year=req.planning_year,
        )
        session.add(version)
        session.flush()
    else:
        version = PlanningVersion(
            planning_period=planning_period,
            version_number=0,
            revision_label="R0",
            source_filename=req.source_filename,
            status="DRAFT",
            created_by=current_user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            updated_by=None,
            planning_month=req.planning_month,
            planning_year=req.planning_year,
        )
        session.add(version)
        session.flush()

    ensure_operational_units(session)
    inserted_count = 0
    for idx, item in enumerate(req.records, start=1):
        p_name = str(item.get("part_name", "")).strip()
        p_num = str(item.get("part_number", "")).strip() or p_name
        c_code = str(item.get("consumable_code", "")).strip()
        c_name = str(item.get("consumable_name", "")).strip() or c_code
        proc_name = str(item.get("process_name", "Standard Process")).strip()

        try:
            prod_qty = Decimal(str(item.get("production_order_qty", "0")).replace(",", ""))
        except Exception:
            prod_qty = Decimal("0")

        try:
            sched_qty = Decimal(str(item.get("scheduled_consumable_qty", "0")).replace(",", ""))
        except Exception:
            sched_qty = Decimal("0")

        try:
            thk = Decimal(str(item.get("part_thickness", "0")).replace(",", ""))
        except Exception:
            thk = Decimal("0")

        try:
            p_cnt = int(str(item.get("process_count", "1")))
        except Exception:
            p_cnt = 1

        plant_str = str(item.get("plant", "Plant 1")).strip()
        plant_id_val = _normalize_plant_identifier(plant_str)
        is_dept = is_department_unit(plant_str) or is_department_unit(plant_id_val) or item.get("rule_type") == "PLANT_REQUEST" or p_num == "DEPARTMENT_INDENT"

        status_val = "CALCULATED" if is_dept else "DRAFT"
        remarks_val = item.get("remarks") or (f"Departmental indent: {plant_str}" if is_dept else None)

        gross_req_val = sched_qty
        if "gross_requirement" in item and item["gross_requirement"] is not None:
            try:
                gross_req_val = Decimal(str(item["gross_requirement"]).replace(",", ""))
            except Exception:
                gross_req_val = sched_qty

        rec = MonthlyRequirementRecord(
            planning_version_id=version.id,
            planning_period=planning_period,
            planning_month=req.planning_month,
            planning_year=req.planning_year,
            row_index=idx,
            part_name=p_name,
            part_number=p_num,
            consumable_code=c_code,
            consumable_name=c_name,
            process_name=proc_name,
            part_thickness=thk,
            process_count=p_cnt,
            production_order_qty=prod_qty,
            scheduled_consumable_qty=sched_qty,
            gross_requirement=gross_req_val,
            unit=str(item.get("unit", "NOS")),
            plant=plant_str,
            plant_id=plant_id_val,
            status=status_val,
            remarks=remarks_val,
            created_by=current_user_id,
        )
        session.add(rec)
        inserted_count += 1

    # Record Audit Log
    session.add(
        AuditLog(
            actor_id=current_user_id,
            action="IMPORT",
            entity_type="planning_versions",
            entity_id=version.id,
            old_values=None,
            new_values={
                "planning_period": planning_period,
                "filename": req.source_filename,
                "inserted_count": inserted_count,
                "revision": version.revision_label,
            },
            reason="Imported monthly consumable requirement records from Excel",
        )
    )

    session.commit()
    meta = get_monthly_plan_metadata(session, req.planning_month, req.planning_year)
    return inserted_count, meta


def create_departmental_row(
    session, current_user_id: UUID, data: DepartmentalRowCreateRequest
) -> RequirementWorkspaceRecord:
    """Creates or updates a departmental consumable indent record."""
    dept_key = _match_department_tab(data.plant) or _normalize_plant_identifier(data.plant)
    dept_display = DEPARTMENT_DISPLAY_NAMES.get(dept_key, data.plant)
    proc_name = "MAINTENANCE" if dept_key == "PMD" else "DEPARTMENT_INDENT"
    planning_period = f"{data.year:04d}-{data.month:02d}"

    plan_ver = session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
        .limit(1)
    )
    if not plan_ver:
        plan_ver = PlanningVersion(
            planning_month=data.month,
            planning_year=data.year,
            planning_period=planning_period,
            version_number=1,
            status="DRAFT",
            revision_label="R0",
            source_filename=f"manual_indent_{planning_period}.xlsx",
            created_by=current_user_id,
        )
        session.add(plan_ver)
        session.flush()

    code_upper = data.consumable_code.strip().upper()
    existing = session.scalar(
        select(MonthlyRequirementRecord).where(
            MonthlyRequirementRecord.planning_period == planning_period,
            func.upper(MonthlyRequirementRecord.plant) == dept_display.upper(),
            func.upper(MonthlyRequirementRecord.consumable_code) == code_upper,
            MonthlyRequirementRecord.is_deleted == False,
        ).limit(1)
    )

    qty = data.scheduled_consumable_qty
    now = datetime.now(timezone.utc)
    if existing:
        existing.scheduled_consumable_qty = qty
        existing.gross_requirement = qty
        if data.part_number:
            existing.part_number = data.part_number
        if data.unit:
            existing.unit = data.unit
        if data.remarks:
            existing.remarks = data.remarks
        existing.updated_at = now
        rec = existing
    else:
        rec = MonthlyRequirementRecord(
            planning_version_id=plan_ver.id,
            planning_period=planning_period,
            planning_month=data.month,
            planning_year=data.year,
            plant=dept_display,
            part_name=dept_display,
            part_number=data.part_number or "DEPARTMENT_INDENT",
            consumable_code=code_upper,
            consumable_name=data.consumable_name.strip(),
            process_name=proc_name,
            unit=data.unit or "NOS",
            part_thickness=Decimal("0.0000"),
            process_count=1,
            production_order_qty=Decimal("0.0000"),
            scheduled_consumable_qty=qty,
            gross_requirement=qty,
            stock_qty=Decimal("0.0000"),
            shortage_qty=qty,
            po_pending_qty=Decimal("0.0000"),
            msl=Decimal("0.0000"),
            status="Normal",
            remarks=data.remarks or f"Departmental indent: {dept_display}",
            is_deleted=False,
            created_by=current_user_id,
            created_at=now,
            updated_at=now,
        )
        session.add(rec)
        session.flush()

    # Calculate rolling average for this item
    hist_records = session.scalars(
        select(MonthlyRequirementRecord).where(
            func.upper(MonthlyRequirementRecord.plant) == dept_display.upper(),
            func.upper(MonthlyRequirementRecord.consumable_code) == code_upper,
            MonthlyRequirementRecord.is_deleted == False,
        )
    ).all()
    avg_qty, active_count = compute_non_zero_rolling_average(hist_records, data.month, data.year)

    session.commit()

    doc_ref_val = rec.part_number if rec.part_number != "DEPARTMENT_INDENT" else None
    return RequirementWorkspaceRecord(
        id=str(rec.id),
        plan_id=str(plan_ver.id),
        planning_period=rec.planning_period,
        planning_month=rec.planning_month,
        planning_year=rec.planning_year,
        revision=plan_ver.revision_label,
        part_name=rec.part_name,
        part_number=rec.part_number,
        consumable_code=rec.consumable_code,
        consumable_name=rec.consumable_name,
        process_name=rec.process_name,
        part_thickness="0.0000",
        process_count=1,
        production_order_qty="0.0000",
        scheduled_consumable_qty=format(rec.scheduled_consumable_qty, ".4f"),
        plant=rec.plant,
        process=rec.process_name,
        description=rec.consumable_name,
        unit=rec.unit,
        rule_type="PLANT_REQUEST",
        required_qty=format(rec.scheduled_consumable_qty, ".4f"),
        stock_qty=format(rec.stock_qty, ".4f"),
        shortage_qty=format(rec.shortage_qty, ".4f"),
        po_pending_qty=format(rec.po_pending_qty, ".4f"),
        msl=format(rec.msl, ".4f"),
        status=rec.status,
        remarks=rec.remarks,
        historical_avg_qty=format(avg_qty, ".4f"),
        active_month_count=active_count,
        doc_ref=doc_ref_val,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def batch_update_requirements(
    session, current_user_id: UUID, req: RequirementBatchUpdateRequest
) -> RequirementBatchUpdateResponse:
    """Updates permitted spreadsheet fields in a single database transaction."""
    if not req.records:
        raise ApplicationError("EMPTY_UPDATE", "No records provided for update.", 400)

    updated_count = 0
    affected_version_ids = set()
    sample_version = None

    for item in req.records:
        rec = None
        is_auto = str(item.id).startswith("auto-")
        if not is_auto:
            try:
                rec = session.get(MonthlyRequirementRecord, UUID(str(item.id)))
            except (ValueError, TypeError):
                rec = None

        if is_auto or (not rec and (item.plant or item.month)):
            parts = str(item.id).split("-", 2)
            plant_name = item.plant or (parts[1] if len(parts) > 1 else "PMD")
            code_val = (item.consumable_code or (parts[2] if len(parts) > 2 else "")).strip().upper()
            month_val = item.month or (sample_version.planning_month if sample_version else 10)
            year_val = item.year or (sample_version.planning_year if sample_version else 2026)
            period_str = f"{year_val:04d}-{month_val:02d}"

            plan_ver = session.scalar(
                select(PlanningVersion).where(PlanningVersion.planning_period == period_str)
                .order_by(PlanningVersion.version_number.desc()).limit(1)
            )
            if not plan_ver:
                plan_ver = PlanningVersion(
                    planning_month=month_val,
                    planning_year=year_val,
                    planning_period=period_str,
                    version_number=1,
                    status="DRAFT",
                    revision_label="R0",
                    source_filename=f"manual_indent_{period_str}.xlsx",
                    created_by=current_user_id,
                )
                session.add(plan_ver)
                session.flush()

            rec = session.scalar(
                select(MonthlyRequirementRecord).where(
                    MonthlyRequirementRecord.planning_period == period_str,
                    func.upper(MonthlyRequirementRecord.plant) == plant_name.upper(),
                    func.upper(MonthlyRequirementRecord.consumable_code) == code_val,
                    MonthlyRequirementRecord.is_deleted == False,
                ).limit(1)
            )
            if not rec:
                proc_name = "MAINTENANCE" if _normalize_plant_identifier(plant_name) == "PMD" else "DEPARTMENT_INDENT"
                rec = MonthlyRequirementRecord(
                    planning_version_id=plan_ver.id,
                    planning_period=period_str,
                    planning_month=month_val,
                    planning_year=year_val,
                    plant=plant_name,
                    part_name=plant_name,
                    part_number=item.part_number or "DEPARTMENT_INDENT",
                    consumable_code=code_val,
                    consumable_name=item.consumable_name or code_val,
                    process_name=proc_name,
                    unit=item.unit or "NOS",
                    scheduled_consumable_qty=Decimal("0.0000"),
                    gross_requirement=Decimal("0.0000"),
                    stock_qty=Decimal("0.0000"),
                    shortage_qty=Decimal("0.0000"),
                    po_pending_qty=Decimal("0.0000"),
                    msl=Decimal("0.0000"),
                    status="Normal",
                    remarks=item.remarks or f"Departmental indent: {plant_name}",
                    is_deleted=False,
                    created_by=current_user_id,
                )
                session.add(rec)
                session.flush()

        if not rec or rec.is_deleted:
            continue

        if item.scheduled_consumable_qty is not None:
            try:
                rec.scheduled_consumable_qty = Decimal(str(item.scheduled_consumable_qty).replace(",", ""))
                if item.gross_requirement is None:
                    rec.gross_requirement = rec.scheduled_consumable_qty
            except Exception:
                pass

        if item.gross_requirement is not None:
            try:
                rec.gross_requirement = Decimal(str(item.gross_requirement).replace(",", ""))
            except Exception:
                pass

        if item.production_order_qty is not None:
            try:
                rec.production_order_qty = Decimal(str(item.production_order_qty).replace(",", ""))
            except Exception:
                pass

        if item.part_thickness is not None:
            try:
                rec.part_thickness = Decimal(str(item.part_thickness).replace(",", ""))
            except Exception:
                pass

        if item.process_count is not None:
            rec.process_count = int(item.process_count)

        if item.remarks is not None:
            rec.remarks = item.remarks

        if item.consumable_code is not None:
            rec.consumable_code = item.consumable_code.strip().upper()
        if item.consumable_name is not None:
            rec.consumable_name = item.consumable_name.strip()
        if item.unit is not None:
            rec.unit = item.unit.strip()
        if item.part_number is not None:
            rec.part_number = item.part_number.strip()

        cls = (rec.opening_stock or Decimal("0")) + (rec.grn_received_qty or Decimal("0")) - (rec.consumed_qty or Decimal("0"))
        rec.closing_stock = cls
        gross = rec.gross_requirement or rec.scheduled_consumable_qty or Decimal("0")
        msl_val = rec.msl or Decimal("0")
        rec.shortage_qty = max(Decimal("0.0000"), (gross + msl_val) - cls)
        rec.net_order_requirement = rec.shortage_qty
        if is_department_unit(rec.plant):
            if rec.shortage_qty > Decimal("0"):
                rec.status = "Critical shortage" if cls <= Decimal("0") else "Low"
            else:
                rec.status = "Normal"

        rec.updated_at = datetime.now(timezone.utc)
        if rec.planning_version_id:
            affected_version_ids.add(rec.planning_version_id)
        updated_count += 1

    now = datetime.now(timezone.utc)
    for v_id in affected_version_ids:
        v = session.get(PlanningVersion, v_id)
        if v:
            v.updated_at = now
            v.updated_by = current_user_id
            sample_version = v

    if sample_version:
        session.add(
            AuditLog(
                actor_id=current_user_id,
                action="UPDATE",
                entity_type="planning_versions",
                entity_id=sample_version.id,
                old_values=None,
                new_values={"updated_count": updated_count},
                reason="Batch updated spreadsheet fields in monthly requirements",
            )
        )

    session.commit()

    # Retrieve fresh metadata and records
    month = sample_version.planning_month if sample_version and sample_version.planning_month else None
    year = sample_version.planning_year if sample_version and sample_version.planning_year else None
    period = sample_version.planning_period if sample_version else None

    refreshed_records = calculate_workspace_requirements(session, month=month, year=year, planning_period=period)
    meta = get_monthly_plan_metadata(session, month or 1, year or 2026) if month and year else MonthlyPlanMetadata()

    return RequirementBatchUpdateResponse(
        message=f"Successfully updated {updated_count} record(s).",
        updated_count=updated_count,
        records=refreshed_records,
        plan_metadata=meta,
    )


def delete_requirement_record(
    session, record_id: UUID, current_user_id: UUID, reason: Optional[str] = None
) -> None:
    rec = session.get(MonthlyRequirementRecord, record_id)
    if not rec or rec.is_deleted:
        raise ApplicationError("RECORD_NOT_FOUND", "Requirement record not found.", 404)

    rec.is_deleted = True
    now = datetime.now(timezone.utc)
    rec.updated_at = now

    if rec.planning_version_id:
        v = session.get(PlanningVersion, rec.planning_version_id)
        if v:
            v.updated_at = now
            v.updated_by = current_user_id

    session.add(
        AuditLog(
            actor_id=current_user_id,
            action="DELETE",
            entity_type="monthly_requirement_records",
            entity_id=record_id,
            old_values={"part_number": rec.part_number, "consumable_code": rec.consumable_code},
            new_values={"is_deleted": True},
            reason=reason or "Deleted single requirement record",
        )
    )
    session.commit()


def bulk_delete_requirement_records(
    session,
    record_ids: list[Any],
    current_user_id: UUID,
    reason: Optional[str] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> tuple[int, Optional[MonthlyPlanMetadata]]:
    if not record_ids:
        return 0, None

    deleted_count = 0
    affected_version_ids = set()
    sample_version = None
    now = datetime.now(timezone.utc)

    for r_id in record_ids:
        r_str = str(r_id)
        if r_str.startswith("auto-"):
            parts = r_str.split("-", 2)
            plant_name = parts[1] if len(parts) > 1 else "PMD"
            code_val = (parts[2] if len(parts) > 2 else "").strip().upper()
            m = month or 10
            y = year or 2026
            period_str = f"{y:04d}-{m:02d}"

            plan_ver = session.scalar(
                select(PlanningVersion).where(PlanningVersion.planning_period == period_str)
                .order_by(PlanningVersion.version_number.desc()).limit(1)
            )
            if not plan_ver:
                plan_ver = PlanningVersion(
                    planning_month=m,
                    planning_year=y,
                    planning_period=period_str,
                    version_number=1,
                    status="DRAFT",
                    revision_label="R0",
                    source_filename=f"manual_indent_{period_str}.xlsx",
                    created_by=current_user_id,
                )
                session.add(plan_ver)
                session.flush()

            rec = MonthlyRequirementRecord(
                planning_version_id=plan_ver.id,
                planning_period=period_str,
                planning_month=m,
                planning_year=y,
                plant=plant_name,
                part_name=plant_name,
                part_number="DEPARTMENT_INDENT",
                consumable_code=code_val,
                consumable_name=code_val,
                scheduled_consumable_qty=Decimal("0.0000"),
                gross_requirement=Decimal("0.0000"),
                stock_qty=Decimal("0.0000"),
                shortage_qty=Decimal("0.0000"),
                po_pending_qty=Decimal("0.0000"),
                msl=Decimal("0.0000"),
                status="Normal",
                remarks=f"Deleted departmental row: {code_val}",
                is_deleted=True,
                created_by=current_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(rec)
            deleted_count += 1
            affected_version_ids.add(plan_ver.id)
            sample_version = plan_ver
            continue

        try:
            uuid_id = UUID(r_str)
            rec = session.get(MonthlyRequirementRecord, uuid_id)
            if not rec or rec.is_deleted:
                continue
            rec.is_deleted = True
            rec.updated_at = now
            if rec.planning_version_id:
                affected_version_ids.add(rec.planning_version_id)
            deleted_count += 1
        except (ValueError, TypeError):
            continue

    for v_id in affected_version_ids:
        v = session.get(PlanningVersion, v_id)
        if v:
            v.updated_at = now
            v.updated_by = current_user_id
            sample_version = v

    if sample_version:
        session.add(
            AuditLog(
                actor_id=current_user_id,
                action="BULK_DELETE",
                entity_type="planning_versions",
                entity_id=sample_version.id,
                old_values=None,
                new_values={"deleted_count": deleted_count},
                reason=reason or f"Bulk deleted {deleted_count} requirement records",
            )
        )

    session.commit()

    meta = None
    if sample_version and sample_version.planning_month and sample_version.planning_year:
        meta = get_monthly_plan_metadata(session, sample_version.planning_month, sample_version.planning_year)
    elif month and year:
        meta = get_monthly_plan_metadata(session, month, year)

    return deleted_count, meta


def recalculate_monthly_requirements(
    session, current_user_id: UUID, month: int, year: int
) -> RequirementRecalculateResponse:
    """Deterministically recalculates consumable requirements using approved formulas."""
    planning_period = f"{year:04d}-{month:02d}"

    version = session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
        .with_for_update()
    )

    if not version:
        raise ApplicationError(
            "PLAN_NOT_FOUND",
            f"No monthly requirement plan exists for {planning_period}. Please upload an Excel sheet first.",
            404,
        )

    from app.services import basic_planning
    if basic_planning.is_central_version(session, version.id):
        from datetime import date
        from app.schemas.requirements import CalculationRunRequest
        result = basic_planning.calculate(session, CalculationRunRequest(planning_version_id=version.id, as_of_date=date(year, month, 1)), current_user_id)

        # Also recalculate departmental records in MonthlyRequirementRecord for this period
        dept_records = session.scalars(
            select(MonthlyRequirementRecord).where(
                MonthlyRequirementRecord.planning_period == planning_period,
                MonthlyRequirementRecord.is_deleted == False,
            )
        ).all()
        t2_m, t2_y = get_t_minus_2_period(month, year)
        t2_b_id = session.scalar(
            select(StockStatementBatch.id).where(
                StockStatementBatch.statement_month == t2_m,
                StockStatementBatch.statement_year == t2_y,
                StockStatementBatch.status == "active",
            ).limit(1)
        )
        t2_stock: dict[str, Decimal] = {}
        if t2_b_id:
            for i_id, c_qty in session.execute(
                select(StockStatementLine.item_id, StockStatementLine.closing_qty).where(
                    StockStatementLine.batch_id == t2_b_id,
                    StockStatementLine.item_class == "CONSUMABLE",
                )
            ).all():
                if i_id:
                    t2_stock[i_id.strip().upper()] = c_qty or Decimal("0.0")

        for rec in dept_records:
            is_dept = (
                is_department_unit(rec.plant)
                or is_department_unit(rec.plant_id)
                or rec.part_number == "DEPARTMENT_INDENT"
                or rec.process_name in ("DEPARTMENT_INDENT", "MAINTENANCE")
            )
            if is_dept:
                code_u = rec.consumable_code.strip().upper() if rec.consumable_code else ""
                if code_u in t2_stock:
                    rec.opening_stock = t2_stock[code_u]
                rec.closing_stock = (rec.opening_stock + rec.grn_received_qty) - rec.consumed_qty
                rec.gross_requirement = rec.scheduled_consumable_qty or Decimal("0.0")
                rec.net_order_requirement = max(Decimal("0.0000"), (rec.gross_requirement + rec.msl) - rec.closing_stock)
                rec.shortage_qty = rec.net_order_requirement
                rec.stock_qty = rec.closing_stock
                if rec.net_order_requirement > Decimal("0"):
                    rec.status = "Critical shortage" if rec.closing_stock <= Decimal("0") else "Low"
                else:
                    rec.status = "Normal"
                rec.remarks = f"Departmental indent: {rec.plant or 'Department'}"
                rec.updated_at = datetime.now(timezone.utc)

        records = calculate_workspace_requirements(session, month=month, year=year)
        crit_count = sum(1 for r in records if r.status == "Critical shortage")
        low_count = sum(1 for r in records if r.status == "Low")
        return RequirementRecalculateResponse(
            message=f"Production-based requirements updated: {result.successful_requirements_count} lines; {result.error_count} configuration issues.",
            record_count=len(records), critical_shortages=crit_count, low_stock=low_count, records=records,
            plan_metadata=get_monthly_plan_metadata(session, month, year))

    records = session.scalars(
        select(MonthlyRequirementRecord).where(
            MonthlyRequirementRecord.planning_version_id == version.id,
            MonthlyRequirementRecord.is_deleted == False,  # noqa: E712
        )
    ).all()

    if not records:
        raise ApplicationError(
            "NO_RECORDS_TO_CALCULATE",
            f"No records found in plan for {planning_period}.",
            400,
        )

    # Deterministic calculation using approved rules
    critical_count = 0
    low_count = 0

    for rec in records:
        is_dept = (
            is_department_unit(rec.plant)
            or is_department_unit(rec.plant_id)
            or rec.part_number == "DEPARTMENT_INDENT"
            or rec.process_name in ("DEPARTMENT_INDENT", "MAINTENANCE")
        )
        if is_dept:
            rec.gross_requirement = rec.scheduled_consumable_qty
            rec.status = "CALCULATED"
            rec.remarks = f"Departmental indent: {rec.plant or 'Department'}"
            shortage = max(Decimal("0"), rec.scheduled_consumable_qty - (rec.stock_qty + rec.po_pending_qty))
            rec.shortage_qty = shortage
            if shortage > Decimal("0"):
                if rec.stock_qty <= Decimal("0"):
                    rec.status = "Critical shortage"
                    critical_count += 1
                else:
                    rec.status = "Low"
                    low_count += 1
            rec.updated_at = datetime.now(timezone.utc)
            continue

        # Find approved consumption norm by consumable_code
        norm = session.scalar(
            select(ConsumptionNorm)
            .join(Consumable, ConsumptionNorm.consumable_id == Consumable.id)
            .where(
                func.upper(Consumable.code) == rec.consumable_code.strip().upper(),
                ConsumptionNorm.is_active == True,  # noqa: E712
            )
            .limit(1)
        )

        if norm:
            rule_type = RuleType(norm.rule_type)
            params = dict(norm.parameters)

            if rule_type == RuleType.PRODUCTION_RATE:
                if "rate" not in params and "usage_rate" in params:
                    params["rate"] = params["usage_rate"]
                elif "rate" not in params and "consumption_rate" in params:
                    params["rate"] = params["consumption_rate"]
            elif rule_type == RuleType.AREA_COVERAGE:
                if "coverage" not in params and "coverage_sqft_per_unit" in params:
                    params["coverage"] = params["coverage_sqft_per_unit"]
                if "area_per_unit" not in params and "area_per_unit_sqft" in params:
                    params["area_per_unit"] = params["area_per_unit_sqft"]
            elif rule_type == RuleType.TOOL_LIFE:
                if "tool_life" not in params and "tool_life_strokes" in params:
                    params["tool_life"] = params["tool_life_strokes"]
                params.setdefault("number_of_operations", Decimal(str(rec.process_count or 1)))

            # Injected variables for formulas requiring thickness or process count
            if rec.part_thickness and rec.part_thickness > Decimal("0"):
                params.setdefault("thickness", float(rec.part_thickness))
            if rec.process_count and rec.process_count > 1:
                params.setdefault("processes", rec.process_count)

            rule_input = RuleCalculationInput(
                rule_type=rule_type,
                rule_version=norm.version,
                production_quantity=rec.production_order_qty,
                parameters=params,
                rounding_policy=RoundingPolicy.parse(norm.rounding_policy),
                rounding_precision=norm.rounding_precision,
                unit=rec.unit,
            )

            try:
                calc_res = evaluate_rule(rule_input)
                rec.scheduled_consumable_qty = calc_res.final_calculated_requirement
                rec.status = "Calculated"
                rec.remarks = f"Calculated: {rule_type.value}"
            except (RuleDomainError, Exception) as e:
                rec.status = "Configuration required"
                rec.remarks = f"Calculation error: {str(e)}"
        else:
            # Fallback: if no explicit norm configured in consumption_norms, flag for review
            rec.status = "Configuration required"
            rec.remarks = f"No active Consumption Norm configured for '{rec.consumable_code}'"

        # Calculate shortage
        shortage = max(Decimal("0"), rec.scheduled_consumable_qty - (rec.stock_qty + rec.po_pending_qty))
        rec.shortage_qty = shortage
        if shortage > Decimal("0"):
            if rec.stock_qty <= Decimal("0"):
                rec.status = "Critical shortage"
                critical_count += 1
            else:
                rec.status = "Low"
                low_count += 1

        rec.updated_at = datetime.now(timezone.utc)

    # Touch version status & modified timestamps
    now = datetime.now(timezone.utc)
    version.calculated_at = now
    version.status = "CALCULATED"
    version.updated_at = now
    version.updated_by = current_user_id

    # Record Audit Log
    session.add(
        AuditLog(
            actor_id=current_user_id,
            action="CALCULATE",
            entity_type="planning_versions",
            entity_id=version.id,
            old_values=None,
            new_values={
                "planning_period": planning_period,
                "recalculated_count": len(records),
                "critical_shortages": critical_count,
            },
            reason="Recalculated monthly requirements with deterministic rules",
        )
    )

    session.commit()

    refreshed = calculate_workspace_requirements(session, month=month, year=year)
    meta = get_monthly_plan_metadata(session, month, year)

    return RequirementRecalculateResponse(
        message=f"Recalculation complete for {planning_period}. Processed {len(records)} records.",
        record_count=len(records),
        critical_shortages=critical_count,
        low_stock=low_count,
        records=refreshed,
        plan_metadata=meta,
    )


def export_requirements_excel(
    session,
    month: Optional[int] = None,
    year: Optional[int] = None,
    planning_period: Optional[str] = None,
    plant_filter: Optional[str] = None,
    consumable_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    record_ids: Optional[list[str]] = None,
    scope: Optional[str] = None,
) -> bytes:
    records = calculate_workspace_requirements(
        session,
        month=month,
        year=year,
        planning_period=planning_period,
        plant_filter=plant_filter,
        consumable_filter=consumable_filter,
        status_filter=status_filter,
        search=search,
    )
    if record_ids:
        records = [r for r in records if r.id in record_ids]

    is_dept_scope = bool(scope and scope.strip().lower() == "departmental")
    if is_dept_scope:
        records = [r for r in records if is_department_unit(r.plant)]

    period_str = planning_period or (f"{year:04d}-{month:02d}" if month and year else "All Periods")
    month_name = calendar.month_name[month] if month and 1 <= month <= 12 else ""
    period_label = f"{month_name} {year}" if month_name and year else period_str

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Departmental Consumables" if is_dept_scope else "Consumable Requirements"

    # Color palette
    navy_fill = PatternFill(start_color="1B3A5C", end_color="1B3A5C", fill_type="solid")
    steel_fill = PatternFill(start_color="2E5B88", end_color="2E5B88", fill_type="solid")
    gray_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    title_font = Font(name="Calibri", size=14, bold=True, color="1B3A5C")
    meta_font = Font(name="Calibri", size=10, italic=True, color="475569")
    group_header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    col_header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    def to_num(val: Any) -> float:
        if val is None:
            return 0.0
        try:
            return float(str(val).replace(",", "").strip())
        except Exception:
            return 0.0

    group_row = 4
    col_row = 5
    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 18
    ws.row_dimensions[group_row].height = 22
    ws.row_dimensions[col_row].height = 24

    if is_dept_scope:
        # Row 1: Title
        ws.cell(row=1, column=1, value="KNL DEPARTMENTAL & MAINTENANCE CONSUMABLE REQUIREMENTS").font = title_font
        # Row 2: Metadata
        ws.cell(
            row=2,
            column=1,
            value=f"Planning Period: {period_label}  |  Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  |  Records: {len(records)}",
        ).font = meta_font

        # Row 4: Group Headers (13 cols total)
        # Col 1: #
        # Col 2-6: DEPARTMENT & ITEM DETAILS (Location/Dept, Item Id., Item Description, Part No., Unit)
        # Col 7-8: PLANNING & CONSUMPTION (Historical Avg, Required Qty)
        # Col 9-13: INVENTORY & OPERATIONAL STATUS (Stock Qty, GRN Received, Shortage Qty, Status, Remarks)
        ws.cell(row=group_row, column=1, value="")
        ws.merge_cells(start_row=group_row, start_column=2, end_row=group_row, end_column=6)
        ws.cell(row=group_row, column=2, value="DEPARTMENT & ITEM DETAILS").fill = navy_fill
        ws.cell(row=group_row, column=2).font = group_header_font
        ws.cell(row=group_row, column=2).alignment = Alignment(horizontal="center", vertical="center")

        ws.merge_cells(start_row=group_row, start_column=7, end_row=group_row, end_column=8)
        ws.cell(row=group_row, column=7, value="PLANNING & CONSUMPTION").fill = steel_fill
        ws.cell(row=group_row, column=7).font = group_header_font
        ws.cell(row=group_row, column=7).alignment = Alignment(horizontal="center", vertical="center")

        ws.merge_cells(start_row=group_row, start_column=9, end_row=group_row, end_column=13)
        ws.cell(row=group_row, column=9, value="INVENTORY & OPERATIONAL STATUS").fill = navy_fill
        ws.cell(row=group_row, column=9).font = group_header_font
        ws.cell(row=group_row, column=9).alignment = Alignment(horizontal="center", vertical="center")

        dept_headers = [
            "#",
            "Location/Dept",
            "Item Id.",
            "Item Description",
            "Part No.",
            "Unit",
            "Historical Avg (Active Mos)",
            f"Required Qty ({period_label})",
            "Stock Qty (T-2)",
            "GRN Received",
            "Shortage Qty",
            "Status",
            "Remarks",
        ]

        for col_num, h_text in enumerate(dept_headers, start=1):
            cell = ws.cell(row=col_row, column=col_num, value=h_text)
            cell.fill = navy_fill if col_num in (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13) else steel_fill
            cell.font = col_header_font
            cell.border = thin_border
            cell.alignment = Alignment(
                horizontal="center" if col_num in (1, 2, 6, 12) else "right" if col_num in (7, 8, 9, 10, 11) else "left",
                vertical="center",
                wrap_text=True,
            )

        for r_idx, row in enumerate(records, start=1):
            current_row = col_row + r_idx
            ws.row_dimensions[current_row].height = 20
            part_ref = getattr(row, "doc_ref", None) or getattr(row, "part_number", None) or ""
            if part_ref == "DEPARTMENT_INDENT":
                part_ref = ""

            row_data = [
                r_idx,
                row.plant,
                row.consumable_code,
                row.consumable_name,
                part_ref,
                row.unit,
                to_num(getattr(row, "historical_avg_qty", "0.0000")),
                to_num(row.scheduled_consumable_qty),
                to_num(row.stock_qty),
                to_num(getattr(row, "grn_received_qty", "0.0000")),
                to_num(row.shortage_qty),
                row.status,
                row.remarks or "",
            ]

            for col_num, val in enumerate(row_data, start=1):
                cell = ws.cell(row=current_row, column=col_num, value=val)
                cell.font = data_font
                cell.border = thin_border
                if col_num in (1, 2, 6, 12):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_num in (7, 8, 9, 10, 11):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.number_format = "#,##0.0000"
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

    else:
        # Standard Production Consumables Export (15 cols)
        ws.cell(row=1, column=1, value="KNL CONSUMABLE REQUIREMENTS PLANNING").font = title_font
        ws.cell(
            row=2,
            column=1,
            value=f"Planning Period: {period_label}  |  Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  |  Records: {len(records)}",
        ).font = meta_font

        ws.cell(row=group_row, column=1, value="")
        ws.merge_cells(start_row=group_row, start_column=2, end_row=group_row, end_column=3)
        ws.cell(row=group_row, column=2, value="FOR COMPONENT").fill = navy_fill
        ws.cell(row=group_row, column=2).font = group_header_font
        ws.cell(row=group_row, column=2).alignment = Alignment(horizontal="center", vertical="center")

        ws.merge_cells(start_row=group_row, start_column=4, end_row=group_row, end_column=10)
        ws.cell(row=group_row, column=4, value="FOR CONSUMABLES").fill = steel_fill
        ws.cell(row=group_row, column=4).font = group_header_font
        ws.cell(row=group_row, column=4).alignment = Alignment(horizontal="center", vertical="center")

        ws.merge_cells(start_row=group_row, start_column=11, end_row=group_row, end_column=15)
        ws.cell(row=group_row, column=11, value="INVENTORY & STATUS").fill = navy_fill
        ws.cell(row=group_row, column=11).font = group_header_font
        ws.cell(row=group_row, column=11).alignment = Alignment(horizontal="center", vertical="center")

        headers = [
            "#",
            "Used For – Part Name",
            "Used Part No. (Production Order)",
            "Consumable Item ID",
            "Consumable Name",
            "Process Name",
            "Part Thickness (mm)",
            "Number of Processes",
            "Production Order for Selected Month",
            "Scheduled Consumable Quantity for Selected Month",
            "Unit",
            "Stock Qty",
            "Shortage Qty",
            "Status",
            "Remarks",
        ]

        for col_num, h_text in enumerate(headers, start=1):
            cell = ws.cell(row=col_row, column=col_num, value=h_text)
            cell.fill = navy_fill if col_num in (1, 2, 3, 11, 12, 13, 14, 15) else steel_fill
            cell.font = col_header_font
            cell.border = thin_border
            cell.alignment = Alignment(
                horizontal="center" if col_num in (1, 8, 11, 14) else "right" if col_num in (7, 9, 10, 12, 13) else "left",
                vertical="center",
                wrap_text=True,
            )

        for r_idx, row in enumerate(records, start=1):
            current_row = col_row + r_idx
            ws.row_dimensions[current_row].height = 20

            row_data = [
                r_idx,
                row.part_name,
                row.part_number,
                row.consumable_code,
                row.consumable_name,
                row.process_name,
                to_num(row.part_thickness),
                row.process_count,
                to_num(row.production_order_qty),
                to_num(row.scheduled_consumable_qty),
                row.unit,
                to_num(row.stock_qty),
                to_num(row.shortage_qty),
                row.status,
                row.remarks or "",
            ]

            for col_num, val in enumerate(row_data, start=1):
                cell = ws.cell(row=current_row, column=col_num, value=val)
                cell.font = data_font
                cell.border = thin_border

                if col_num == 1:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_num in (7, 9, 10, 12, 13):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.number_format = "#,##0.0000"
                elif col_num in (8, 11, 14):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

    # Column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col if cell.row >= col_row)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _normalize_header_key(col_name: Any) -> str:
    if col_name is None:
        return ""
    return str(col_name).strip().lower().replace(" ", "_").replace("-", "_").replace(".", "_")


def _normalize_header_slug(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(val).lower())


ITEM_CODE_SLUGS = {
    "itemid", "itemcode", "partno", "partnumber", "consumableid",
    "consumablecode", "materialcode", "itemno", "item", "consumable", "material"
}

QTY_SLUGS = {
    "grnqty", "receivedqty", "acceptedqty", "billedqty", "qty",
    "receiptqty", "grnquantity", "receivedquantity", "quantity", "received", "accepted"
}

LANDED_RATE_SLUGS = {
    "landedcostrate", "landedrate", "landedcost", "landingrate",
    "totallandedcost", "landedprice", "totallandedrate"
}
BASE_RATE_SLUGS = {
    "rate", "unitrate", "unitprice", "basicrate", "grnrate", "price"
}
OTHER_RATE_SLUGS = {
    "cost", "unitcost", "itemrate"
}
RATE_SLUGS = LANDED_RATE_SLUGS | BASE_RATE_SLUGS | OTHER_RATE_SLUGS

GRN_NO_SLUGS = {
    "grnno", "grnnumber", "grnid", "docno", "documentno",
    "receiptno", "receiptnumber", "invoiceno", "invoicenum", "invoicenumber",
    "billno", "dcno", "challanno", "doc"
}

DATE_SLUGS = {
    "grndate", "date", "receiptdate", "docdate", "postingdate",
    "billdate", "invoicedate", "entrydate"
}

VENDOR_SLUGS = {
    "suppliername", "vendorname", "supplier", "vendor",
    "partyname", "party", "supplierid", "vendorid"
}

PLANT_SLUGS = {
    "plant", "plantid", "plantname", "location", "facility",
    "unitlocation", "works", "plantunit", "worklocation"
}

UOM_SLUGS = {
    "unit", "uom", "unitofmeasure", "outputunit"
}

CANCELLED_SLUGS = {
    "cancelled", "canceled", "iscancelled", "iscanceled"
}

DESC_SLUGS = {
    "description", "itemdescription", "itemname", "name", "materialname",
    "materialdescription", "partname", "partdescription", "itemdesc", "desc", "productdescription"
}


def _score_qty_slug(slug: str) -> int:
    if slug in ("grnqty", "receivedqty", "grnquantity", "receivedquantity", "receiptqty"):
        return 3
    if slug in ("acceptedqty", "accepted"):
        return 2
    return 1


def _score_rate_slug(slug: str) -> int:
    if slug in ("landedcostrate", "landedrate", "landedcost", "landingrate", "totallandedcost", "landedprice", "totallandedrate"):
        return 4
    if slug in ("rate", "unitrate", "unitprice", "basicrate", "grnrate", "price"):
        return 3
    if slug in ("cost", "unitcost", "itemrate"):
        return 2
    return 1



def _parse_safe_date(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if hasattr(val, "year") and hasattr(val, "month") and hasattr(val, "day"):
        return datetime(val.year, val.month, val.day, tzinfo=timezone.utc)
    val_str = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(val_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def ingest_mrp_grn(
    session,
    file_bytes: bytes,
    filename: str,
    plant_id: Optional[str] = None,
    planning_month: int = 1,
    planning_year: int = 2026,
    current_user_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """Ingests store GRN file and performs month-end overwrite upsert for MRP consumable records."""
    if not file_bytes:
        raise ApplicationError("EMPTY_FILE", "The uploaded GRN file is empty.", 400)

    planning_period = f"{planning_year:04d}-{planning_month:02d}"
    now = datetime.now(timezone.utc)

    # 1. Parse raw rows from CSV or Excel into list of lists
    raw_rows: list[list[Any]] = []
    is_csv = filename.lower().endswith(".csv")

    if is_csv:
        text_content = ""
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text_content = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not text_content:
            text_content = file_bytes.decode("utf-8", errors="replace")

        reader = csv.reader(io.StringIO(text_content))
        for row in reader:
            if any(str(c).strip() for c in row if c is not None):
                raw_rows.append(list(row))
    else:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            try:
                ws = wb.active
                if ws is None:
                    ws = wb.worksheets[0]
                for row in ws.iter_rows(values_only=True):
                    if any(row is not None and str(c).strip() for c in row if c is not None):
                        raw_rows.append(list(row))
            finally:
                try:
                    wb.close()
                except Exception:
                    pass
        except Exception as exc:
            raise ApplicationError("INVALID_EXCEL_FORMAT", f"Unable to parse Excel file: {str(exc)}", 400)

    if not raw_rows:
        raise ApplicationError("EMPTY_DATA", "No data rows found in uploaded GRN file.", 400)

    # 2. Dynamic header detection in first 10 rows
    header_row_idx = -1
    col_map: dict[str, int] = {}

    for r_idx, row in enumerate(raw_rows[:10]):
        slugs = [_normalize_header_slug(c) for c in row]
        has_item = any(s in ITEM_CODE_SLUGS for s in slugs if s)
        has_qty = any(s in QTY_SLUGS for s in slugs if s)
        if has_item and has_qty:
            header_row_idx = r_idx
            for c_idx, s in enumerate(slugs):
                if not s:
                    continue
                if s in ITEM_CODE_SLUGS and "item_code" not in col_map:
                    col_map["item_code"] = c_idx
                elif s in QTY_SLUGS:
                    if "qty" not in col_map or _score_qty_slug(s) > _score_qty_slug(slugs[col_map["qty"]]):
                        col_map["qty"] = c_idx
                elif s in RATE_SLUGS:
                    if "rate" not in col_map or _score_rate_slug(s) > _score_rate_slug(slugs[col_map["rate"]]):
                        col_map["rate"] = c_idx
                elif s in GRN_NO_SLUGS and "grn_no" not in col_map:
                    col_map["grn_no"] = c_idx
                elif s in DATE_SLUGS and "date" not in col_map:
                    col_map["date"] = c_idx
                elif s in VENDOR_SLUGS and "vendor" not in col_map:
                    col_map["vendor"] = c_idx
                elif s in PLANT_SLUGS and "plant" not in col_map:
                    col_map["plant"] = c_idx
                elif s in UOM_SLUGS and "uom" not in col_map:
                    col_map["uom"] = c_idx
                elif s in CANCELLED_SLUGS and "cancelled" not in col_map:
                    col_map["cancelled"] = c_idx
                elif s in DESC_SLUGS and "desc" not in col_map:
                    col_map["desc"] = c_idx
            break

    if header_row_idx == -1 or "item_code" not in col_map or "qty" not in col_map:
        raise ApplicationError(
            "NO_VALID_GRN_ITEMS",
            "Could not detect valid items or received quantities in uploaded GRN file. Ensure headers include 'item_id' / 'item_code' and 'grn_qty' / 'received_qty'.",
            400,
        )

    # 3. Aggregate incoming quantities per consumable and plant within this file
    aggregated_incoming: dict[tuple[str, Optional[str]], dict[str, Any]] = {}

    for row_idx, r in enumerate(raw_rows[header_row_idx + 1:], start=header_row_idx + 2):
        # Skip summary rows where grn_no starts with total
        grn_no_val = ""
        if "grn_no" in col_map and col_map["grn_no"] < len(r) and r[col_map["grn_no"]] is not None:
            grn_no_val = str(r[col_map["grn_no"]]).strip()
        if grn_no_val.lower().startswith("total"):
            continue

        # Skip rows where item_code is empty or starts with total
        item_raw = r[col_map["item_code"]] if "item_code" in col_map and col_map["item_code"] < len(r) else None
        item_val = str(item_raw).strip() if item_raw is not None else ""
        if not item_val or item_val.lower() == "total" or item_val.lower().startswith("total"):
            continue

        # Skip cancelled rows
        if "cancelled" in col_map and col_map["cancelled"] < len(r):
            canc_raw = r[col_map["cancelled"]]
            canc_val = str(canc_raw).strip().lower() if canc_raw is not None else ""
            if canc_val in ("yes", "y", "true", "1"):
                continue

        # Quantity
        qty_raw = r[col_map["qty"]] if "qty" in col_map and col_map["qty"] < len(r) else None
        if qty_raw is None or str(qty_raw).strip() == "":
            continue
        try:
            qty_clean = Decimal(str(qty_raw).replace(",", "").strip())
        except (InvalidOperation, ValueError):
            continue

        # Rate
        rate_val = None
        if "rate" in col_map and col_map["rate"] < len(r) and r[col_map["rate"]] is not None:
            rate_str = str(r[col_map["rate"]]).replace(",", "").strip()
            if rate_str:
                try:
                    rate_val = Decimal(rate_str)
                except (InvalidOperation, ValueError):
                    pass

        # Date
        date_val = None
        if "date" in col_map and col_map["date"] < len(r) and r[col_map["date"]] is not None:
            date_val = _parse_safe_date(r[col_map["date"]])

        # Plant
        plant_val = None
        if "plant" in col_map and col_map["plant"] < len(r) and r[col_map["plant"]] is not None:
            pv = str(r[col_map["plant"]]).strip()
            if pv:
                plant_val = pv
        if not plant_val and plant_id and str(plant_id).strip():
            plant_val = str(plant_id).strip()

        row_plant_key = _normalize_plant_identifier(plant_val) if plant_val else None

        # UOM & Description
        uom_val = None
        if "uom" in col_map and col_map["uom"] < len(r) and r[col_map["uom"]] is not None:
            uv = str(r[col_map["uom"]]).strip()
            if uv:
                uom_val = uv

        desc_val = None
        if "desc" in col_map and col_map["desc"] < len(r) and r[col_map["desc"]] is not None:
            dv = str(r[col_map["desc"]]).strip()
            if dv:
                desc_val = dv

        inv_val = grn_no_val or None

        item_key = item_val.strip().upper()
        agg_key = (item_key, row_plant_key)
        if agg_key not in aggregated_incoming:
            aggregated_incoming[agg_key] = {
                "raw_item": item_val.strip(),
                "qty": qty_clean,
                "invoice_no": inv_val,
                "grn_date": date_val,
                "rate": rate_val,
                "row_plant_key": row_plant_key,
                "raw_plant": plant_val,
                "uom": uom_val,
                "description": desc_val,
            }
        else:
            aggregated_incoming[agg_key]["qty"] += qty_clean
            if inv_val:
                aggregated_incoming[agg_key]["invoice_no"] = inv_val
            if date_val:
                aggregated_incoming[agg_key]["grn_date"] = date_val
            if rate_val is not None:
                aggregated_incoming[agg_key]["rate"] = rate_val
            if uom_val and not aggregated_incoming[agg_key].get("uom"):
                aggregated_incoming[agg_key]["uom"] = uom_val
            if desc_val and not aggregated_incoming[agg_key].get("description"):
                aggregated_incoming[agg_key]["description"] = desc_val

    # 4. Existing record index across month and year
    existing_records = session.scalars(
        select(MonthlyRequirementRecord).where(
            MonthlyRequirementRecord.planning_month == planning_month,
            MonthlyRequirementRecord.planning_year == planning_year,
            MonthlyRequirementRecord.is_deleted == False,  # noqa: E712
        )
    ).all()

    # Index by (consumable_code, plant_key) and globally by consumable_code
    existing_by_plant_and_code: dict[tuple[str, str], list[MonthlyRequirementRecord]] = {}
    existing_by_code: dict[str, list[MonthlyRequirementRecord]] = {}
    for rec in existing_records:
        rec_code = rec.consumable_code.strip().upper()
        rec_plant_k = _normalize_plant_identifier(rec.plant_id or rec.plant)
        if rec_plant_k:
            existing_by_plant_and_code.setdefault((rec_code, rec_plant_k), []).append(rec)
        existing_by_code.setdefault(rec_code, []).append(rec)

    # Find active PlanningVersion if any
    version = session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
        .limit(1)
    )

    t2_month, t2_year = get_t_minus_2_period(planning_month, planning_year)
    t2_batch = session.scalar(
        select(StockStatementBatch)
        .where(
            StockStatementBatch.statement_month == t2_month,
            StockStatementBatch.statement_year == t2_year,
            StockStatementBatch.status == "active",
        )
        .limit(1)
    )
    t2_stock_by_code: dict[str, Decimal] = {}
    if t2_batch:
        lines = session.execute(
            select(StockStatementLine.item_id, StockStatementLine.closing_qty)
            .where(
                StockStatementLine.batch_id == t2_batch.id,
                StockStatementLine.item_class == "CONSUMABLE",
            )
        ).all()
        for item_id, closing_qty in lines:
            if item_id:
                t2_stock_by_code[item_id.strip().upper()] = closing_qty or Decimal("0.0")

    consumables_updated_count = 0
    updated_count = 0
    inserted_count = 0

    # 5. Perform month-end overwrite upsert
    for entry in aggregated_incoming.values():
        raw_item = entry["raw_item"]
        incoming_qty = entry["qty"]
        inv_no = entry["invoice_no"]
        grn_dt = entry["grn_date"]
        rate = entry["rate"]
        row_plant_key = entry["row_plant_key"]
        raw_plant = entry["raw_plant"]
        row_uom = entry.get("uom")
        row_desc = entry.get("description")

        # Resolve consumable master
        consumable = None
        try:
            c_uuid = UUID(raw_item)
            consumable = session.get(Consumable, c_uuid)
        except (ValueError, TypeError):
            pass
        if not consumable:
            consumable = session.scalar(
                select(Consumable).where(func.upper(func.btrim(Consumable.item_id)) == raw_item.upper()).limit(1)
            )

        if consumable:
            consumable_code = consumable.code
            consumable_name = getattr(consumable, "name", None) or row_desc or consumable.code
            consumable_uom = getattr(consumable, "output_unit", None) or getattr(consumable, "unit_of_measure", None) or row_uom or "NOS"
            if rate is not None and hasattr(consumable, "latest_grn_rate"):
                consumable.latest_grn_rate = rate
                consumables_updated_count += 1
        else:
            consumable_code = raw_item
            consumable_name = row_desc or raw_item
            consumable_uom = row_uom or "NOS"
            # Auto-create consumable in master so latest_grn_rate is recorded
            new_consumable = Consumable(
                item_id=raw_item.strip().upper(),
                name=consumable_name,
                output_unit=consumable_uom,
                latest_grn_rate=rate if (rate is not None and rate > Decimal("0")) else Decimal("0.0"),
            )
            session.add(new_consumable)
            consumables_updated_count += 1

        code_upper = consumable_code.strip().upper()
        raw_upper = raw_item.strip().upper()

        matched_recs: list[MonthlyRequirementRecord] = []
        if row_plant_key:
            # Row has specific plant
            matched_recs = existing_by_plant_and_code.get((code_upper, row_plant_key), [])
            if not matched_recs and raw_upper != code_upper:
                matched_recs = existing_by_plant_and_code.get((raw_upper, row_plant_key), [])
        else:
            # Global store intake: match across all plants
            matched_recs = existing_by_code.get(code_upper, [])
            if not matched_recs and raw_upper != code_upper:
                matched_recs = existing_by_code.get(raw_upper, [])

        if matched_recs:
            # Overwrite existing record's grn_received_qty (month-end overwrite, not additive summing)
            for rec in matched_recs:
                rec.grn_received_qty = incoming_qty
                if code_upper in t2_stock_by_code:
                    opening = t2_stock_by_code[code_upper]
                elif raw_upper in t2_stock_by_code:
                    opening = t2_stock_by_code[raw_upper]
                elif rec.opening_stock is not None:
                    opening = rec.opening_stock
                else:
                    opening = Decimal("0.0")
                rec.opening_stock = opening

                consumed = rec.consumed_qty if rec.consumed_qty is not None else Decimal("0.0")
                closing = (opening + rec.grn_received_qty) - consumed
                rec.closing_stock = closing

                gross = rec.gross_requirement if rec.gross_requirement and rec.gross_requirement > Decimal("0") else (rec.scheduled_consumable_qty or Decimal("0.0"))
                rec.gross_requirement = gross
                msl_qty = rec.msl if rec.msl is not None else Decimal("0.0")
                net_req = max(Decimal("0.0"), (gross + msl_qty) - closing)
                rec.net_order_requirement = net_req

                # Sync spreadsheet display columns
                rec.stock_qty = closing
                rec.shortage_qty = net_req
                rec.last_synced_at = now
                rec.grn_source_file = filename
                if inv_no:
                    rec.invoice_no = inv_no
                if grn_dt:
                    rec.grn_date = grn_dt

                if rec.shortage_qty > Decimal("0"):
                    rec.status = "Critical shortage" if rec.closing_stock <= Decimal("0") else "Low"
                else:
                    rec.status = "Normal"

                rec.updated_at = now
                updated_count += 1
        else:
            # Insert a new record initialized with T-2 opening stock and uploaded GRN quantity
            if code_upper in t2_stock_by_code:
                opening = t2_stock_by_code[code_upper]
            elif raw_upper in t2_stock_by_code:
                opening = t2_stock_by_code[raw_upper]
            else:
                opening = Decimal("0.0000")

            closing = opening + incoming_qty
            gross = Decimal("0.0000")
            msl_qty = Decimal("0.0000")
            net_req = max(Decimal("0.0000"), (gross + msl_qty) - closing)
            assigned_plant = raw_plant or plant_id or "Plant 1"
            assigned_plant_id = raw_plant or plant_id or "PLANT_1"
            new_rec = MonthlyRequirementRecord(
                planning_period=planning_period,
                planning_month=planning_month,
                planning_year=planning_year,
                planning_version_id=version.id if version else None,
                part_name=row_desc or "General",
                part_number=raw_item.strip().upper(),
                consumable_code=consumable_code,
                consumable_name=consumable_name,
                process_name="Store Receipt",
                part_thickness=Decimal("0.0000"),
                process_count=1,
                production_order_qty=Decimal("0.0000"),
                scheduled_consumable_qty=Decimal("0.0000"),
                unit=consumable_uom,
                plant=assigned_plant,
                plant_id=assigned_plant_id,
                opening_stock=opening,
                grn_received_qty=incoming_qty,
                consumed_qty=Decimal("0.0000"),
                closing_stock=closing,
                gross_requirement=gross,
                net_order_requirement=net_req,
                stock_qty=closing,
                shortage_qty=net_req,
                po_pending_qty=Decimal("0.0000"),
                msl=msl_qty,
                status="Critical shortage" if (net_req > Decimal("0") and closing <= Decimal("0")) else ("Low" if net_req > Decimal("0") else "Normal"),
                last_synced_at=now,
                grn_source_file=filename,
                invoice_no=inv_no,
                grn_date=grn_dt,
                created_by=current_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(new_rec)
            rec_p_k = _normalize_plant_identifier(assigned_plant_id)
            if rec_p_k:
                existing_by_plant_and_code.setdefault((code_upper, rec_p_k), []).append(new_rec)
            existing_by_code.setdefault(code_upper, []).append(new_rec)
            inserted_count += 1

    # Update version timestamp if available
    if version:
        version.updated_at = now
        if current_user_id:
            version.updated_by = current_user_id

    # Audit log
    session.add(
        AuditLog(
            actor_id=current_user_id,
            action="GRN_OVERWRITE_INGEST",
            entity_type="monthly_requirement_records",
            entity_id=version.id if version else uuid4(),
            new_values={
                "period": planning_period,
                "plant_id": plant_id or "ALL",
                "filename": filename,
                "updated_count": updated_count,
                "inserted_count": inserted_count,
                "consumables_updated_count": consumables_updated_count,
            },
            reason=f"Ingested GRN month-end overwrite file {filename} for {plant_id or 'all plants'} ({planning_period})",
        )
    )

    session.commit()

    return {
        "status": "success",
        "updated_count": updated_count,
        "inserted_count": inserted_count,
        "period": planning_period,
        "consumables_updated_count": consumables_updated_count,
    }


def get_period_calculation_issues(session, *, month: int, year: int) -> list[dict[str, Any]]:
    planning_period = f"{year:04d}-{month:02d}"
    version = session.scalar(
        select(PlanningVersion)
        .where(PlanningVersion.planning_period == planning_period)
        .order_by(PlanningVersion.version_number.desc())
        .limit(1)
    )
    if not version:
        return []
    errors = session.scalars(
        select(RequirementCalculationError)
        .options(
            joinedload(RequirementCalculationError.product),
            joinedload(RequirementCalculationError.prd_order_item),
            joinedload(RequirementCalculationError.consumable),
        )
        .where(RequirementCalculationError.planning_version_id == version.id)
        .order_by(RequirementCalculationError.id)
    ).all()
    results = []
    for err in errors:
        prod = getattr(err, "product", None)
        prd_item = getattr(err, "prd_order_item", None)
        consumable = getattr(err, "consumable", None)
        ctx = getattr(err, "context_data", None) or {}

        product_ref = (
            getattr(err, "product_code", None)
            or (prod.code if prod else None)
            or (prd_item.product_code if prd_item else None)
            or ctx.get("product_code")
            or str(getattr(err, "product_id", "") or "")
        )
        part_number = (
            (prod.part_number if prod else None)
            or (prd_item.part_number if prd_item else None)
            or ctx.get("part_number")
            or getattr(err, "product_code", None)
            or product_ref
            or ""
        )
        item_id = (
            (prod.item_id if prod else None)
            or (prd_item.item_id if prd_item else None)
            or ctx.get("item_id")
            or ""
        )
        product_name = (
            (prod.name if prod else None)
            or (prd_item.product_name if prd_item else None)
            or ctx.get("product_name")
            or ""
        )
        consumable_code = (
            (consumable.code if consumable else None)
            or (consumable.item_id if consumable else None)
            or ctx.get("consumable_code")
            or ""
        )
        error_code = getattr(err, "error_code", "") or ""
        error_message = (
            getattr(err, "error_message", None)
            or getattr(err, "reason", None)
            or ""
        )

        results.append({
            "id": str(getattr(err, "id", "")),
            "product_code": product_ref,
            "part_number": part_number,
            "item_id": item_id,
            "product_name": product_name,
            "consumable_code": consumable_code,
            "error_code": error_code,
            "error_message": error_message,
        })
    return results


def export_period_calculation_issues_csv(session, *, month: int, year: int) -> bytes:
    issues = get_period_calculation_issues(session, month=month, year=year)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Part No.", "Item ID", "Product Code", "Description", "Consumable Item ID", "Issue Code", "Issue Description"])
    for row in issues:
        writer.writerow([
            row["part_number"],
            row["item_id"],
            row["product_code"],
            row["product_name"],
            row["consumable_code"],
            row["error_code"],
            row["error_message"],
        ])
    return out.getvalue().encode("utf-8-sig")
