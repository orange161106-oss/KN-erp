from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.stock_statements import StockStatementLine, StockParameter
from app.tests.test_stock_statement_delete import db, identity, seed as statement_seed, client_for
from app.tests.test_stock_management_delete import seed as parameter_seed
from app.services import stock_statement_service, stock_management_service


def editing_case(db, module):
    batch = statement_seed(db) if module == 'statement' else parameter_seed(db)
    model = StockStatementLine if module == 'statement' else StockParameter
    row = db.scalar(select(model).where(model.batch_id == batch.id))
    field = 'receipt_qty' if module == 'statement' else 'min_stock_level'
    body = {'month':9,'year':2026,'batch_id':str(batch.id),'updates':[{'id':str(row.id),field:'12.1234'}]}
    return batch, row, field, body


@pytest.mark.parametrize('module',['statement','management'])
def test_exact_decimal_patch_is_audited_and_preserves_unedited_fields(db,module):
    batch,row,field,body = editing_case(db,module)
    with client_for(db,identity(db,inventory_update=True)) as client:
        response=client.patch(f'/api/v1/inventory/{module}/batch-update',json=body)
    assert response.status_code == 200, response.text
    db.refresh(row)
    assert getattr(row,field) == Decimal('12.1234')
    if module == 'management':
        assert row.max_stock_level == 20 and row.min_order_qty == 5 and row.lead_time_days == 2
    audit=db.scalar(select(AuditLog))
    assert audit.actor_id == identity(db).id and audit.entity_id == row.id
    assert audit.new_values[field] == '12.1234'


@pytest.mark.parametrize('module',['statement','management'])
def test_explicit_null_clears_only_one_field(db,module):
    _,row,field,body=editing_case(db,module)
    body['updates'][0][field]=None
    with client_for(db,identity(db,inventory_update=True)) as client:
        response=client.patch(f'/api/v1/inventory/{module}/batch-update',json=body)
    assert response.status_code == 200
    db.refresh(row)
    assert getattr(row,field) is None
    if module == 'management': assert row.max_stock_level == 20


@pytest.mark.parametrize('module',['statement','management'])
@pytest.mark.parametrize('flags',[{'inventory_read':True},{'inventory_create':True}])
def test_read_and_upload_cannot_edit(db,module,flags):
    _,_,_,body=editing_case(db,module)
    with client_for(db,identity(db,**flags)) as client:
        assert client.patch(f'/api/v1/inventory/{module}/batch-update',json=body).status_code == 403


@pytest.mark.parametrize('module',['statement','management'])
@pytest.mark.parametrize('value',['-1','0.00001','NaN','Infinity','not numeric'])
def test_invalid_decimal_edits_are_rejected(db,module,value):
    _,row,field,body=editing_case(db,module)
    body['updates'][0][field]=value
    before=getattr(row,field)
    with client_for(db,identity(db,inventory_update=True)) as client:
        assert client.patch(f'/api/v1/inventory/{module}/batch-update',json=body).status_code == 422
    db.refresh(row)
    assert getattr(row,field) == before


@pytest.mark.parametrize('module',['statement','management'])
def test_entire_patch_rolls_back_if_one_row_is_invalid(db,module):
    _,row,field,body=editing_case(db,module)
    before=getattr(row,field)
    body['updates'].append({'id':str(uuid4()),field:'3'})
    with client_for(db,identity(db,inventory_update=True)) as client:
        assert client.patch(f'/api/v1/inventory/{module}/batch-update',json=body).status_code == 422
    db.refresh(row)
    assert getattr(row,field) == before
    assert db.scalar(select(AuditLog)) is None


@pytest.mark.parametrize('module',['statement','management'])
def test_replaced_batch_cannot_be_corrected_from_stale_page(db,module):
    batch,_,_,body=editing_case(db,module)
    batch.status='superseded'; db.commit()
    with client_for(db,identity(db,inventory_update=True)) as client:
        assert client.patch(f'/api/v1/inventory/{module}/batch-update',json=body).status_code in (404,409)


@pytest.mark.parametrize('module',['statement','management'])
def test_audit_failure_rolls_back_edits(db,module):
    _,row,field,body=editing_case(db,module)
    before=getattr(row,field)
    service=stock_statement_service if module == 'statement' else stock_management_service
    with patch.object(service,'log_audit_event',side_effect=RuntimeError('synthetic audit failure')):
        with client_for(db,identity(db,inventory_update=True)) as client:
            with pytest.raises(RuntimeError,match='synthetic audit failure'):
                client.patch(f'/api/v1/inventory/{module}/batch-update',json=body)
    db.refresh(row)
    assert getattr(row,field) == before


def test_identity_column_changes_and_fractional_lead_time_are_rejected(db):
    for module in ('statement','management'):
        _,_,_,body=editing_case(db,module)
        body['updates'][0]['item_id']='INVENTED'
        with client_for(db,identity(db,inventory_update=True)) as client:
            assert client.patch(f'/api/v1/inventory/{module}/batch-update',json=body).status_code == 422
    _,_,_,body=editing_case(db,'management')
    body['updates'][0]={'id':body['updates'][0]['id'],'lead_time_days':1.5}
    with client_for(db,identity(db,inventory_update=True)) as client:
        assert client.patch('/api/v1/inventory/management/batch-update',json=body).status_code == 422


@pytest.mark.parametrize('module',['statement','management'])
def test_description_correction_is_saved_and_audited_without_changing_identity(db,module):
    _,row,_,body=editing_case(db,module)
    field='item_description' if module=='statement' else 'description'
    item_id=row.item_id
    body['updates']=[{'id':str(row.id),field:'Rework Tag, approved'}]
    with client_for(db,identity(db,inventory_update=True)) as client:
        response=client.patch(f'/api/v1/inventory/{module}/batch-update',json=body)
    assert response.status_code == 200, response.text
    db.refresh(row)
    assert getattr(row,field) == 'Rework Tag, approved'
    assert row.item_id == item_id
    audit=db.scalar(select(AuditLog))
    assert audit.new_values[field] == 'Rework Tag, approved'


@pytest.mark.parametrize('module',['statement','management'])
def test_description_clear_and_validation(db,module):
    _,row,_,body=editing_case(db,module)
    field='item_description' if module=='statement' else 'description'
    with client_for(db,identity(db,inventory_update=True)) as client:
        body['updates']=[{'id':str(row.id),field:'x'*2001}]
        assert client.patch(f'/api/v1/inventory/{module}/batch-update',json=body).status_code == 422
        body['updates']=[{'id':str(row.id),field:None}]
        assert client.patch(f'/api/v1/inventory/{module}/batch-update',json=body).status_code == 200
    db.refresh(row)
    assert getattr(row,field) is None
