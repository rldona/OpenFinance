"""Aviso de versión nueva (OF-907).

Solo informa: OpenFinance nunca se actualiza solo. La consulta a GitHub es opcional
(`OPENFINANCE_UPDATE_CHECK`, apagada por defecto) porque revela a GitHub que hay una
instalación en esa IP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[.-]?(?:dev|a|b|rc|alpha|beta)\.?\d*)?$")


@dataclass(frozen=True, slots=True)
class LatestRelease:
    version: str
    """Sin la «v» de la etiqueta: «0.3.0»."""
    url: str
    """Página de la release en GitHub."""


class ReleaseSource(Protocol):
    def latest(self) -> LatestRelease | None:
        """La última release publicada, o ``None`` si no se puede saber."""
        ...


@dataclass(frozen=True, slots=True)
class VersionInfo:
    current: str
    enabled: bool
    latest: str | None
    url: str | None
    update_available: bool


def parse_version(text: str) -> tuple[tuple[int, int, int], bool] | None:
    """(números, es_desarrollo) o ``None`` si no es una versión que entendamos."""
    match = _VERSION.match(text.strip())
    if match is None:
        return None
    numbers = (int(match[1]), int(match[2]), int(match[3]))
    is_dev = match.group(0).lstrip("v") != ".".join(match.groups()[:3])
    return numbers, is_dev


def is_newer(current: str, latest: str) -> bool:
    """Si ``latest`` (una release) es posterior a ``current``. La versión de desarrollo
    0.2.0.dev0 es anterior a la release 0.2.0."""
    cur, new = parse_version(current), parse_version(latest)
    if cur is None or new is None or new[1]:
        return False
    if new[0] != cur[0]:
        return new[0] > cur[0]
    return cur[1]


def version_info(current: str, source: ReleaseSource | None) -> VersionInfo:
    if source is None:
        return VersionInfo(current, False, None, None, False)
    release = source.latest()
    if release is None:
        return VersionInfo(current, True, None, None, False)
    return VersionInfo(
        current, True, release.version, release.url, is_newer(current, release.version)
    )
