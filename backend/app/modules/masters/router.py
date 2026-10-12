from app.security.permissions import require_permissions
from typing import Annotated, Sequence

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.masters import (
    CustomerAliasCreate,
    CustomerAliasResponse,
    CustomerCreate,
    CustomerResponse,
    ProductBulkCreate,
    ProductCreate,
    ProductResponse,
    ProductSourcePreview,
)
from app.security.dependencies import get_current_user
from app.services.customer import create_customer, create_customer_alias, list_customer_aliases, list_customers
from app.services.product import create_product, create_products, list_products
from app.services import product_source

router = APIRouter(prefix="/masters", tags=["masters"])


@router.post("/products/preview", response_model=ProductSourcePreview, dependencies=[Depends(require_permissions("masters.write"))])
async def preview_products(file: UploadFile = File(...), sheet_name: str = Form("Prd. Order")):
    return product_source.preview(await file.read(10 * 1024 * 1024 + 1), file.filename or "source.xlsx", sheet_name)


@router.post("/products/reviewed", response_model=list[ProductResponse], dependencies=[Depends(require_permissions("masters.write"))])
def reviewed_products(data: ProductBulkCreate, session: Annotated[Session, Depends(get_db)],
                      user: Annotated[CurrentUser, Depends(get_current_user)]):
    return create_products(session, data, user.id)


@router.get("/products", response_model=list[ProductResponse], dependencies=[Depends(require_permissions('masters.read'))])
def get_products(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Sequence[ProductResponse]:
    return list_products(session)


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permissions('masters.write'))])
def post_product(
    data: ProductCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProductResponse:
    try:
        return create_product(session, data, current_user.id)
    except ValueError as e:
        raise ApplicationError("DUPLICATE_PRODUCT", str(e), status_code=409)


@router.get("/customers", response_model=list[CustomerResponse], dependencies=[Depends(require_permissions('masters.read'))])
def get_customers(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Sequence[CustomerResponse]:
    return list_customers(session)


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permissions('masters.write'))])
def post_customer(
    data: CustomerCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CustomerResponse:
    try:
        return create_customer(session, data)
    except ValueError as e:
        raise ApplicationError("DUPLICATE_CUSTOMER", str(e), status_code=409)


@router.get("/customers/aliases", response_model=list[CustomerAliasResponse], dependencies=[Depends(require_permissions('masters.read'))])
def get_customer_aliases(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Sequence[CustomerAliasResponse]:
    return list_customer_aliases(session)


@router.post("/customers/aliases", response_model=CustomerAliasResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permissions('masters.write'))])
def post_customer_alias(
    data: CustomerAliasCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CustomerAliasResponse:
    try:
        return create_customer_alias(session, data)
    except ValueError as e:
        raise ApplicationError("ALIAS_ERROR", str(e), status_code=422)
