"""Limitador de intentos de login en memoria.

Suficiente para una instalación doméstica con un único proceso. Si se escala a varios
procesos, hay que mover el contador a la base de datos o al proxy.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta


class LoginThrottle:
    def __init__(self, max_per_email: int, max_per_ip: int, window: timedelta) -> None:
        self._limits = {"email": max_per_email, "ip": max_per_ip}
        self._window = window
        self._failures: dict[tuple[str, str], deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _keys(self, email: str, ip: str) -> list[tuple[str, str]]:
        return [("email", email.strip().lower()), ("ip", ip)]

    def _prune(self, key: tuple[str, str], now: datetime) -> deque[datetime]:
        q = self._failures[key]
        while q and now - q[0] > self._window:
            q.popleft()
        return q

    def is_blocked(self, email: str, ip: str, now: datetime) -> bool:
        with self._lock:
            return any(
                len(self._prune(k, now)) >= self._limits[k[0]] for k in self._keys(email, ip)
            )

    def record_failure(self, email: str, ip: str, now: datetime) -> None:
        with self._lock:
            for k in self._keys(email, ip):
                self._prune(k, now).append(now)

    def reset(self, email: str) -> None:
        with self._lock:
            self._failures.pop(("email", email.strip().lower()), None)
