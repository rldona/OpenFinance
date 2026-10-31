import threading

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError

# Cada verificación usa ~64 MiB; limitar la concurrencia evita agotar la memoria
# de un servidor doméstico con peticiones de login en paralelo.
_MAX_CONCURRENT_VERIFICATIONS = 2


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._argon = _Argon2()
        self._dummy = self._argon.hash("openfinance-dummy-password")
        self._slots = threading.BoundedSemaphore(_MAX_CONCURRENT_VERIFICATIONS)

    def hash(self, password: str) -> str:
        with self._slots:
            return self._argon.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        with self._slots:
            try:
                return self._argon.verify(password_hash, password)
            except (VerificationError, InvalidHashError):
                return False

    def dummy_verify(self, password: str) -> None:
        self.verify(self._dummy, password)
