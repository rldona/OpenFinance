"""Adjuntos de un movimiento: tickets y facturas (OF-1007).

Solo PDF e imágenes (PNG, JPEG, WebP), reconocidos por su contenido y no por lo que diga el
navegador. Nada de SVG ni HTML: un adjunto se descarga, no se ejecuta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from openfinance.domain.shared.ids import TransactionId, UserId, WorkspaceId

MAX_BYTES = 5 * 1024 * 1024
MAX_PER_TRANSACTION = 10
MAX_FILENAME = 100

AttachmentId = UUID


class AttachmentError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Attachment:
    id: AttachmentId
    household_id: WorkspaceId
    transaction_id: TransactionId
    filename: str
    content_type: str
    size: int
    sha256: str
    created_by: UserId
    created_at: datetime
    deleted_at: datetime | None = None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


def sniff(content: bytes) -> tuple[str, str] | None:
    """(tipo, extensión) según los primeros bytes, o ``None`` si no es un tipo admitido."""
    if content.startswith(b"%PDF-"):
        return "application/pdf", "pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def clean_filename(name: str, extension: str) -> str:
    """Un nombre seguro para mostrar y para descargar: sin rutas, sin caracteres de control y
    con la extensión del tipo real."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[\x00-\x1f\x7f\"<>|:*?]", "", base).strip(" .")
    stem = base.rsplit(".", 1)[0] if "." in base else base
    stem = " ".join(stem.split())[: MAX_FILENAME - len(extension) - 1] or "adjunto"
    return f"{stem}.{extension}"


def validate(content: bytes) -> tuple[str, str]:
    if not content:
        raise AttachmentError("El archivo está vacío")
    if len(content) > MAX_BYTES:
        raise AttachmentError("El archivo es demasiado grande (máximo 5 MB)")
    kind = sniff(content)
    if kind is None:
        raise AttachmentError("Solo se admiten PDF e imágenes PNG, JPEG o WebP")
    return kind
