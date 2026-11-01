"""Consulta la última release de GitHub, con caché (OF-907)."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from openfinance.application.updates import LatestRelease, parse_version

logger = logging.getLogger(__name__)

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TIMEOUT_SECONDS = 3
_MAX_BYTES = 256 * 1024
_RETRY_AFTER_FAILURE = 3600.0


class GithubLatestRelease:
    """`GET /repos/{repo}/releases/latest` (no incluye borradores ni prereleases).

    No envía nada de la instalación: ni versión, ni identificador, ni datos. Guarda el
    resultado `ttl_seconds` y, si falla, no vuelve a intentarlo hasta pasada una hora.
    """

    def __init__(
        self,
        repo: str,
        ttl_seconds: float = 86400.0,
        clock: Callable[[], float] = time.monotonic,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        if not _REPO.match(repo):
            raise ValueError(f"Repositorio no válido: {repo}")
        self._repo = repo
        self._ttl = ttl_seconds
        self._clock = clock
        self._opener = opener
        self._lock = threading.Lock()
        self._expires_at = 0.0
        self._cached: LatestRelease | None = None

    def latest(self) -> LatestRelease | None:
        with self._lock:
            now = self._clock()
            if now < self._expires_at:
                return self._cached
            try:
                self._cached = self._fetch()
                self._expires_at = now + self._ttl
            except Exception:  # sin red, límite de GitHub, respuesta rara…
                logger.warning("No se ha podido consultar la última versión", exc_info=True)
                self._cached = None
                self._expires_at = now + _RETRY_AFTER_FAILURE
            return self._cached

    def _fetch(self) -> LatestRelease | None:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{self._repo}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "OpenFinance"},
        )
        with self._opener(request, timeout=_TIMEOUT_SECONDS) as response:  # type: ignore[attr-defined]
            data = json.loads(response.read(_MAX_BYTES))
        tag = str(data.get("tag_name", ""))
        parsed = parse_version(tag)
        if parsed is None or parsed[1]:
            return None
        url = str(data.get("html_url", ""))
        # El enlace se muestra en la web: solo vale si apunta al repositorio.
        if not url.startswith(f"https://github.com/{self._repo}/"):
            return None
        return LatestRelease(tag.lstrip("v"), url)
