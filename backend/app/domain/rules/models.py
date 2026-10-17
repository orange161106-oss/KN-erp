from decimal import Decimal
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.rules.errors import InvalidDenominatorError, ParameterValidationError
from app.domain.rules.types import RoundingPolicy, RuleType


# --- Typed Parameter Models ---

class ProductionRateParams(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    rate: Decimal = Field(..., description="Consumption rate per unit of product")
    scrap_factor: Decimal = Field(default=Decimal("0"), description="Scrap allowance factor (e.g. 0.05 for 5%)")

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "consumption_rate" in data and "rate" not in data:
                data["rate"] = data["consumption_rate"]
            elif "rate" in data and "consumption_rate" not in data:
                data["consumption_rate"] = data["rate"]
        return data

    @field_validator("rate")
    @classmethod
    def validate_rate(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ParameterValidationError("Production rate must be greater than zero.")
        return v

    @field_validator("scrap_factor")
    @classmethod
    def validate_scrap(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ParameterValidationError("Scrap factor cannot be negative.")
        return v


class AreaCoverageParams(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    area_per_unit: Decimal = Field(default=Decimal("1"), description="Surface area per unit of product")
    coverage: Decimal = Field(..., description="Area covered per unit of consumable")
    loss_factor: Decimal = Field(default=Decimal("0"), description="Process loss/overspray factor")

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "overspray_factor" in data and "loss_factor" not in data:
                data["loss_factor"] = data["overspray_factor"]
            if "coverage_per_unit" in data and "coverage" not in data:
                data["coverage"] = data["coverage_per_unit"]
        return data

    @field_validator("area_per_unit")
    @classmethod
    def validate_area(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ParameterValidationError("Area per unit must be greater than zero.")
        return v

    @field_validator("coverage")
    @classmethod
    def validate_coverage(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise InvalidDenominatorError("Coverage denominator must be strictly greater than zero.")
        return v

    @field_validator("loss_factor")
    @classmethod
    def validate_loss(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ParameterValidationError("Loss factor cannot be negative.")
        return v


class PackingRatioParams(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    units_per_pack: Decimal = Field(..., description="Number of product units per pack/box")
    material_per_pack: Decimal = Field(default=Decimal("1"), description="Multiplier of material per pack")

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "pieces_per_pack" in data and "units_per_pack" not in data:
                data["units_per_pack"] = data["pieces_per_pack"]
            elif "units_per_pack" in data and "pieces_per_pack" not in data:
                data["pieces_per_pack"] = data["units_per_pack"]
        return data

    @field_validator("units_per_pack")
    @classmethod
    def validate_units_per_pack(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise InvalidDenominatorError("Units per pack denominator must be strictly greater than zero.")
        return v

    @field_validator("material_per_pack")
    @classmethod
    def validate_material_per_pack(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ParameterValidationError("Material per pack must be greater than zero.")
        return v


class ToolLifeParams(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    operations_per_unit: Decimal = Field(default=Decimal("1"), description="Number of tool operations per unit product")
    tool_life: Decimal = Field(..., description="Rated tool life in total operations")

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "operations_per_part" in data and "operations_per_unit" not in data:
                data["operations_per_unit"] = data["operations_per_part"]
            elif "operations_per_unit" in data and "operations_per_part" not in data:
                data["operations_per_part"] = data["operations_per_unit"]
        return data

    @field_validator("operations_per_unit")
    @classmethod
    def validate_ops(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ParameterValidationError("Operations per unit must be greater than zero.")
        return v

    @field_validator("tool_life")
    @classmethod
    def validate_tool_life(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise InvalidDenominatorError("Tool life denominator must be strictly greater than zero.")
        return v


class FixedQuantityParams(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    quantity: Decimal = Field(..., description="Fixed setup or baseline consumable quantity")

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "fixed_quantity" in data and "quantity" not in data:
                data["quantity"] = data["fixed_quantity"]
            elif "quantity" in data and "fixed_quantity" not in data:
                data["fixed_quantity"] = data["quantity"]
        return data

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ParameterValidationError("Fixed quantity must be strictly greater than zero.")
        return v


class PlantRequestParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    default_quantity: Decimal = Field(default=Decimal("0"), description="Default fallback quantity if not explicitly requested")
    department_requests: Optional[dict[str, Decimal]] = Field(default=None, description="Department-wise requests breakdown")

    @field_validator("default_quantity")
    @classmethod
    def validate_default(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ParameterValidationError("Default quantity cannot be negative.")
        return v

    @field_validator("department_requests")
    @classmethod
    def validate_dept_requests(cls, v: Optional[dict[str, Decimal]]) -> Optional[dict[str, Decimal]]:
        if v is not None:
            for dept, qty in v.items():
                if qty < 0:
                    raise ParameterValidationError(f"Request quantity for '{dept}' cannot be negative.")
        return v


class MaintenanceParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fixed_amount: Decimal = Field(default=Decimal("0"), description="Periodic baseline maintenance amount")
    variable_rate: Decimal = Field(default=Decimal("0"), description="Variable maintenance rate per production unit")

    @model_validator(mode="after")
    def validate_maintenance(self) -> "MaintenanceParams":
        if self.fixed_amount < 0 or self.variable_rate < 0:
            raise ParameterValidationError("Maintenance fixed amount and variable rate cannot be negative.")
        if self.fixed_amount == 0 and self.variable_rate == 0:
            raise ParameterValidationError("Maintenance rule must have at least fixed amount or variable rate > 0.")
        return self


class MinMaxParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # KNL-Verified Stock Policy Parameters:
    msl_days: Decimal = Field(default=Decimal("10"), description="Number of days of requirement kept as minimum stock (MSL)")
    working_days: Decimal = Field(default=Decimal("26"), description="Working days in month used to calculate daily requirement")
    lead_time_days: Decimal = Field(default=Decimal("0"), description="Supplier lead time in days")
    moq: Decimal = Field(default=Decimal("0"), description="Minimum Order Quantity")
    order_multiple: Decimal = Field(default=Decimal("0"), description="Pack size / order multiple")
    current_stock: Decimal = Field(default=Decimal("0"), description="Current / closing stock on hand")
    incoming_po: Decimal = Field(default=Decimal("0"), description="Confirmed incoming PO quantity")
    monthly_requirement: Optional[Decimal] = Field(default=None, description="Explicit monthly requirement if not derived from production")

    # Optional / Legacy compatibility fields:
    min_quantity: Optional[Decimal] = Field(default=None, description="Explicit minimum stock level override if configured")
    max_quantity: Optional[Decimal] = Field(default=None, description="Explicit maximum stock level override if configured")
    base_rate: Optional[Decimal] = Field(default=None, description="Base consumption rate per production unit if requirement derived")

    @model_validator(mode="after")
    def validate_min_max(self) -> "MinMaxParams":
        if self.working_days <= 0:
            raise InvalidDenominatorError("Working days denominator must be strictly greater than zero.")
        if self.msl_days < 0:
            raise ParameterValidationError("MSL days cannot be negative.")
        if self.lead_time_days < 0:
            raise ParameterValidationError("Lead time days cannot be negative.")
        if self.moq < 0:
            raise ParameterValidationError("MOQ cannot be negative.")
        if self.order_multiple < 0:
            raise ParameterValidationError("Order multiple cannot be negative.")
        if self.current_stock < 0:
            raise ParameterValidationError("Current stock cannot be negative.")
        if self.incoming_po < 0:
            raise ParameterValidationError("Incoming PO cannot be negative.")
        if self.min_quantity is not None and self.min_quantity < 0:
            raise ParameterValidationError("Minimum quantity cannot be negative.")
        if self.max_quantity is not None and self.min_quantity is not None and self.max_quantity < self.min_quantity:
            raise ParameterValidationError("Maximum quantity must be greater than or equal to minimum quantity.")
        if self.base_rate is not None and self.base_rate <= 0:
            raise ParameterValidationError("Base rate must be strictly greater than zero.")
        return self


# --- Input and Output Execution Contracts ---

class RuleCalculationInput(BaseModel):
    rule_type: RuleType
    rule_version: int = 1
    parameters: dict[str, Any]
    production_quantity: Decimal = Decimal("0")
    rounding_policy: RoundingPolicy = RoundingPolicy.NONE
    rounding_precision: int = 2
    unit: str = "PCS"
    requested_quantity: Optional[Decimal] = None
    # Stock policy & departmental contextual inputs:
    current_stock: Optional[Decimal] = None
    incoming_po: Optional[Decimal] = None
    department_requests: Optional[dict[str, Decimal]] = None


class CalculationStep(BaseModel):
    step_number: int
    description: str
    formula: str
    result: Decimal


class CalculationResult(BaseModel):
    rule_type: RuleType
    rule_version: int
    parameters: dict[str, Any]
    source_production_qty: Decimal
    calculation_steps: list[CalculationStep]
    raw_requirement: Decimal
    rounding_policy: RoundingPolicy
    rounding_precision: int
    final_calculated_requirement: Decimal
    unit: str
    metadata: Optional[dict[str, Any]] = None
