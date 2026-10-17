from decimal import Decimal
import pytest
from sqlalchemy import select, func, delete

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.inventory_masters import Unit, SupplierConsumable
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_plan import PurchasePlanDraft
from app.models.requirements import CalculatedRequirement
from app.schemas.purchase_workspace import PurchasePlanSave
from app.services.purchase_workspace import list_purchase_workspace, save_purchase_plan
from app.tests.test_permission_foundation import db, actor
from app.tests.test_central_basic_planning import catalog, calculated


def context(db, catalog):
    identity, _ = calculated(db, catalog)
    user = actor(is_super_admin=True)
    user.id = catalog[0].id
    row = list_purchase_workspace(db, month=10, year=2026).records[0]
    return identity, user, row


def request(row, **changes):
    return PurchasePlanSave(edits=[dict(record_id=row.id, expected_draft_version=row.draft_version,
        expected_name=row.consumable_name, expected_master_unit=row.master_unit or '', **changes)], reason='Synthetic purchase edit')


def save(db, user, data):
    return save_purchase_plan(db, month=10, year=2026, request=data, current_user=user)


def test_requested_quantity_and_notes_save_without_changing_calculation_or_approval(db, catalog):
    identity, user, row = context(db, catalog)
    result = save(db, user, request(row, requested_purchase_qty='12.3456', purchase_notes='Review before order'))
    saved = result.records[0]
    assert saved.requested_purchase_qty == Decimal('12.3456') and saved.purchase_notes == 'Review before order'
    assert saved.requested_purchase_unit == 'PCS' and saved.draft_version == 1
    assert saved.required_qty == Decimal('230') and saved.system_recommended_qty is None
    assert db.scalar(select(func.sum(CalculatedRequirement.calculated_qty))) == Decimal('230')
    assert db.scalar(select(PurchaseApproval)) is None
    assert db.scalar(select(AuditLog).where(AuditLog.action == 'EDIT_PURCHASE_PLAN')) is not None


def test_cell_name_edits_use_master_audit_and_stale_names_are_rejected(db, catalog):
    _, user, row = context(db, catalog)
    result = save(db, user, request(row, consumable_name='Reviewed drill'))
    assert result.records[0].consumable_name == 'Reviewed drill'
    assert catalog[5].name == 'Reviewed drill'
    assert catalog[5].description == 'Reviewed drill'
    with pytest.raises(ApplicationError) as error:
        save(db, user, request(row, consumable_name='Stale overwrite'))
    assert error.value.code == 'STALE_PURCHASE_EDIT'


def test_unit_restrictions_roll_back_other_cell_edits_atomically(db, catalog):
    _, user, row = context(db, catalog)
    db.add(Unit(code='KG', name='Kilograms')); db.commit()
    with pytest.raises(ApplicationError) as error:
        save(db, user, request(row, consumable_name='Must roll back', master_unit='KG', requested_purchase_qty='10'))
    assert error.value.code == 'UNIT_CHANGE_CONFLICT'
    db.refresh(catalog[5])
    assert catalog[5].name == row.consumable_name
    assert db.scalar(select(PurchasePlanDraft)) is None


def test_master_unit_edit_does_not_relabel_historical_calculated_quantity(db, catalog):
    _, user, row = context(db, catalog)
    db.add(Unit(code='KG', name='Kilograms'))
    db.execute(delete(SupplierConsumable).where(SupplierConsumable.consumable_id == catalog[5].id)); db.commit()
    result = save(db, user, request(row, master_unit='KG', requested_purchase_qty='10'))
    saved = result.records[0]
    assert saved.master_unit == 'KG' and saved.unit == 'PCS'
    assert catalog[5].output_unit == 'KG'
    assert saved.requested_purchase_unit == 'PCS' and saved.required_qty == Decimal('230')


def test_concurrent_quantity_edits_do_not_overwrite_each_other(db, catalog):
    _, user, row = context(db, catalog)
    save(db, user, request(row, requested_purchase_qty='10'))
    with pytest.raises(ApplicationError) as error:
        save(db, user, request(row, requested_purchase_qty='20'))
    assert error.value.code == 'STALE_PURCHASE_EDIT'
    assert db.scalar(select(PurchasePlanDraft.requested_qty)) == Decimal('10')


def test_permissions_are_independent_for_purchase_and_master_changes(db, catalog):
    _, _, row = context(db, catalog)
    user = actor(purchase_update=True); user.id = catalog[0].id
    with pytest.raises(ApplicationError) as error:
        save(db, user, request(row, consumable_name='Denied name'))
    assert error.value.status_code == 403
    assert save(db, user, request(row, requested_purchase_qty='10')).records[0].requested_purchase_qty == Decimal('10')
    with pytest.raises(ApplicationError):
        save(db, actor(masters_update=True), request(row, purchase_notes='Denied write'))


def test_submitted_purchase_demand_remains_protected(db, catalog):
    identity, user, row = context(db, catalog)
    db.add(PurchaseApproval(planning_version_id=identity, consumable_id=catalog[5].id, supplier_id=catalog[6].id,
        raw_calculated_qty=Decimal('10'), system_recommended_qty=Decimal('10'), uom='PCS'))
    db.commit()
    with pytest.raises(ApplicationError) as error:
        save(db, user, request(row, requested_purchase_qty='30'))
    assert error.value.code == 'PURCHASE_REVIEW_PROTECTED'


def test_saved_requested_quantity_and_notes_reach_the_review_queue(db, catalog):
    from app.services.purchase_approval import list_purchase_approvals
    identity, user, row = context(db, catalog)
    save(db, user, request(row, requested_purchase_qty='30', purchase_notes='Please review this proposal'))
    db.add(PurchaseApproval(planning_version_id=identity, consumable_id=catalog[5].id, supplier_id=catalog[6].id,
        raw_calculated_qty=Decimal('10'), system_recommended_qty=Decimal('12'), uom='PCS'))
    db.commit()
    result = list_purchase_approvals(db)[0]
    assert result.requested_purchase_qty == Decimal('30') and result.requested_purchase_unit == 'PCS'
    assert result.purchase_notes == 'Please review this proposal'
    assert result.system_recommended_qty == Decimal('12') and result.approved_qty is None and result.status == 'PENDING'


def test_missing_master_unit_can_be_filled_later_without_rewriting_calculation_unit(db, catalog):
    _, user, _ = context(db, catalog)
    catalog[5].unit_id = None; db.commit()
    row = list_purchase_workspace(db, month=10, year=2026).records[0]
    result = save(db, user, request(row, master_unit='PCS'))
    assert result.records[0].master_unit == 'PCS' and result.records[0].unit == 'PCS'
