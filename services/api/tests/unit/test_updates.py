"""OF-907: aviso de versión nueva."""

import io
import json
import urllib.error

import pytest

from openfinance.application.updates import (
    LatestRelease,
    is_newer,
    parse_version,
    version_info,
)
from openfinance.infrastructure.updates import GithubLatestRelease


class TestVersions:
    @pytest.mark.parametrize(
        ("current", "latest", "expected"),
        [
            ("0.2.0", "0.3.0", True),
            ("0.2.0", "0.2.1", True),
            ("0.2.0", "1.0.0", True),
            ("0.2.0", "0.2.0", False),
            ("0.3.0", "0.2.9", False),
            ("0.2.0.dev0", "0.2.0", True),  # la versión de desarrollo es anterior a su release
            ("0.2.0-dev", "0.2.0", True),
            ("0.2.0", "0.3.0-rc1", False),  # nunca se avisa de una prerelease
            ("0.10.0", "0.9.0", False),  # numérico, no alfabético
            ("0.9.0", "0.10.0", True),
            ("0.2.0", "no-es-una-version", False),
            ("raro", "0.3.0", False),
        ],
    )
    def test_is_newer(self, current: str, latest: str, expected: bool) -> None:
        assert is_newer(current, latest) is expected

    def test_parses_tags_and_dev_versions(self) -> None:
        assert parse_version("v0.3.0") == ((0, 3, 0), False)
        assert parse_version("0.2.0.dev0") == ((0, 2, 0), True)
        assert parse_version("0.2.0-dev") == ((0, 2, 0), True)
        assert parse_version("1.2") is None


class FakeSource:
    def __init__(self, release: LatestRelease | None) -> None:
        self.release = release
        self.calls = 0

    def latest(self) -> LatestRelease | None:
        self.calls += 1
        return self.release


class TestVersionInfo:
    def test_disabled_never_asks(self) -> None:
        info = version_info("0.2.0", None)
        assert (info.enabled, info.latest, info.update_available) == (False, None, False)

    def test_reports_a_newer_release(self) -> None:
        source = FakeSource(LatestRelease("0.3.0", "https://github.com/x/y/releases/tag/v0.3.0"))
        info = version_info("0.2.0", source)
        assert info.update_available and info.latest == "0.3.0" and info.enabled

    def test_unknown_when_the_source_cannot_tell(self) -> None:
        info = version_info("0.2.0", FakeSource(None))
        assert info.enabled and info.latest is None and not info.update_available


class Response(io.BytesIO):
    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def body(**kw: str) -> Response:
    data = {
        "tag_name": "v0.3.0",
        "html_url": "https://github.com/rldona/OpenFinance/releases/tag/v0.3.0",
    }
    data.update(kw)
    return Response(json.dumps(data).encode())


class TestGithub:
    def make(self, responses: list, clock: list[float]):  # type: ignore[no-untyped-def]
        calls: list[object] = []

        def opener(request, timeout):  # type: ignore[no-untyped-def]
            calls.append(request)
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        source = GithubLatestRelease("rldona/OpenFinance", clock=lambda: clock[0], opener=opener)
        return source, calls

    def test_reads_the_latest_release_and_caches_it(self) -> None:
        clock = [0.0]
        source, calls = self.make([body()], clock)
        first = source.latest()
        assert first == LatestRelease(
            "0.3.0", "https://github.com/rldona/OpenFinance/releases/tag/v0.3.0"
        )
        clock[0] = 3600
        assert source.latest() == first
        assert len(calls) == 1

    def test_refreshes_after_the_ttl(self) -> None:
        clock = [0.0]
        source, calls = self.make(
            [body(), body(tag_name="v0.4.0", html_url="https://github.com/rldona/OpenFinance/x/")],
            clock,
        )
        source.latest()
        clock[0] = 86401
        assert source.latest().version == "0.4.0"  # type: ignore[union-attr]
        assert len(calls) == 2

    def test_a_failure_is_not_retried_for_an_hour(self) -> None:
        clock = [0.0]
        source, calls = self.make([urllib.error.URLError("sin red"), body()], clock)
        assert source.latest() is None
        clock[0] = 1800
        assert source.latest() is None
        assert len(calls) == 1
        clock[0] = 3601
        assert source.latest() is not None

    def test_request_sends_nothing_about_the_installation(self) -> None:
        source, calls = self.make([body()], [0.0])
        source.latest()
        request = calls[0]
        assert request.full_url == "https://api.github.com/repos/rldona/OpenFinance/releases/latest"  # type: ignore[attr-defined]
        assert dict(request.header_items()) == {  # type: ignore[attr-defined]
            "Accept": "application/vnd.github+json",
            "User-agent": "OpenFinance",
        }

    @pytest.mark.parametrize(
        "bad",
        [
            {"tag_name": "v0.3.0-rc1"},  # prerelease
            {"tag_name": "latest"},
            {"html_url": "https://evil.example/phish"},  # el enlace debe ser del repositorio
            {"html_url": "javascript:alert(1)"},
        ],
    )
    def test_ignores_anything_suspicious(self, bad: dict[str, str]) -> None:
        source, _ = self.make([body(**bad)], [0.0])
        assert source.latest() is None

    def test_rejects_a_malformed_repository(self) -> None:
        with pytest.raises(ValueError):
            GithubLatestRelease("../../etc/passwd")
