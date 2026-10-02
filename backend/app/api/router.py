from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.modules.auth.router import router as auth_router
from app.modules.masters.inventory_router import router as inventory_master_router
from app.modules.masters.mapping_router import router as mapping_router
from app.modules.masters.router import router as product_customer_router
from app.modules.prd.router import router as prd_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(inventory_master_router)
api_router.include_router(product_customer_router)
api_router.include_router(mapping_router)
api_router.include_router(prd_router)
