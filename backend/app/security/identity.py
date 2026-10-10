def normalize_username(value: str) -> str:
    """Apply the same username normalization for storage and login lookup."""
    return value.strip().casefold()
