from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.error import ErrorResponse
from app.schemas.inventory_masters import Page, StatusChange
from app.security.permissions import require_permissions
from app.services import inventory_masters as service


def resource_router(resource: service.Resource) -> APIRouter:
    router = APIRouter(prefix="/" + resource.path, tags=["inventory masters"], responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)
    })
    read = require_permissions("masters." + resource.permission_name + ".read")
    write = require_permissions("masters." + resource.permission_name + ".write")
    create_schema, update_schema = resource.create_schema, resource.update_schema
    response_schema = resource.response_schema

    @router.get("", response_model=Page[response_schema], operation_id="list_" + resource.permission_name)
    def list_records(
        session: Annotated[Session, Depends(get_db)], user: Annotated[CurrentUser, Depends(read)],
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0)] = 0,
        q: Annotated[str | None, Query(max_length=100)] = None,
        is_active: bool | None = None, supplier_id: UUID | None = None, consumable_id: UUID | None = None,
    ):
        return service.list_records(session, resource, limit=limit, offset=offset, q=q,
                                    is_active=is_active, supplier_id=supplier_id, consumable_id=consumable_id)

    @router.get("/{entity_id}", response_model=response_schema, operation_id="get_" + resource.permission_name)
    def get_record(entity_id: UUID, session: Annotated[Session, Depends(get_db)], user: Annotated[CurrentUser, Depends(read)]):
        return service.get_record(session, resource, entity_id)

    @router.post("", response_model=response_schema, status_code=201, operation_id="create_" + resource.permission_name)
    def create_record(data: create_schema, session: Annotated[Session, Depends(get_db)], user: Annotated[CurrentUser, Depends(write)]):
        return service.create_record(session, resource, data, user.id)

    @router.patch("/{entity_id}", response_model=response_schema, operation_id="update_" + resource.permission_name)
    def update_record(entity_id: UUID, data: update_schema, session: Annotated[Session, Depends(get_db)], user: Annotated[CurrentUser, Depends(write)]):
        return service.update_record(session, resource, entity_id, data, user.id)

    @router.patch("/{entity_id}/status", response_model=response_schema, operation_id="status_" + resource.permission_name)
    def change_status(entity_id: UUID, data: StatusChange, session: Annotated[Session, Depends(get_db)], user: Annotated[CurrentUser, Depends(write)]):
        return service.change_status(session, resource, entity_id, data, user.id)

    return router


router = APIRouter(prefix="/masters")
for resource in service.RESOURCES:
    router.include_router(resource_router(resource))
