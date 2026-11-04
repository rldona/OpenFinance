"""Cliente de Enable Banking, el agregador PSD2 (ADR-0024, OF-1401).

Solo biblioteca estándar y ``cryptography``. Cada petición lleva un JWT RS256 de una hora
firmado con la clave de la aplicación. Los errores se traducen a ``AggregatorError`` con un
mensaje para la persona: nunca llevan el cuerpo de la respuesta, el token ni la sesión.
"""

from __future__ import annotations

import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from openfinance.application.errors import AggregatorError
from openfinance.domain.bank import BankAccountRef, RemoteBalance, RemoteTransaction
from openfinance.domain.shared import Currency, Money
from openfinance.infrastructure.config import Settings

log = logging.getLogger(__name__)
BASE_URL = "https://api.enablebanking.com"
TIMEOUT_SECONDS = 20
TOKEN_SECONDS = 3600
MAX_PAGES = 20
"""Tope de páginas por cuenta: un banco que no para de dar continuación no cuelga todo."""
_BALANCE_ORDER = ("CLBD", "ITBD", "XPCD", "OPBD", "ITAV", "CLAV")
"""Saldo contable al cierre primero; luego el provisional."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _load_key(pem: str) -> rsa.RSAPrivateKey:
    key = serialization.load_pem_private_key(pem.replace("\\n", "\n").encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("La clave de Enable Banking debe ser RSA")
    return key


def sign_jwt(app_id: str, key: rsa.RSAPrivateKey, now: float) -> str:
    header = {"typ": "JWT", "alg": "RS256", "kid": app_id}
    claims = {
        "iss": "enablebanking.com",
        "aud": "api.enablebanking.com",
        "iat": int(now),
        "exp": int(now) + TOKEN_SECONDS,
    }
    signing_input = ".".join(
        _b64(json.dumps(part, separators=(",", ":")).encode()) for part in (header, claims)
    )
    signature = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64(signature)}"


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_transaction(raw: Mapping[str, Any]) -> RemoteTransaction | None:
    """Un movimiento del agregador, o ``None`` si no se puede leer (no se inventa nada)."""
    amount_block = raw.get("transaction_amount") or {}
    amount = _decimal(amount_block.get("amount"))
    currency = amount_block.get("currency")
    when = raw.get("booking_date") or raw.get("value_date") or raw.get("transaction_date")
    if amount is None or not currency or not when:
        return None
    try:
        booked_on = date.fromisoformat(str(when)[:10])
    except ValueError:
        return None
    # El importe llega en positivo y el sentido en credit_debit_indicator.
    signed = -abs(amount) if raw.get("credit_debit_indicator") == "DBIT" else abs(amount)
    remittance = raw.get("remittance_information") or []
    counterparty = (raw.get("creditor") or {}).get("name") or (raw.get("debtor") or {}).get("name")
    parts = [str(p) for p in remittance if p] or ([str(counterparty)] if counterparty else [])
    if counterparty and str(counterparty) not in parts:
        parts.insert(0, str(counterparty))
    entry = raw.get("entry_reference") or raw.get("transaction_id")
    return RemoteTransaction(
        entry_id=str(entry) if entry else None,
        booked_on=booked_on,
        amount=signed,
        currency=str(currency),
        description=" · ".join(parts),
    )


def parse_balance(payload: Mapping[str, Any]) -> RemoteBalance | None:
    by_type = {b.get("balance_type"): b for b in payload.get("balances") or []}
    for kind in _BALANCE_ORDER:
        block = by_type.get(kind)
        if block is None:
            continue
        amount = _decimal((block.get("balance_amount") or {}).get("amount"))
        code = (block.get("balance_amount") or {}).get("currency")
        if amount is None or not code:
            continue
        at = block.get("reference_date") or block.get("last_change_date_time")
        try:
            moment = datetime.fromisoformat(str(at).replace("Z", "+00:00")) if at else None
        except ValueError:
            moment = None
        if moment is None:
            moment = datetime.now(UTC)
        elif moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return RemoteBalance(Money(amount, Currency(str(code))), moment)
    return None


class EnableBankingAggregator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._key = _load_key(settings.bank_private_key) if settings.bank_enabled else None

    @property
    def enabled(self) -> bool:
        return self._key is not None

    def _call(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, object] | None = None,
        query: Mapping[str, str] | None = None,
    ) -> Any:
        if self._key is None:
            raise AggregatorError("La conexión con el banco no está configurada")
        url = BASE_URL + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = json.dumps(body).encode() if body is not None else None
        token = sign_jwt(self._settings.bank_app_id, self._key, time.time())
        request = urllib.request.Request(  # noqa: S310 - la URL base es fija y https
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
                raw = response.read()
        except urllib.error.HTTPError as exc:
            log.warning("Enable Banking respondió %s a %s %s", exc.code, method, path.split("?")[0])
            raise AggregatorError(_http_message(exc.code)) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            log.warning("No se pudo contactar con Enable Banking (%s)", method)
            raise AggregatorError(
                "No se pudo contactar con el banco; inténtalo más tarde"
            ) from None
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            raise AggregatorError("Respuesta no válida del banco") from None

    def banks(self, country: str) -> list[str]:
        reply = self._call("GET", "/aspsps", query={"country": country})
        names = {str(b["name"]) for b in reply.get("aspsps") or [] if b.get("name")}
        return sorted(names, key=str.casefold)

    def start(self, aspsp: str, country: str, state: str, valid_until: datetime) -> str:
        reply = self._call(
            "POST",
            "/auth",
            body={
                "access": {"valid_until": valid_until.astimezone(UTC).isoformat()},
                "aspsp": {"name": aspsp, "country": country},
                "state": state,
                "redirect_url": self._settings.bank_redirect_url,
                "psu_type": "personal",
            },
        )
        url = reply.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise AggregatorError("El banco no devolvió una dirección de autorización")
        return url

    def authorize(self, code: str) -> tuple[str, list[BankAccountRef], datetime]:
        reply = self._call("POST", "/sessions", body={"code": code})
        session_id = reply.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise AggregatorError("El banco no devolvió la sesión")
        accounts = []
        for raw in reply.get("accounts") or []:
            iban = str((raw.get("account_id") or {}).get("iban") or "")
            uid = raw.get("uid")
            if not uid:
                continue
            accounts.append(
                BankAccountRef(
                    str(uid),
                    iban[-4:],
                    str(raw.get("name") or raw.get("product") or "Cuenta")[:100],
                    str(raw.get("currency") or ""),
                )
            )
        until = (reply.get("access") or {}).get("valid_until")
        try:
            valid_until = datetime.fromisoformat(str(until).replace("Z", "+00:00"))
        except ValueError:
            raise AggregatorError(
                "El banco no indicó hasta cuándo vale el consentimiento"
            ) from None
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        return session_id, accounts, valid_until

    def transactions(
        self, session_id: str, remote_uid: str, since: date
    ) -> list[RemoteTransaction]:
        # La sesión va implícita en la cuenta (uid); se conserva en la firma del puerto
        # porque otros agregadores sí la piden en cada llamada.
        found: list[RemoteTransaction] = []
        query = {"date_from": since.isoformat(), "transaction_status": "BOOK"}
        for _ in range(MAX_PAGES):
            reply = self._call(
                "GET",
                f"/accounts/{urllib.parse.quote(remote_uid, safe='')}/transactions",
                query=query,
            )
            for raw in reply.get("transactions") or []:
                parsed = parse_transaction(raw)
                if parsed is not None:
                    found.append(parsed)
            key = reply.get("continuation_key")
            if not key:
                break
            query = {**query, "continuation_key": str(key)}
        return found

    def balance(self, session_id: str, remote_uid: str) -> RemoteBalance | None:
        reply = self._call("GET", f"/accounts/{urllib.parse.quote(remote_uid, safe='')}/balances")
        return parse_balance(reply)

    def revoke(self, session_id: str) -> None:
        self._call("DELETE", f"/sessions/{urllib.parse.quote(session_id, safe='')}")


def _http_message(status: int) -> str:
    if status in (401, 403):
        return "El banco rechazó la petición: puede que el consentimiento haya caducado"
    if status == 429:
        return "El banco limita las consultas; se reintentará más tarde"
    if status == 404:
        return "El banco no encontró la cuenta o la sesión"
    return "El banco no pudo atender la petición"
