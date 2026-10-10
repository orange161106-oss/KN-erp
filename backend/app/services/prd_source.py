"""Read KNL revision columns and flat PRD exports without invented values."""
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from app.core.errors import ApplicationError
from app.services.product_source import identity_headers, normalize_header


def period(value):
    if isinstance(value, (datetime, date)):
        return value.strftime('%Y-%m')
    text = str(value or '').strip()
    for fmt in ('%Y-%m', '%d.%m.%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt).strftime('%Y-%m')
        except ValueError:
            pass
    raise ApplicationError('PLANNING_PERIOD_REQUIRED', 'Provide a valid planning month (YYYY-MM).', 422)


def revision(value):
    text = str(value or '').strip().upper()
    if not re.fullmatch(r'R(?:0|[1-9][0-9]*)', text):
        raise ApplicationError('REVISION_REQUIRED', 'Use a numeric revision such as R0, R1 or R3.', 422)
    return int(text[1:])


def parse(rows, target_period=None, revision_label=None):
    header, columns = identity_headers(rows)
    revisions = [(revision(value), i) for i, value in enumerate(rows[header])
                 if re.fullmatch(r'R(?:0|[1-9][0-9]*)', str(value or '').strip().upper())]
    if revisions:
        if not target_period:
            raise ApplicationError('PLANNING_PERIOD_REQUIRED', 'Select the planning month to distinguish repeated revision columns.', 422)
        target_period = period(target_period)
        month_rows = [row for row in rows[:header] if any(normalize_header(v) == 'month' for v in row)]
        if len(month_rows) != 1:
            raise ApplicationError('SOURCE_MONTH_REQUIRED', 'The revision columns need one verified Month header row.', 422)
        eligible = []
        for number, index in revisions:
            try:
                month = period(month_rows[0][index])
            except ApplicationError:
                continue
            if month == target_period:
                eligible.append((number, index))
        if revision_label is not None and revision_label.strip():
            wanted = revision(revision_label)
            eligible = [(number, index) for number, index in eligible if number == wanted]
        if not eligible:
            raise ApplicationError('REVISION_NOT_FOUND', 'No revision column matches the selected month/revision.', 422)
        highest = max(number for number, _ in eligible)
        selected = [(number, index) for number, index in eligible if number == highest]
        if len(selected) != 1:
            raise ApplicationError('AMBIGUOUS_REVISION', 'The selected month has repeated columns for the same revision.', 422)
        rev, quantity_column = selected[0]
        revision_label = f'R{rev}'
    else:
        aliases = {'plannedquantity': 'quantity', 'plannedqty': 'quantity', 'planqty': 'quantity',
                   'quantity': 'quantity', 'qty': 'quantity', 'plant': 'plant', 'plantcode': 'plant',
                   'plantname': 'plant', 'targetperiod': 'period', 'planningperiod': 'period',
                   'planningversion': 'revision', 'revision': 'revision'}
        columns.update({aliases[normalize_header(v)]: i for i, v in enumerate(rows[header]) if normalize_header(v) in aliases})
        if 'quantity' not in columns:
            raise ApplicationError('QUANTITY_COLUMN_REQUIRED', 'A planned-quantity column is required.', 422)
        quantity_column = columns['quantity']
    result = []
    for row_number, row in enumerate(rows[header + 1:], start=header + 2):
        def value(field):
            return row[columns[field]] if field in columns and columns[field] < len(row) else None
        identifiers = {field: str(value(field)).strip() if value(field) is not None else ''
                       for field in ('item_id', 'part_number', 'code')}
        if not any(identifiers.values()):
            continue
        raw = row[quantity_column] if quantity_column < len(row) else None
        try:
            quantity = Decimal(str(raw).strip())
            if not quantity.is_finite() or quantity < 0 or quantity > Decimal('9999999999.9999') or quantity != quantity.quantize(Decimal('0.0001')):
                raise ValueError
        except (ValueError, InvalidOperation):
            raise ApplicationError('INVALID_PRD_QUANTITY', f'Row {row_number} needs an explicit nonnegative quantity with at most four decimal places. Blank is not zero.', 422) from None
        row_period = period(target_period or value('period'))
        row_revision = revision_label or str(value('revision') or '').strip().upper()
        revision(row_revision)
        result.append({**identifiers, 'quantity': quantity, 'period': row_period,
                       'revision': row_revision, 'source_row_number': row_number,
                       'uom': str(value('uom') or '').strip(),
                       'plant': str(value('plant') or '').strip()})
    if not result:
        raise ApplicationError('EMPTY_PRD_SOURCE', 'No production-order item rows were found.', 422)
    if len({(r['period'], r['revision']) for r in result}) != 1:
        raise ApplicationError('MIXED_PRD_VERSION', 'Import one planning period and revision at a time.', 422)
    return result
