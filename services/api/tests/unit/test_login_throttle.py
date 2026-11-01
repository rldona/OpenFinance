"""OF-906: el limitador es atómico y acotado; Argon2 corre en sus propios hilos."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from openfinance.infrastructure.security import Argon2PasswordHasher
from openfinance.infrastructure.throttle import LoginThrottle

NOW = datetime(2026, 11, 1, 12, 0)  # noqa: DTZ001
WINDOW = timedelta(minutes=15)


class TestAtomic:
    def test_parallel_attempts_cannot_overshoot_the_limit(self) -> None:
        throttle = LoginThrottle(5, 1000, WINDOW)
        barrier = threading.Barrier(40)

        def attempt(_: int) -> bool:
            barrier.wait()
            return throttle.try_acquire("victima@example.org", "10.0.0.1", NOW)

        with ThreadPoolExecutor(40) as pool:
            granted = sum(pool.map(attempt, range(40)))
        # Comprobar y contar por separado dejaría pasar a casi todos; aquí pasan exactamente 5.
        assert granted == 5

    def test_a_success_forgets_the_email_and_gives_the_ip_attempt_back(self) -> None:
        throttle = LoginThrottle(3, 2, WINDOW)
        assert throttle.try_acquire("a@b.c", "1.1.1.1", NOW)
        assert throttle.try_acquire("a@b.c", "1.1.1.1", NOW)
        throttle.release_success("a@b.c", "1.1.1.1", NOW)
        # El email empieza de cero; la IP conserva solo el primer intento.
        assert throttle.try_acquire("a@b.c", "1.1.1.1", NOW)
        assert not throttle.try_acquire("c@d.e", "1.1.1.1", NOW)

    def test_a_released_attempt_does_not_count(self) -> None:
        throttle = LoginThrottle(1, 1, WINDOW)
        assert throttle.try_acquire("a@b.c", "1.1.1.1", NOW)
        throttle.release("a@b.c", "1.1.1.1", NOW)
        assert throttle.try_acquire("a@b.c", "1.1.1.1", NOW)


class TestBounded:
    def test_expired_keys_are_dropped_before_evicting_live_ones(self) -> None:
        throttle = LoginThrottle(5, 5, WINDOW, max_keys=10)
        for i in range(5):
            throttle.try_acquire(f"u{i}@b.c", f"10.0.0.{i}", NOW)
        assert len(throttle) == 10
        later = NOW + WINDOW + timedelta(seconds=1)
        assert throttle.try_acquire("nuevo@b.c", "9.9.9.9", later)
        assert len(throttle) == 2  # las diez caducadas se han ido; quedan las dos nuevas

    def test_never_holds_more_than_max_keys(self) -> None:
        throttle = LoginThrottle(5, 5, WINDOW, max_keys=100)
        for i in range(5000):
            throttle.try_acquire(f"inventado{i}@b.c", f"10.{i // 250}.{i % 250}.1", NOW)
        assert len(throttle) <= 100

    def test_a_live_key_is_still_enforced_after_eviction_pressure(self) -> None:
        throttle = LoginThrottle(2, 1000, WINDOW, max_keys=10)
        assert throttle.try_acquire("v@b.c", "1.1.1.1", NOW)
        assert throttle.try_acquire("v@b.c", "1.1.1.1", NOW)
        assert not throttle.try_acquire("v@b.c", "1.1.1.1", NOW)


class TestArgonThreads:
    def test_async_verification_runs_in_its_own_threads(self) -> None:
        hasher = Argon2PasswordHasher()
        seen: list[str] = []
        real = hasher._argon

        class Spy:
            def hash(self, password: str) -> str:
                return real.hash(password)

            def verify(self, password_hash: str, password: str) -> bool:
                seen.append(threading.current_thread().name)
                return real.verify(password_hash, password)

        hasher._argon = Spy()  # type: ignore[assignment]
        password_hash = hasher.hash("contraseña-de-prueba")

        assert asyncio.run(hasher.averify(password_hash, "contraseña-de-prueba")) is True
        assert asyncio.run(hasher.averify(password_hash, "otra")) is False
        assert asyncio.run(hasher.averify(None, "lo que sea")) is False  # usuario inexistente
        assert len(seen) == 3
        assert all(name.startswith("argon2") for name in seen)
