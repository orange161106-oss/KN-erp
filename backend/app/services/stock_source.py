"""Map reviewed daily stock statements into the existing authoritative import contract."""
import hashlib
from datetime import datetime
from sqlalchemy import select
from app.core.errors import ApplicationError
from app.models.inventory_masters import Consumable, Unit
from app.schemas.inventory import SourceImport, SourceSnapshot
from app.services.product_source import source_rows, normalize_header


def preview(session, contents, filename, sheet_name, *, as_of, generated_at, exclusions_confirmed):
    if not exclusions_confirmed:
        raise ApplicationError('STOCK_EXCLUSIONS_REQUIRED', 'Confirm that the balance excludes damaged, rejected, held and reserved stock.', 422)
    rows = source_rows(contents, filename, sheet_name)
    columns, header = None, None
    aliases = {'itemid': 'code', 'itemcode': 'code', 'unit': 'unit', 'uom': 'unit',
               'closing': 'quantity', 'closingqty': 'quantity', 'closingquantity': 'quantity',
               'usablequantity': 'quantity', 'usablestock': 'quantity'}
    for index, row in enumerate(rows[:10]):
        found = {aliases[normalize_header(value)]: i for i, value in enumerate(row) if normalize_header(value) in aliases}
        if set(found) == {'code', 'unit', 'quantity'}:
            columns, header = found, index
            break
    if columns is None:
        raise ApplicationError('STOCK_HEADERS_REQUIRED', 'Item ID, Unit and Closing/Usable Quantity headers are required.', 422)
    materials = {c.code: c for c in session.scalars(select(Consumable).where(Consumable.is_active.is_(True)))}
    units = {u.id: u for u in session.scalars(select(Unit))}
    snapshots = []
    for number, row in enumerate(rows[header + 1:], start=header + 2):
        code = str(row[columns['code']] or '').strip()
        if not code:
            continue
        material = materials.get(code)
        if material is None:
            raise ApplicationError('STOCK_MATERIAL_REVIEW_REQUIRED', f'Row {number}: review material {code} in master data before import.', 422)
        unit = units[material.unit_id]
        source_unit = str(row[columns['unit']] or '').strip()
        if not unit.is_active or source_unit.casefold() != unit.code.casefold():
            raise ApplicationError('STOCK_UNIT_MISMATCH', f'Row {number}: source unit {source_unit} does not match {unit.code}. An approved conversion is required.', 422)
        quantity = row[columns['quantity']]
        # Spreadsheet numeric cells are read as text before exact Decimal validation.
        snapshots.append(SourceSnapshot(source_snapshot_id=f'daily:{material.id}:{as_of.isoformat()}',
            consumable_id=material.id, unit_id=material.unit_id, usable_quantity=str(quantity), as_of=as_of,
            nonusable_excluded=True, reservations_excluded=True))
    digest = hashlib.sha256(contents + as_of.isoformat().encode() + generated_at.isoformat().encode()).hexdigest()
    return SourceImport(export_id=f'stock-xlsx:{digest}', generated_at=generated_at,
        import_reason=f'Reviewed daily usable-stock statement: {filename}; sheet {sheet_name}', snapshots=snapshots)
