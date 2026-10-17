"""Batched, read-only company monthly purchase inputs; never rewrites approvals."""
from decimal import Decimal
import re

from sqlalchemy import select

from app.domain.purchase_engine.monthly import RULE_VERSION, FORMULA_REFERENCE, calculate_monthly_purchase
from app.models.inventory_masters import Consumable, Unit
from app.models.stock_statements import StockParameter, StockParameterBatch, StockStatementBatch, StockStatementLine
from app.services.stock_management_service import normalize_item_id_key, resolve_stock_parameter_for_item
from app.services.stock_statement_service import UNIT_SYNONYMS


def _unit_matches(left, right):
    """Reuse known label synonyms, but missing/numeric units are never evidence."""
    a, b = (re.sub(r'[^A-Z0-9]', '', str(value or '').upper()) for value in (left, right))
    return bool(a and b and not a.isdigit() and not b.isdigit()
                and (a == b or any(a in labels and b in labels for labels in UNIT_SYNONYMS)))


class MonthlyPurchaseInputs:
    def __init__(self, session, *, month, year, material_ids):
        self.stock_period = f'{year - 1 if month == 1 else year:04d}-{12 if month == 1 else month - 1:02d}'
        self.parameter_period = f'{year:04d}-{month:02d}'
        prev_year, prev_month = map(int, self.stock_period.split('-'))
        self.masters = {material.id: (material, unit) for material, unit in session.execute(
            select(Consumable, Unit).outerjoin(Unit, Unit.id == Consumable.unit_id)
            .where(Consumable.id.in_(material_ids)))} if material_ids else {}
        statements = list(session.scalars(select(StockStatementBatch).where(
            StockStatementBatch.statement_month == prev_month, StockStatementBatch.statement_year == prev_year,
            StockStatementBatch.status == 'active')))
        parameters = list(session.scalars(select(StockParameterBatch).where(
            StockParameterBatch.month == month, StockParameterBatch.year == year,
            StockParameterBatch.status == 'active')))
        self.statement = statements[0] if len(statements) == 1 else None
        self.parameters = parameters[0] if len(parameters) == 1 else None
        self.source_issues = []
        if not self.statement:
            self.source_issues.append(f'{"No" if not statements else "Multiple active"} stock statement for {self.stock_period}.')
        if not self.parameters:
            self.source_issues.append(f'{"No" if not parameters else "Multiple active"} Stock Management upload for {self.parameter_period}.')
        self.lines, self.limits = {}, {}
        if self.statement:
            for line in session.scalars(select(StockStatementLine).where(StockStatementLine.batch_id == self.statement.id)):
                self.lines.setdefault(normalize_item_id_key(line.item_id), []).append(line)
        if self.parameters:
            for param in session.scalars(select(StockParameter).where(StockParameter.batch_id == self.parameters.id)
                                         .order_by(StockParameter.source_row)):
                self.limits.setdefault(normalize_item_id_key(param.item_id), []).append(param)

    def calculate(self, *, material_id, unit_id, uom, required):
        issues = list(self.source_issues)
        master, unit = self.masters.get(material_id, (None, None))
        if not master or not master.is_active:
            issues.append('Active consumable master is required.')
        if not unit or not unit.is_active or unit.id != unit_id or not _unit_matches(unit.code, uom):
            issues.append('Saved requirement unit must match the active Stock Unit in Product Master.')
        code = normalize_item_id_key(master.code) if master else ''
        lines = self.lines.get(code, [])
        stock = None
        if self.statement:
            if not lines:
                issues.append(f'Item is missing from the {self.stock_period} stock statement; missing is not zero stock.')
            else:
                stock_issues = []
                if any(line.closing_qty is None for line in lines):
                    stock_issues.append(f'Closing quantity is blank in the {self.stock_period} stock statement; enter a verified balance (including zero).')
                if any(not _unit_matches(line.unit, uom) for line in lines):
                    stock_issues.append(f'Stock statement unit does not match the calculation unit {uom}; review the {self.stock_period} statement.')
                if any(line.consumable_id and line.consumable_id != material_id for line in lines):
                    stock_issues.append(f'Stock statement item mapping needs review in the {self.stock_period} statement.')
                issues.extend(stock_issues)
                if not stock_issues:
                    # SUMIF in Plan!S4. Apply shared stock once after consolidating product demand.
                    stock = sum((line.closing_qty for line in lines), Decimal('0'))
        param, flag = resolve_stock_parameter_for_item(self.limits.get(code, []))
        if self.parameters and flag:
            issues.append(flag)
        msl, moq = (param.min_stock_level, param.min_order_qty) if param else (None, None)
        if param and (msl is None or moq is None):
            issues.append('Both MSL and MOQ must be entered in the selected month\'s Stock Management upload (zero is allowed).')
        rate = master.rate if master and master.rate is not None and master.rate >= 0 else None
        result = {'raw_quantity': None, 'recommended_quantity': None, 'purchase_value': None}
        if not issues:
            try:
                result = calculate_monthly_purchase(required=required, closing_stock=stock, msl=msl, moq=moq, rate=rate)
            except ValueError as error:
                issues.append(str(error))
        movement = lines[0] if len(lines) == 1 else None
        return dict(**result, stock_qty=stock, minimum_stock_level=msl, minimum_order_qty=moq,
                    category=master.category if master else None,
                    type_of_material=master.type_of_material if master else None,
                    output_unit=master.output_unit if master else None,
                    max_stock_level=param.max_stock_level if param else None,
                    lead_time_days=param.lead_time_days if param else None,
                    opening_qty=movement.opening_qty if movement else None,
                    opening_value=movement.opening_value if movement else None,
                    receipt_qty=movement.receipt_qty if movement else None,
                    receipt_value=movement.receipt_value if movement else None,
                    issue_qty=movement.issue_qty if movement else None,
                    closing_value=movement.closing_value if movement else None,
                    unit_rate=rate, calculation_basis=RULE_VERSION, stock_period=self.stock_period,
                    input_issues=issues, calculation_details=(
                        f'{FORMULA_REFERENCE}. MSL + requirement − {self.stock_period} closing stock; '
                        'positive gap is raised to MOQ; otherwise zero. Pending POs are not deducted. '
                        'No pack rounding or maximum cap. MSL/MOQ: uploaded Stock Management '
                        f'{self.parameter_period} ({self.parameters.source_filename if self.parameters else "not uploaded"}); '
                        f'stock file: {self.statement.source_filename if self.statement else "not uploaded"}. ' + (' '.join(issues) if issues else
                        f'{msl} + {required} − {stock} = {result["raw_quantity"]}; order {result["recommended_quantity"]}.') +
                        (' Rate is missing in Product Master; purchase value is unavailable.' if rate is None else '')),
                    calculation_sources={
                        'formula_reference': FORMULA_REFERENCE,
                        'stock_batch_id': str(self.statement.id) if self.statement else None,
                        'stock_filename': self.statement.source_filename if self.statement else None,
                        'stock_file_hash': self.statement.file_hash if self.statement else None,
                        'stock_line_ids': [str(line.id) for line in lines],
                        'parameter_batch_id': str(self.parameters.id) if self.parameters else None,
                        'parameter_filename': self.parameters.source_filename if self.parameters else None,
                        'parameter_file_hash': self.parameters.file_hash if self.parameters else None,
                        'parameter_id': str(param.id) if param else None,
                        'parameter_period': self.parameter_period,
                        'rate_source': 'Product Master',
                    })
