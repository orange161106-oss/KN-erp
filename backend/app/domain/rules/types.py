from enum import Enum


class RuleType(str, Enum):
    PRODUCTION_RATE = "PRODUCTION_RATE"
    AREA_COVERAGE = "AREA_COVERAGE"
    PACKING_RATIO = "PACKING_RATIO"
    TOOL_LIFE = "TOOL_LIFE"
    FIXED_QUANTITY = "FIXED_QUANTITY"
    PLANT_REQUEST = "PLANT_REQUEST"
    MAINTENANCE = "MAINTENANCE"
    MIN_MAX = "MIN_MAX"


class RoundingPolicy(str, Enum):
    NONE = "NONE"
    ROUND_UP = "ROUND_UP"          # Math ceiling
    ROUND_HALF_UP = "ROUND_HALF_UP"  # Standard arithmetic round
    ROUND_DOWN = "ROUND_DOWN"      # Math floor
