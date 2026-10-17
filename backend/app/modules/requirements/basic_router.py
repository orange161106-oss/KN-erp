"""Central planning uses strict grants and retains legacy plant workflows."""
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.errors import ApplicationError
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.requirements import CalculationRunRequest
from app.schemas.requirement_loading import CentralWorkspace
from app.security.permissions import require_feature_flag
from app.services import basic_planning as service
from app.services.requirements import get_calculated_requirements, get_calculation_errors
from app.services.plant_workflow import get_final_requirements
from app.models.projection import ProjectionInputSet

router = APIRouter(prefix='/requirements/basic', tags=['central basic planning'])
DB = Annotated[Session, Depends(get_db)]
Read = Annotated[CurrentUser, Depends(require_feature_flag('requirements_read'))]
Calculate = Annotated[CurrentUser, Depends(require_feature_flag('requirements_update'))]
CreatePRD = Annotated[CurrentUser, Depends(require_feature_flag('prd_planning_create'))]

class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    planning_version_id: UUID
    as_of_date: date

def central_user(user):
    if not user.is_super_admin and user.plant_ids:
        raise ApplicationError('CENTRAL_REVIEW_REQUIRED', 'Central plans are reviewed by Super Admin.', 403)

@router.get('/versions')
def versions(user: Read, db: DB):
    central_user(user)
    return service.versions(db)

@router.get('/workspace', response_model=CentralWorkspace)
def workspace(user: Read, db: DB, planning_version_id: UUID | None = None):
    central_user(user)
    return service.workspace(db, planning_version_id)

@router.post('/production-preview')
def production_preview(user: CreatePRD, db: DB, file: UploadFile = File(...), sheet_name: str = Form('Prd. Order'),
    target_period: str = Form(...), revision_label: str | None = Form(None), as_of_date: date = Form(...)):
    return jsonable_encoder(service.production_preview(db, file.file.read(10 * 1024 * 1024 + 1), file.filename or '', sheet_name,
        target_period, revision_label, as_of_date), custom_encoder={Decimal: str})

@router.post('/production-confirm')
def production_confirm(user: CreatePRD, db: DB, file: UploadFile = File(...), sheet_name: str = Form(...),
    target_period: str = Form(...), revision_label: str = Form(...), as_of_date: date = Form(...), review_token: str = Form(...)):
    return service.production_confirm(db, file.file.read(10 * 1024 * 1024 + 1), file.filename or '', sheet_name,
        target_period, revision_label, as_of_date, review_token, user.id)

@router.post('/preview')
def preview(data: PreviewRequest, user: Read, db: DB):
    central_user(user)
    return jsonable_encoder(service.preview(db, data.planning_version_id, data.as_of_date), custom_encoder={Decimal: str})

@router.post('/calculate')
def calculate(data: PreviewRequest, user: Calculate, db: DB):
    central_user(user)
    if not service.is_central_version(db, data.planning_version_id):
        raise ApplicationError('CENTRAL_VERSION_REQUIRED', 'Choose a central production revision.', 404)
    return service.calculate(db, CalculationRunRequest(**data.model_dump()), user.id)

@router.get('/{version_id}/results')
def results(version_id: UUID, user: Read, db: DB):
    central_user(user)
    if not service.is_central_version(db, version_id):
        raise ApplicationError('CENTRAL_VERSION_REQUIRED', 'Choose a central production revision.', 404)
    return {'calculations': get_calculated_requirements(db, version_id), 'errors': get_calculation_errors(db, version_id),
        'summary': get_final_requirements(db, planning_version_id=version_id)}

@router.get('/{version_id}/sources')
def projection_sources(version_id: UUID, consumable_id: UUID, user: Read, db: DB):
    central_user(user)
    return [{'source_set_id': row.source_set_id, 'imported_at': row.imported_at,
        'stock_snapshot_id': row.stock_snapshot_id, 'source_reference': (row.payload or {}).get('source_reference')}
        for row in db.scalars(select(ProjectionInputSet).where(ProjectionInputSet.planning_version_id == version_id,
            ProjectionInputSet.consumable_id == consumable_id).order_by(ProjectionInputSet.imported_at.desc()))]

@router.get('/{version_id}/export')
def export(version_id: UUID, user: Read, db: DB, format: str = Query('xlsx')):
    value = results(version_id, user, db)
    if format not in {'xlsx', 'csv'}:
        raise ApplicationError('INVALID_EXPORT_FORMAT', 'Choose xlsx or csv.', 422)
    import csv, io, json
    from openpyxl import Workbook
    rows = [['Product Code', 'Part No.', 'Product Item ID', 'Product Description', 'Process', 'Consumable Item ID', 'Consumable Name', 'Production Quantity', 'Basic Requirement', 'Unit', 'Norm ID', 'Norm Version', 'Parameters', 'Steps']]
    for item in value['calculations']:
        rows.append([item.product_code, item.product_part_number, item.product_item_id, item.product_name,
            item.process_name, item.consumable_code, item.consumable_name,
            str(item.source_production_qty), str(item.calculated_qty), item.uom, str(item.rule_id), item.rule_version,
            json.dumps(item.parameters), json.dumps(item.calculation_steps)])
    rows += [[], ['Consolidated Consumable', 'Basic Requirement', 'Unit', 'Super Admin Approved']]
    rows += [[row.consumable_code, str(row.final_required_qty), row.uom, str(row.is_fully_confirmed)] for row in value['summary']]
    rows += [[], ['Source Item', 'Validation Code', 'Validation Error']]
    rows += [[str(row.prd_order_item_id), row.error_code, row.error_message] for row in value['errors']]
    if format == 'csv':
        stream = io.StringIO(); writer = csv.writer(stream)
        for row in rows:
            writer.writerow(["'" + cell if isinstance(cell, str) and cell.startswith(('=', '+', '-', '@')) else cell for cell in row])
        content, media = stream.getvalue().encode('utf-8-sig'), 'text/csv; charset=utf-8'
    else:
        book = Workbook(); book.active.title = 'Basic Requirements'
        for row in rows: book.active.append(row)
        for row in book.active:
            for cell in row:
                if isinstance(cell.value, str): cell.data_type = 's'
        stream = io.BytesIO(); book.save(stream)
        content, media = stream.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return Response(content, media_type=media, headers={'Content-Disposition': f'attachment; filename="basic-requirements.{format}"'})
