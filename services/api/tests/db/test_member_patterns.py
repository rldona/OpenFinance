"""ADR-0015: patrones por persona guardados en base de datos y gestionados por CLI."""

from datetime import UTC, datetime

import pytest

from openfinance import cli
from openfinance.application import member_patterns as mp
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.domain.imports import MemberPattern, PatternDirection
from openfinance.infrastructure.db.repositories import SqlUnitOfWork

NOW = datetime(2026, 11, 1, tzinfo=UTC)
INFLOW, OUTFLOW = PatternDirection.INFLOW, PatternDirection.OUTFLOW


def house(uow, user):
    return uow.households.households_of(user.id)[0]


class TestRepository:
    def test_add_list_and_delete(self, session_factory, seed) -> None:
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            h = house(uow, seed.raul)
            uow.member_patterns.add(MemberPattern(h, seed.raul.id, "*1234"), NOW)
            uow.member_patterns.add(MemberPattern(h, seed.raul.id, "*1234", OUTFLOW), NOW)
            uow.commit()
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            listed = uow.member_patterns.for_household(house(uow, seed.raul))
            assert [(p.pattern, p.direction) for p in listed] == [
                ("*1234", INFLOW),
                ("*1234", OUTFLOW),
            ]
            assert uow.member_patterns.for_household(house(uow, seed.ana)) == []
            assert uow.member_patterns.delete(house(uow, seed.raul), INFLOW, "*1234") is True
            assert uow.member_patterns.delete(house(uow, seed.raul), INFLOW, "*1234") is False

    def test_duplicate_is_a_conflict(self, session_factory, seed) -> None:
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            h = house(uow, seed.raul)
            uow.member_patterns.add(MemberPattern(h, seed.raul.id, "*1234"), NOW)
            with pytest.raises(ConflictError):
                uow.member_patterns.add(MemberPattern(h, seed.elena.id, "*1234"), NOW)

    def test_member_of_another_household_is_rejected_by_the_database(
        self, session_factory, seed
    ) -> None:
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            with pytest.raises(ConflictError):
                uow.member_patterns.add(
                    MemberPattern(house(uow, seed.raul), seed.ana.id, "*9999"), NOW
                )


class TestUseCases:
    def test_add_normalizes_and_lists_the_whole_household(self, session_factory, seed) -> None:
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            added = mp.add_member_pattern(uow, " RAUL@example.org", "recarga de *1234", INFLOW, NOW)
            assert added.pattern == "RECARGA DE *1234"
            mp.add_member_pattern(uow, "elena@example.org", "*5678", INFLOW, NOW)
            listed = mp.list_member_patterns(uow, "raul@example.org")
            assert {(i.pattern.pattern, i.member.email) for i in listed} == {
                ("RECARGA DE *1234", "raul@example.org"),
                ("*5678", "elena@example.org"),
            }
            assert mp.list_member_patterns(uow, "ana@example.org") == []

    @pytest.mark.parametrize("pattern", ["***", "ab", ""])
    def test_weak_patterns_are_rejected(self, session_factory, seed, pattern) -> None:
        with session_factory() as s, pytest.raises(InvalidRequestError):
            mp.add_member_pattern(SqlUnitOfWork(s), "raul@example.org", pattern, INFLOW, NOW)

    def test_unknown_email(self, session_factory, seed) -> None:
        with session_factory() as s, pytest.raises(NotFoundError):
            mp.add_member_pattern(SqlUnitOfWork(s), "nadie@example.org", "*1234", INFLOW, NOW)
        with session_factory() as s, pytest.raises(InvalidRequestError):
            mp.add_member_pattern(SqlUnitOfWork(s), "no-es-email", "*1234", INFLOW, NOW)

    def test_person_in_two_households_is_ambiguous(self, session_factory, seed) -> None:
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            uow.households.add_member(house(uow, seed.ana), seed.raul.id)
            uow.commit()
            with pytest.raises(InvalidRequestError, match="2 hogares"):
                mp.add_member_pattern(uow, "raul@example.org", "*1234", INFLOW, NOW)

    def test_remove_only_own_existing_patterns(self, session_factory, seed) -> None:
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            mp.add_member_pattern(uow, "raul@example.org", "*1234", INFLOW, NOW)
            with pytest.raises(NotFoundError):
                mp.remove_member_pattern(uow, "elena@example.org", "*1234", INFLOW)
            with pytest.raises(NotFoundError):
                mp.remove_member_pattern(uow, "raul@example.org", "*1234", OUTFLOW)
            mp.remove_member_pattern(uow, "raul@example.org", "*1234", INFLOW)
            assert mp.list_member_patterns(uow, "raul@example.org") == []


class TestCli:
    @pytest.fixture(autouse=True)
    def database(self, monkeypatch, session_factory):
        monkeypatch.setattr(cli, "get_session_factory", lambda: session_factory)

    def test_add_list_remove(self, seed, capsys) -> None:
        assert cli.main(["member-patterns", "add", "raul@example.org", "*1234"]) == 0
        args = ["member-patterns", "add", "raul@example.org", "revolut**", "--outflow"]
        assert cli.main(args) == 0
        assert cli.main(["member-patterns", "list", "elena@example.org"]) == 0
        out = capsys.readouterr().out
        assert "inflow   raul@example.org" in out
        assert "REVOLUT**" in out
        args = ["member-patterns", "remove", "raul@example.org", "*1234"]
        assert cli.main(args) == 0

    def test_errors_go_to_stderr_with_exit_1(self, seed, capsys) -> None:
        assert cli.main(["member-patterns", "add", "raul@example.org", "***"]) == 1
        assert "letras o cifras" in capsys.readouterr().err
        assert cli.main(["member-patterns", "remove", "raul@example.org", "*1234"]) == 1
