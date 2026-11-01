"""Limitador de intentos de login en memoria (OF-906).

Suficiente para una instalación doméstica con un único proceso. Si se escala a varios
procesos, hay que mover el contador a la base de datos o al proxy.

- **Atómico**: `try_acquire` comprueba el límite y cuenta el intento en un único paso, antes
  de gastar tiempo en verificar la contraseña. Con comprobar y apuntar por separado, muchas
  peticiones en paralelo pasarían todas la comprobación antes de que ninguna fallara.
- **Acotado**: las claves caducadas se borran al tocarlas y, antes de descartar nada, al llegar
  al máximo de claves (`max_keys`); si aun así no caben, se descartan las más antiguas.
  Sin tope, quien prueba emails inventados haría crecer la memoria sin límite.
"""

from __future__ import annotations

import threading
from collections import deque
from contextlib import suppress
from datetime import datetime, timedelta

Key = tuple[str, str]


class LoginThrottle:
    def __init__(
        self,
        max_per_email: int,
        max_per_ip: int,
        window: timedelta,
        max_keys: int = 10_000,
    ) -> None:
        self._limits = {"email": max_per_email, "ip": max_per_ip}
        self._window = window
        self._max_keys = max_keys
        self._attempts: dict[Key, deque[datetime]] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        """Claves con intentos vivos (para las pruebas y el diagnóstico)."""
        with self._lock:
            return len(self._attempts)

    @staticmethod
    def _keys(email: str, ip: str) -> list[Key]:
        return [("email", email.strip().lower()), ("ip", ip)]

    def _live(self, key: Key, now: datetime) -> deque[datetime] | None:
        """Los intentos de esa clave dentro de la ventana; borra la clave si ya no tiene."""
        attempts = self._attempts.get(key)
        if attempts is None:
            return None
        while attempts and now - attempts[0] > self._window:
            attempts.popleft()
        if not attempts:
            del self._attempts[key]
            return None
        return attempts

    def _make_room(self, needed: int, now: datetime) -> None:
        if len(self._attempts) + needed <= self._max_keys:
            return
        for key in list(self._attempts):
            self._live(key, now)
        while self._attempts and len(self._attempts) + needed > self._max_keys:
            del self._attempts[next(iter(self._attempts))]

    def try_acquire(self, email: str, ip: str, now: datetime) -> bool:
        """Cuenta un intento de login si no se ha superado el límite; si no, devuelve False.

        El intento queda contado aunque aún no se sepa si acertará: quien acierta lo devuelve
        con `release_success`.
        """
        keys = self._keys(email, ip)
        with self._lock:
            for key in keys:
                attempts = self._live(key, now)
                if attempts is not None and len(attempts) >= self._limits[key[0]]:
                    return False
            self._make_room(len(keys), now)
            for key in keys:
                self._attempts.setdefault(key, deque()).append(now)
            return True

    def _refund(self, key: Key, now: datetime) -> None:
        attempts = self._attempts.get(key)
        if attempts is not None:
            with suppress(ValueError):
                attempts.remove(now)
            if not attempts:
                del self._attempts[key]

    def release(self, email: str, ip: str, now: datetime) -> None:
        """Devuelve el intento: no era un fallo de credenciales (p. ej. una contraseña nueva
        demasiado corta), así que no debe acercar a nadie al límite."""
        with self._lock:
            for key in self._keys(email, ip):
                self._refund(key, now)

    def release_success(self, email: str, ip: str, now: datetime) -> None:
        """Tras un login correcto: el email vuelve a cero y la IP recupera este intento."""
        email_key, ip_key = self._keys(email, ip)
        with self._lock:
            self._attempts.pop(email_key, None)
            self._refund(ip_key, now)
