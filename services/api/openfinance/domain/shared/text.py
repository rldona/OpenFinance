import unicodedata


def normalize_text(text: str) -> str:
    """Mayúsculas, sin tildes y con espacios simples: base estable para comparar conceptos."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(ascii_only.upper().split())
