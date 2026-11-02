"""Lectores de extractos bancarios y su registro por entidad."""

from __future__ import annotations

from openfinance.application.ports import StatementParser
from openfinance.domain.csv_profile import CsvProfile, CsvSample
from openfinance.domain.imports import ClassificationRules, ParseResult
from openfinance.domain.ledger import Institution
from openfinance.infrastructure.importers.bankinter import parse_bankinter
from openfinance.infrastructure.importers.csv_profile import parse_csv, sample
from openfinance.infrastructure.importers.revolut import RevolutProfile, parse_revolut
from openfinance.infrastructure.importers.universal import parse_standard


def _revolut(content: bytes, account_key: str, rules: ClassificationRules) -> ParseResult:
    return parse_revolut(content, RevolutProfile(account_key=account_key, rules=rules))


class StatementParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[Institution, StatementParser] = {
            Institution.REVOLUT: _revolut,
            Institution.BANKINTER: parse_bankinter,
            Institution.OTHER: parse_standard,
        }

    def get(self, institution: Institution) -> StatementParser | None:
        return self._parsers.get(institution)

    def csv(self, profile: CsvProfile) -> StatementParser:
        def parse(content: bytes, account_key: str, rules: ClassificationRules) -> ParseResult:
            return parse_csv(content, account_key, rules, profile)

        return parse

    def csv_sample(self, content: bytes) -> CsvSample:
        return sample(content)
