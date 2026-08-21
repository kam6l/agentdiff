"""Security tests for provider-source retrieval."""

from __future__ import annotations

import email.message
import io
from pathlib import Path
from typing import Any, Self

import pytest

from agentdiff.api.fetch import ProviderFetchError, SafeProviderFetcher


def _public_resolver(host: str, port: int, *, type: Any) -> list[tuple[Any, ...]]:
    del host, type
    return [(2, 1, 6, "", ("93.184.216.34", port))]


class _Response(io.BytesIO):
    def __init__(self, payload: bytes, content_type: str = "text/markdown") -> None:
        super().__init__(payload)
        self.status = 200
        self.headers = email.message.Message()
        self.headers["Content-Type"] = content_type
        self.headers["ETag"] = '"v1"'

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class _Opener:
    def __init__(self, response: Any) -> None:
        self.response = response

    def open(self, request: Any, *, timeout: float) -> Any:
        del request, timeout
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def test_fetches_bounded_public_https_source(tmp_path: Path) -> None:
    fetcher = SafeProviderFetcher(
        tmp_path,
        resolver=_public_resolver,
        opener=_Opener(_Response(b"# Changelog\n- Removed `old.call`")),
    )

    artifact = fetcher.fetch("https://api.example.com/changelog.md")

    assert artifact.source_digest.startswith("sha256:")
    assert artifact.size_bytes > 0
    assert artifact.cache_status == "MISS"
    assert Path(artifact.cache_path).read_bytes().startswith(b"# Changelog")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://example.com/changelog",
        "https://localhost/changelog",
        "https://user:pass@example.com/changelog",
    ],
)
def test_rejects_unsafe_urls(tmp_path: Path, url: str) -> None:
    fetcher = SafeProviderFetcher(tmp_path, resolver=_public_resolver, opener=_Opener(None))
    with pytest.raises(ProviderFetchError):
        fetcher.fetch(url)


def test_rejects_private_dns_resolution(tmp_path: Path) -> None:
    def private_resolver(host: str, port: int, *, type: Any) -> list[tuple[Any, ...]]:
        del host, type
        return [(2, 1, 6, "", ("127.0.0.1", port))]

    fetcher = SafeProviderFetcher(tmp_path, resolver=private_resolver, opener=_Opener(None))
    with pytest.raises(ProviderFetchError, match="non-public"):
        fetcher.fetch("https://example.com/changelog")


def test_rejects_oversized_or_wrong_content(tmp_path: Path) -> None:
    oversized = SafeProviderFetcher(
        tmp_path,
        max_bytes=4,
        resolver=_public_resolver,
        opener=_Opener(_Response(b"12345")),
    )
    with pytest.raises(ProviderFetchError, match="size"):
        oversized.fetch("https://example.com/changelog")

    wrong_type = SafeProviderFetcher(
        tmp_path,
        resolver=_public_resolver,
        opener=_Opener(_Response(b"binary", "application/octet-stream")),
    )
    with pytest.raises(ProviderFetchError, match="content type"):
        wrong_type.fetch("https://example.com/changelog")
