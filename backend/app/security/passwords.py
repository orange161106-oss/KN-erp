import secrets
from typing import Optional

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

try:
    from pwdlib.hashers.bcrypt import BcryptHasher
    # Work factor configured to 12 rounds for optimal performance (<150ms)
    # preventing CPU hanging or DoS while ensuring robust entropy.
    _default_hasher = PasswordHash((Argon2Hasher(), BcryptHasher(rounds=12)))
except Exception:
    _default_hasher = PasswordHash.recommended()

# Precomputed once at module load so PasswordService instantiation is instantaneous
_DUMMY_HASH = _default_hasher.hash(secrets.token_urlsafe(32))


class PasswordService:
    def __init__(self, hasher: Optional[PasswordHash] = None) -> None:
        self._hasher = hasher or _default_hasher
        self._dummy_hash = _DUMMY_HASH

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password, password_hash)
        except (UnknownHashError, ValueError):
            # Corrupt/unsupported stored hashes fail closed, without revealing them.
            self.verify_dummy(password)
            return False

    def verify_dummy(self, password: str) -> None:
        self._hasher.verify(password, self._dummy_hash)
