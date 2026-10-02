from decimal import Decimal
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.rules.errors import InvalidDenominatorError, ParameterValidationError
from app.domain.rules.types import RoundingPolicy, RuleType


# --- Typed Parameter Models ---

class ProductionRateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rate: Decimal = Field(..., description="Consumption rate per unit of product")
    scrap_factor: Decimal = Field(default=Decimal("0"), description="Scrap allowance factor (e.g. 0.05 for 5%)")

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
    model_config = ConfigDict(extra="forbid")

    area_per_unit: Decimal = Field(..., description="Surface area per unit of product")
    coverage: Decimal = Field(..., description="Area covered per unit of consumable")
    loss_factor: Decimal = Field(default=Decimal("0"), description="Process loss/overspray factor")

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
    model_config = ConfigDict(extra="forbid")

    units_per_pack: Decimal = Field(..., description="Number of product units per pack/box")

    @field_validator("units_per_pack")
    @classmethod
    def validate_units_per_pack(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise InvalidDenominatorError("Units per pack denominator must be strictly greater than zero.")
        return v


class ToolLifeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations_per_unit: Decimal = Field(..., description="Number of tool operations per unit product")
    tool_life: Decimal = Field(..., description="Rated tool life in total operations")

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
    model_config = ConfigDict(extra="forbid")

    quantity: Decimal = Field(..., description="Fixed setup or baseline consumable quantity")

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ParameterValidationError("Fixed quantity must be strictly greater than zero.")
        return v


class PlantRequestParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_quantity: Decimal = Field(default=Decimal("0"), description="Default fallback quantity if not explicitly requested")

    @field_validator("default_quantity")
    @classmethod
    def validate_default(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ParameterValidationError("Default quantity cannot be negative.")
        return v


class MaintenanceParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    min_quantity: Decimal = Field(..., description="Protected lower bound/floor quantity")
    max_quantity: Decimal = Field(..., description="Capped upper bound/ceiling quantity")
    base_rate: Decimal = Field(..., description="Base consumption rate per production unit")

    @model_validator(mode="after")
    def validate_min_max(self) -> "MinMaxParams":
        if self.min_quantity < 0:
            raise ParameterValidationError("Minimum quantity cannot be negative.")
        if self.max_quantity < self.min_quantity:
            raise ParameterValidationError("Maximum quantity must be greater than or equal to minimum quantity.")
        if self.base_rate <= 0:
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
