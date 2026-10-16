from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.core.errors import ApplicationError
from app.schemas.master_uploads import Category, ExistingMasterDelete, ExistingMasterView, MasterCatalogSave, MasterCatalogView, MasterPeriodView, MasterPeriodSave, MasterPeriodDelete
from app.security.permissions import require_feature_flag
from app.services import master_uploads as service
from app.services import master_catalog as catalog

router = APIRouter(prefix="/masters/product-master", tags=["product-master-periods"])
Database = Annotated[Session, Depends(get_db)]
Month = Annotated[int, Query(ge=1, le=12)]
Year = Annotated[int, Query(ge=2000, le=2100)]
Read = Annotated[CurrentUser, Depends(require_feature_flag("masters_read"))]
Create = Annotated[CurrentUser, Depends(require_feature_flag("masters_create"))]
Update = Annotated[CurrentUser, Depends(require_feature_flag("masters_update"))]
Delete = Annotated[CurrentUser, Depends(require_feature_flag("masters_delete"))]


@router.get("/{category}/workspace", response_model=MasterCatalogView)
def get_catalog(category: Category, session: Database, user: Read):
    return catalog.get_catalog(session, category)


@router.post("/{category}/workspace/preview", response_model=MasterCatalogView)
def preview_catalog(category: Category, session: Database, user: Create, file: UploadFile = File(...)):
    return catalog.preview(session, category, file.filename or "upload.xlsx", file.file.read(15 * 1024 * 1024 + 1))


@router.post("/{category}/workspace", response_model=MasterCatalogView)
def save_catalog_upload(category: Category, session: Database, user: Create,
                        file: UploadFile = File(...), review: str = Form(...)):
    try:
        payload = MasterCatalogSave.model_validate_json(review)
    except ValidationError:
        raise ApplicationError("INVALID_MASTER_EDIT", "Invalid reviewed changes. Upload and review the workbook again.", 422) from None
    return catalog.save_upload(session, category, file.filename or "upload.xlsx",
                               file.file.read(15 * 1024 * 1024 + 1), payload, user)


@router.patch("/{category}/workspace", response_model=MasterCatalogView)
def save_catalog_changes(category: Category, session: Database, user: Update, payload: MasterCatalogSave):
    return catalog.save_changes(session, category, payload, user)


@router.delete("/{category}/workspace", response_model=MasterCatalogView)
def remove_catalog(category: Category, session: Database, user: Delete, payload: ExistingMasterDelete):
    return catalog.delete_catalog(session, category, payload, user)


@router.get("/{category}/workspace/export")
def export_catalog(category: Category, session: Database, user: Read):
    return Response(catalog.export_catalog(session, category),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Product_Master_{category}.xlsx"'})


@router.get("/{category}/existing-data", response_model=ExistingMasterView)
def get_existing(category: Category, session: Database, user: Read):
    return service.get_existing(session, category)


@router.delete("/{category}/existing-data")
def delete_existing(category: Category, session: Database, user: Delete, payload: ExistingMasterDelete):
    return service.delete_existing(session, category, payload, user)


@router.get("/{category}/period", response_model=MasterPeriodView)
def get_period(category: Category, month: Month, year: Year, session: Database, user: Read):
    return service.get_period(session, category, month, year)


@router.post("/{category}/period", response_model=MasterPeriodView)
def upload_period(category: Category, month: Month, year: Year, session: Database, user: Create,
                  file: UploadFile = File(...)):
    return service.import_period(session, category, month, year, file.filename or "upload.xlsx",
                                 file.file.read(15 * 1024 * 1024 + 1), user)


@router.patch("/{category}/period", response_model=MasterPeriodView)
def save_period(category: Category, month: Month, year: Year, session: Database, user: Update,
                payload: MasterPeriodSave):
    return service.save_period(session, category, month, year, payload, user)


@router.delete("/{category}/period")
def delete_period(category: Category, month: Month, year: Year, session: Database, user: Delete,
                  payload: MasterPeriodDelete):
    return service.delete_period(session, category, month, year, payload, user)


@router.get("/{category}/period/export")
def export_period(category: Category, month: Month, year: Year, session: Database, user: Read):
    content = service.export_period(session, category, month, year)
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Product_Master_{category}_{year}_{month:02d}.xlsx"'})
