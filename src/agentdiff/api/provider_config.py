"""Data-first custom-provider initialization and discovery."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from agentdiff.api.fetch import FetchArtifact, SafeProviderFetcher
from agentdiff.api.intel import IntelArtifact, ProviderIntelEngine

_PROVIDER_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


@dataclass(frozen=True, slots=True)
class ProviderDiscovery:
    provider: str
    sources: tuple[FetchArtifact, ...]
    artifacts: tuple[IntelArtifact, ...]
    output_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "provider": self.provider,
            "trust": "UNTRUSTED_CANDIDATES",
            "sources": [source.to_dict() for source in self.sources],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "output_path": self.output_path,
        }


def init_provider(name: str, providers_dir: str | Path = "providers") -> Path:
    """Create a declarative DATA_ONLY provider skeleton."""

    normalized = name.lower()
    if not _PROVIDER_NAME.fullmatch(normalized):
        raise ValueError("provider name must be 2-64 lowercase letters, digits, '_' or '-'")
    root = Path(providers_dir).expanduser().resolve() / normalized
    if root.exists():
        raise FileExistsError(f"provider already exists: {root}")
    (root / "manifests").mkdir(parents=True, mode=0o700)
    metadata = {
        "name": normalized,
        "library": normalized,
        "version": "0.1.0",
        "trust": "DATA_ONLY",
        "publisher": "",
        "capabilities": ["source_discovery", "declarative_manifests"],
    }
    sources = {
        "sources": {
            "changelog": "",
            "sdk_release": "",
            "migration_docs": "",
            "openapi_before": "",
            "openapi_after": "",
        }
    }
    (root / "metadata.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
    (root / "sources.yaml").write_text(yaml.safe_dump(sources, sort_keys=False), encoding="utf-8")
    return root


def discover_provider(
    name: str,
    providers_dir: str | Path = "providers",
    *,
    cache_dir: str | Path = ".agentdiff/provider-cache",
    fetcher: SafeProviderFetcher | None = None,
) -> ProviderDiscovery:
    """Fetch official sources and emit untrusted, validated-shape candidates."""

    provider_root = Path(providers_dir).expanduser().resolve(strict=True) / name
    metadata = _mapping(provider_root / "metadata.yaml")
    if str(metadata.get("trust", "DATA_ONLY")).upper() != "DATA_ONLY":
        raise ValueError("provider discover accepts DATA_ONLY providers only")
    source_config = _mapping(provider_root / "sources.yaml").get("sources", {})
    if not isinstance(source_config, dict):
        raise ValueError("sources.yaml must contain a sources mapping")
    configured = {
        str(kind): str(url)
        for kind, url in source_config.items()
        if isinstance(url, str) and url.strip()
    }
    if not configured:
        raise ValueError("provider has no configured source URLs")

    safe_fetcher = fetcher or SafeProviderFetcher(cache_dir)
    fetched: dict[str, FetchArtifact] = {}
    for kind, url in sorted(configured.items()):
        fetched[kind] = safe_fetcher.fetch(url)

    engine = ProviderIntelEngine(name, str(metadata.get("library", name)))
    artifacts: list[IntelArtifact] = []
    for kind in ("changelog", "sdk_release"):
        source = fetched.get(kind)
        if source is None:
            continue
        artifact = (
            engine.from_changelog(source.cache_path)
            if kind == "changelog"
            else engine.from_sdk_release(source.cache_path)
        )
        artifacts.append(_bind_source(artifact, source))
    before = fetched.get("openapi_before")
    after = fetched.get("openapi_after")
    if before is not None or after is not None:
        if before is None or after is None:
            raise ValueError("OpenAPI discovery requires both before and after sources")
        artifacts.append(
            _bind_source(engine.from_openapi_diff(before.cache_path, after.cache_path), after)
        )

    output_dir = provider_root / "artifacts"
    output_dir.mkdir(mode=0o700)
    output_path = output_dir / "latest-discovery.json"
    discovery = ProviderDiscovery(name, tuple(fetched.values()), tuple(artifacts), str(output_path))
    output_path.write_text(
        json.dumps(discovery.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return discovery


def _mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing provider file: {path.name}")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a mapping")
    return value


def _bind_source(artifact: IntelArtifact, source: FetchArtifact) -> IntelArtifact:
    return replace(
        artifact,
        input_path=source.cache_path,
        candidates=tuple(
            replace(candidate, source_url=source.final_url) for candidate in artifact.candidates
        ),
    )
