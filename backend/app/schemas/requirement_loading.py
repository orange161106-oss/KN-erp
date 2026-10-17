"""Additive read contracts for loading a Requirement screen in one request."""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from app.schemas.plant_workflow import FinalRequirementItemResponse
from app.schemas.requirements import CalculatedRequirementResponse, RequirementCalculationErrorResponse
from app.schemas.requirements_workspace import MonthlyPlanMetadata, RequirementWorkspaceRecord


class CentralVersion(BaseModel):
    id: UUID
    planning_period: str
    revision_label: str
    status: str
    source_filename: str | None = None
    approved_at: datetime | None = None
    is_latest: bool


class CentralResults(BaseModel):
    calculations: list[CalculatedRequirementResponse]
    errors: list[RequirementCalculationErrorResponse]
    summary: list[FinalRequirementItemResponse]


class CentralWorkspace(BaseModel):
    versions: list[CentralVersion]
    selected_version_id: UUID | None
    results: CentralResults | None


class MonthlyWorkspace(BaseModel):
    plan_metadata: MonthlyPlanMetadata
    records: list[RequirementWorkspaceRecord]
