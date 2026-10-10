from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.modules.auth.router import router as auth_router
from app.modules.auth.user_router import router as user_router
from app.modules.masters.inventory_router import router as inventory_master_router
from app.modules.masters.mapping_router import router as mapping_router
from app.modules.masters.router import router as product_customer_router
from app.modules.plant_workflow.router import router as plant_workflow_router
from app.modules.prd.router import router as prd_router
from app.modules.requirements.router import router as requirements_router
from app.modules.rules.router import router as rules_router
from app.modules.inventory.router import router as inventory_router
from app.modules.inventory.projection_router import router as projection_router
from app.modules.inventory.reorder_router import router as reorder_router
from app.modules.alerts.router import router as alerts_router
from app.modules.purchasing.recommendation_router import router as purchase_recommendation_router
from app.modules.purchasing.approval_router import router as purchase_approval_router
from app.modules.purchasing.plan_router import router as purchase_plan_router

from app.modules.po_grn.router import router as purchase_orders_router
from app.modules.po_grn.grn_router import router as grn_router
from app.modules.prd.prd_workspace_router import router as prd_workspace_router
from app.modules.requirements.requirements_workspace_router import router as requirements_workspace_router
from app.modules.reports.router import router as reports_router
from app.modules.reports.inventory_purchase_router import router as inventory_purchase_reports_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(grn_router)
api_router.include_router(purchase_orders_router)
api_router.include_router(prd_workspace_router)
api_router.include_router(requirements_workspace_router)
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(inventory_master_router)
api_router.include_router(product_customer_router)
api_router.include_router(mapping_router)
api_router.include_router(rules_router)
api_router.include_router(prd_router)
api_router.include_router(requirements_router)
api_router.include_router(plant_workflow_router)
api_router.include_router(inventory_router)
api_router.include_router(projection_router)
api_router.include_router(reorder_router)
api_router.include_router(alerts_router)
api_router.include_router(purchase_recommendation_router)
api_router.include_router(purchase_approval_router)
api_router.include_router(purchase_plan_router)
api_router.include_router(reports_router)
api_router.include_router(inventory_purchase_reports_router)


