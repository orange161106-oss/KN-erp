from typing import Annotated, Sequence

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.masters import CustomerCreate, CustomerResponse, ProductCreate, ProductResponse
from app.security.dependencies import get_current_user
from app.services.customer import create_customer, list_customers
from app.services.product import create_product, list_products

router = APIRouter(prefix="/masters", tags=["masters"])


@router.get("/products", response_model=list[ProductResponse])
def get_products(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Sequence[ProductResponse]:
    return list_products(session)


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def post_product(
    data: ProductCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProductResponse:
    try:
        return create_product(session, data)
    except ValueError as e:
        raise ApplicationError("DUPLICATE_PRODUCT", str(e), status_code=409)


@router.get("/customers", response_model=list[CustomerResponse])
def get_customers(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Sequence[CustomerResponse]:
    return list_customers(session)


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def post_customer(
    data: CustomerCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CustomerResponse:
    try:
        return create_customer(session, data)
    except ValueError as e:
        raise ApplicationError("DUPLICATE_CUSTOMER", str(e), status_code=409)
