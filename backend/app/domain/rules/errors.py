class RuleDomainError(Exception):
    """Base exception for rule domain calculations and validations."""

    def __init__(self, message: str, code: str = "RULE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class ParameterValidationError(RuleDomainError):
    """Raised when rule parameters fail validation or are missing required keys."""

    def __init__(self, message: str):
        super().__init__(message, code="PARAMETER_VALIDATION_ERROR")


class InvalidDenominatorError(RuleDomainError):
    """Raised when a division denominator is zero or negative."""

    def __init__(self, message: str):
        super().__init__(message, code="INVALID_DENOMINATOR")


class InactiveRuleError(RuleDomainError):
    """Raised when attempting to calculate using an inactive rule."""

    def __init__(self, message: str = "Rule is inactive and cannot be used for calculation."):
        super().__init__(message, code="INACTIVE_RULE")


class MissingRuleError(RuleDomainError):
    """Raised when no applicable rule exists for a requested item/process."""

    def __init__(self, message: str = "No matching consumption rule/norm found."):
        super().__init__(message, code="MISSING_RULE")


class RuleExpiredError(RuleDomainError):
    """Raised when a rule is outside its effective validity date range."""

    def __init__(self, message: str = "Rule is not effective for the requested date."):
        super().__init__(message, code="RULE_EXPIRED")
