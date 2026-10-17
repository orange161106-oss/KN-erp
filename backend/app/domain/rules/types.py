from enum import Enum
from typing import Any


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
    ROUND = "ROUND"
    ROUND_HALF_UP = "ROUND_HALF_UP"  # Standard arithmetic round
    ROUND_UP = "ROUND_UP"          # Math ceiling
    ROUNDUP = "ROUNDUP"            # Math ceiling alias
    ROUND_DOWN = "ROUND_DOWN"      # Math floor
    ROUNDDOWN = "ROUNDDOWN"        # Math floor alias
    CEILING = "CEILING"            # Ceiling alias
    FLOOR = "FLOOR"                # Floor alias

    @classmethod
    def parse(cls, value: Any) -> "RoundingPolicy":
        if isinstance(value, cls):
            return value
        if not value:
            return cls.NONE
        norm = str(value).upper().strip().replace(" ", "_").replace("-", "_")
        alias_map = {
            "NONE": cls.NONE,
            "ROUND": cls.ROUND,
            "ROUND_HALF_UP": cls.ROUND_HALF_UP,
            "ROUNDUP": cls.ROUNDUP,
            "ROUND_UP": cls.ROUND_UP,
            "ROUNDDOWN": cls.ROUNDDOWN,
            "ROUND_DOWN": cls.ROUND_DOWN,
            "CEILING": cls.CEILING,
            "FLOOR": cls.FLOOR,
        }
        return alias_map.get(norm, cls.NONE)
