"""Archivos de los adjuntos en disco (OF-1007).

El nombre en disco es siempre el identificador del adjunto (nunca algo que mande el cliente), en
dos niveles de carpetas para no llenar una sola. Se escribe a un temporal con permisos 600 y se
renombra al final: nunca queda un archivo a medias con el nombre bueno.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from uuid import UUID


class FileAttachmentStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, attachment_id: UUID) -> Path:
        hexed = attachment_id.hex
        return self._root / hexed[:2] / hexed[2:4] / hexed

    def save(self, attachment_id: UUID, content: bytes) -> None:
        path = self._path(attachment_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_suffix(".part")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise
        tmp.replace(path)

    def read(self, attachment_id: UUID) -> bytes | None:
        try:
            return self._path(attachment_id).read_bytes()
        except FileNotFoundError:
            return None

    def delete(self, attachment_id: UUID) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._path(attachment_id).unlink()
