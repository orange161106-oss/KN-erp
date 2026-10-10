"""Super Admin approves one calculated revision, preserving calculation evidence."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.errors import ApplicationError
from app.models.prd import PlanningVersion
from app.models.requirements import CalculatedRequirement, RequirementCalculationError
from app.models.plant_workflow import PlantConfirmation
from app.models.audit import AuditLog


def approve(session, identity, user):
    if not user.is_super_admin:
        raise ApplicationError('PERMISSION_DENIED', 'Super Admin approval is required.', 403)
    version = session.scalar(select(PlanningVersion).where(PlanningVersion.id == identity).with_for_update())
    if version is None:
        raise ApplicationError('PLANNING_VERSION_NOT_FOUND', 'Planning revision not found.', 404)
    latest = session.scalar(select(PlanningVersion).where(PlanningVersion.planning_period == version.planning_period)
                            .order_by(PlanningVersion.version_number.desc()).limit(1))
    if latest.id != version.id:
        raise ApplicationError('LATEST_REVISION_REQUIRED', 'Approve the latest revision for this planning period.', 409)
    if version.status == 'APPROVED':
        return {'planning_version_id': version.id, 'status': version.status, 'replayed': True}
    if version.status != 'CALCULATED' or session.scalar(select(RequirementCalculationError.id)
            .where(RequirementCalculationError.planning_version_id == identity).limit(1)):
        raise ApplicationError('CALCULATION_REQUIRED', 'Run and resolve all calculation errors before approval.', 409)
    rows = list(session.scalars(select(CalculatedRequirement).where(CalculatedRequirement.planning_version_id == identity)))
    old = version.status
    for row in rows:
        if session.scalar(select(PlantConfirmation.id).where(PlantConfirmation.calculated_requirement_id == row.id)) is None:
            session.add(PlantConfirmation(calculated_requirement_id=row.id, planning_version_id=version.id,
                        plant_id=row.plant_id, confirmed_by=user.id, notes='Super Admin approval of calculated revision'))
    version.status = 'APPROVED'
    version.approved_by = user.id
    version.approved_at = datetime.now(timezone.utc)
    session.add(AuditLog(actor_id=user.id, action='APPROVE', entity_type='planning_version', entity_id=version.id,
        old_values={'status': old}, new_values={'status': 'APPROVED', 'requirement_ids': [str(row.id) for row in rows]},
        reason='Super Admin approved calculated requirements; no purchase order created'))
    session.commit()
    return {'planning_version_id': version.id, 'status': version.status, 'replayed': False}
