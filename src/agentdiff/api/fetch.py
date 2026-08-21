"""Bounded, provenance-preserving fetching for untrusted provider URLs."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "application/openapi+json",
        "application/yaml",
        "application/x-yaml",
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "text/yaml",
    }
)
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


class ProviderFetchError(ValueError):
    """A provider source failed validation or bounded retrieval."""


@dataclass(frozen=True, slots=True)
class FetchArtifact:
    requested_url: str
    final_url: str
    source_digest: str
    retrieved_at: str
    content_type: str
    size_bytes: int
    cache_path: str
    cache_status: str
    etag: str = ""
    last_modified: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


class SafeProviderFetcher:
    """Fetch HTTPS provider data with SSRF, redirect, and size controls."""

    def __init__(
        self,
        cache_root: str | Path,
        *,
        timeout_seconds: float = 15.0,
        max_bytes: int = 5 * 1024 * 1024,
        max_redirects: int = 5,
        resolver: Callable[..., Any] = socket.getaddrinfo,
        opener: Any | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_bytes <= 0 or max_redirects < 0:
            raise ValueError("fetch bounds must be positive")
        self.cache_root = Path(cache_root).expanduser().resolve()
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.resolver = resolver
        self.opener = opener or urllib.request.build_opener(_NoRedirect())

    def fetch(self, url: str) -> FetchArtifact:
        requested_url = url
        cache_key = hashlib.sha256(requested_url.encode("utf-8")).hexdigest()
        payload_path = self.cache_root / f"{cache_key}.payload"
        metadata_path = self.cache_root / f"{cache_key}.json"
        cached = self._read_metadata(metadata_path)
        headers = {"Accept": ", ".join(sorted(_ALLOWED_CONTENT_TYPES)), "User-Agent": "AgentDiff/1"}
        if cached.get("etag"):
            headers["If-None-Match"] = str(cached["etag"])
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = str(cached["last_modified"])

        current = requested_url
        for _redirect_count in range(self.max_redirects + 1):
            self._validate_url(current)
            request = urllib.request.Request(current, headers=headers, method="GET")
            try:
                response = self.opener.open(request, timeout=self.timeout_seconds)  # nosec B310
            except urllib.error.HTTPError as error:
                if error.code == 304 and payload_path.is_file() and cached:
                    return FetchArtifact(**cached, cache_status="REVALIDATED")
                if error.code in _REDIRECT_CODES:
                    location = error.headers.get("Location", "")
                    if not location:
                        raise ProviderFetchError("redirect is missing Location") from error
                    current = urllib.parse.urljoin(current, location)
                    continue
                raise ProviderFetchError(f"provider source returned HTTP {error.code}") from error
            except (OSError, urllib.error.URLError) as error:
                raise ProviderFetchError(
                    f"provider fetch failed: {type(error).__name__}"
                ) from error

            with response:
                status = int(getattr(response, "status", response.getcode()))
                if status in _REDIRECT_CODES:
                    current = urllib.parse.urljoin(current, response.headers.get("Location", ""))
                    continue
                if status != 200:
                    raise ProviderFetchError(f"provider source returned HTTP {status}")
                content_type = response.headers.get_content_type().lower()
                if content_type not in _ALLOWED_CONTENT_TYPES:
                    raise ProviderFetchError(f"unsupported provider content type: {content_type}")
                payload = response.read(self.max_bytes + 1)
                if len(payload) > self.max_bytes:
                    raise ProviderFetchError("provider source exceeds response-size limit")
                digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
                retrieved_at = datetime.now(timezone.utc).isoformat()
                artifact = FetchArtifact(
                    requested_url=requested_url,
                    final_url=current,
                    source_digest=digest,
                    retrieved_at=retrieved_at,
                    content_type=content_type,
                    size_bytes=len(payload),
                    cache_path=str(payload_path),
                    cache_status="MISS" if not cached else "UPDATED",
                    etag=response.headers.get("ETag", ""),
                    last_modified=response.headers.get("Last-Modified", ""),
                )
                self._write_cache(payload_path, metadata_path, payload, artifact)
                return artifact
        raise ProviderFetchError("provider source exceeded redirect limit")

    def _validate_url(self, url: str) -> None:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.lower() != "https":
            raise ProviderFetchError("provider sources must use HTTPS")
        if parsed.username or parsed.password:
            raise ProviderFetchError("provider URL credentials are not allowed")
        hostname = parsed.hostname
        if not hostname or hostname.lower() in {"localhost", "localhost.localdomain"}:
            raise ProviderFetchError("provider source hostname is not public")
        try:
            addresses = self.resolver(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except OSError as error:
            raise ProviderFetchError("provider hostname could not be resolved") from error
        if not addresses:
            raise ProviderFetchError("provider hostname returned no addresses")
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise ProviderFetchError(f"provider hostname resolves to non-public address: {ip}")

    @staticmethod
    def _read_metadata(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(value, dict):
            return {}
        value.pop("cache_status", None)
        return value

    def _write_cache(
        self,
        payload_path: Path,
        metadata_path: Path,
        payload: bytes,
        artifact: FetchArtifact,
    ) -> None:
        self.cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary_name = tempfile.mkstemp(prefix="provider-", dir=self.cache_root)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, payload_path)
        finally:
            temporary.unlink(missing_ok=True)
        metadata = artifact.to_dict()
        metadata.pop("cache_status", None)
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
