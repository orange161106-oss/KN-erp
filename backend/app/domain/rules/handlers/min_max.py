from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from app.domain.rules.handlers.base import BaseRuleHandler
from app.domain.rules.models import CalculationStep, MinMaxParams, RuleCalculationInput


class MinMaxHandler(BaseRuleHandler):
    def calculate(self, input_data: RuleCalculationInput) -> tuple[Decimal, list[CalculationStep]]:
        params = MinMaxParams.model_validate(input_data.parameters)
        steps: list[CalculationStep] = []

        # Legacy fallback if explicitly configuring clamp bounds
        if (
            params.min_quantity is not None
            and params.max_quantity is not None
            and params.base_rate is not None
            and "msl_days" not in input_data.parameters
            and "moq" not in input_data.parameters
            and "current_stock" not in input_data.parameters
        ):
            nominal = input_data.production_quantity * params.base_rate
            steps.append(
                CalculationStep(
                    step_number=1,
                    description="Calculate nominal requirement using base consumption rate",
                    formula=f"{input_data.production_quantity} * {params.base_rate}",
                    result=nominal,
                )
            )
            capped = min(params.max_quantity, nominal)
            steps.append(
                CalculationStep(
                    step_number=2,
                    description=f"Apply ceiling cap (max {params.max_quantity})",
                    formula=f"min({params.max_quantity}, {nominal})",
                    result=capped,
                )
            )
            raw_qty = max(params.min_quantity, capped)
            steps.append(
                CalculationStep(
                    step_number=3,
                    description=f"Apply protected floor (min {params.min_quantity})",
                    formula=f"max({params.min_quantity}, {capped})",
                    result=raw_qty,
                )
            )
            return raw_qty, steps

        # --- KNL-Verified Stock Policy & Purchase Calculation (Sections 12 & 13) ---
        # 1. Determine monthly requirement
        if params.monthly_requirement is not None:
            monthly_req = params.monthly_requirement
        elif params.base_rate is not None and input_data.production_quantity > 0:
            monthly_req = input_data.production_quantity * params.base_rate
        elif input_data.production_quantity > 0:
            monthly_req = input_data.production_quantity
        elif input_data.requested_quantity is not None:
            monthly_req = input_data.requested_quantity
        else:
            monthly_req = Decimal("0")

        # 2. Daily requirement = monthly requirement / working days
        daily_req = monthly_req / params.working_days
        steps.append(
            CalculationStep(
                step_number=1,
                description=f"Calculate daily requirement from monthly requirement ({monthly_req}) over {params.working_days} working days",
                formula=f"{monthly_req} / {params.working_days}",
                result=daily_req,
            )
        )

        # 3. Minimum Stock Level (MSL) = ROUNDUP(daily requirement * MSL days, 0)
        msl_raw = daily_req * params.msl_days
        msl = msl_raw.quantize(Decimal("1"), rounding=ROUND_CEILING)
        steps.append(
            CalculationStep(
                step_number=2,
                description=f"Calculate Minimum Stock Level (MSL = ROUNDUP(daily_requirement * {params.msl_days} days, 0))",
                formula=f"ROUNDUP({daily_req} * {params.msl_days}, 0)",
                result=msl,
            )
        )

        # 4. Lead Time Quantity = ROUND(daily requirement * lead time days, 0)
        if params.lead_time_days > Decimal("0"):
            lead_time_qty = (daily_req * params.lead_time_days).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            steps.append(
                CalculationStep(
                    step_number=len(steps) + 1,
                    description=f"Calculate Lead Time Quantity for {params.lead_time_days} days",
                    formula=f"ROUND({daily_req} * {params.lead_time_days}, 0)",
                    result=lead_time_qty,
                )
            )
            reorder_level = msl + lead_time_qty
            steps.append(
                CalculationStep(
                    step_number=len(steps) + 1,
                    description="Calculate Re-order Level (MSL + Lead Time Quantity)",
                    formula=f"{msl} + {lead_time_qty}",
                    result=reorder_level,
                )
            )

        # 5. Maximum Stock Level = MSL + MOQ
        if params.moq > Decimal("0"):
            max_stock_level = msl + params.moq
            steps.append(
                CalculationStep(
                    step_number=len(steps) + 1,
                    description=f"Calculate Maximum Stock Level (MSL + MOQ of {params.moq})",
                    formula=f"{msl} + {params.moq}",
                    result=max_stock_level,
                )
            )

        # 6. Supply netting: Available Supply = Current Stock + Confirmed Incoming PO (Section 13)
        curr_stock = input_data.current_stock if input_data.current_stock is not None else params.current_stock
        inc_po = input_data.incoming_po if input_data.incoming_po is not None else params.incoming_po
        available_supply = curr_stock + inc_po
        steps.append(
            CalculationStep(
                step_number=len(steps) + 1,
                description="Calculate Available Supply = Current Stock + Confirmed Incoming PO",
                formula=f"{curr_stock} + {inc_po}",
                result=available_supply,
            )
        )

        # 7. Gross Purchase Need = MSL + Monthly Requirement - Available Supply
        gross_need = msl + monthly_req - available_supply
        steps.append(
            CalculationStep(
                step_number=len(steps) + 1,
                description="Calculate Gross Purchase Need = MSL + Monthly Requirement - Available Supply",
                formula=f"{msl} + {monthly_req} - {available_supply}",
                result=gross_need,
            )
        )

        # 8. Order Quantity with MOQ and Multiple
        if gross_need <= Decimal("0"):
            order_qty = Decimal("0")
            steps.append(
                CalculationStep(
                    step_number=len(steps) + 1,
                    description="Gross need <= 0, no additional purchase order required",
                    formula=f"max(0, {gross_need})",
                    result=order_qty,
                )
            )
        else:
            if params.moq > Decimal("0") and gross_need < params.moq:
                order_qty = params.moq
                steps.append(
                    CalculationStep(
                        step_number=len(steps) + 1,
                        description=f"Gross need ({gross_need}) below MOQ ({params.moq}); raised to MOQ",
                        formula=f"max({gross_need}, {params.moq})",
                        result=order_qty,
                    )
                )
            else:
                order_qty = gross_need

            if params.order_multiple > Decimal("0"):
                units = (order_qty / params.order_multiple).quantize(Decimal("1"), rounding=ROUND_CEILING)
                multiplied_qty = units * params.order_multiple
                steps.append(
                    CalculationStep(
                        step_number=len(steps) + 1,
                        description=f"Apply pack multiple of {params.order_multiple}",
                        formula=f"ceil({order_qty} / {params.order_multiple}) * {params.order_multiple}",
                        result=multiplied_qty,
                    )
                )
                order_qty = multiplied_qty

        return order_qty, steps
