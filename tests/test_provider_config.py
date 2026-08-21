"""Tests for data-first provider configuration."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from agentdiff.api.fetch import FetchArtifact
from agentdiff.api.provider_config import discover_provider, init_provider


class _Fetcher:
    def __init__(self, payload: Path) -> None:
        self.payload = payload

    def fetch(self, url: str) -> FetchArtifact:
        content = self.payload.read_bytes()
        return FetchArtifact(
            requested_url=url,
            final_url=url,
            source_digest=f"sha256:{hashlib.sha256(content).hexdigest()}",
            retrieved_at="2026-08-21T00:00:00+00:00",
            content_type="text/markdown",
            size_bytes=len(content),
            cache_path=str(self.payload),
            cache_status="MISS",
        )


def test_init_and_discover_data_only_provider(tmp_path: Path) -> None:
    providers = tmp_path / "providers"
    provider = init_provider("acme", providers)
    metadata = yaml.safe_load((provider / "metadata.yaml").read_text(encoding="utf-8"))
    assert metadata["trust"] == "DATA_ONLY"

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## Breaking Changes\n- Removed `acme.old.call`\n", encoding="utf-8")
    sources: dict[str, Any] = yaml.safe_load(
        (provider / "sources.yaml").read_text(encoding="utf-8")
    )
    sources["sources"]["changelog"] = "https://docs.acme.example/changelog"
    (provider / "sources.yaml").write_text(yaml.safe_dump(sources), encoding="utf-8")

    discovery = discover_provider(
        "acme",
        providers,
        cache_dir=tmp_path / "cache",
        fetcher=_Fetcher(changelog),  # type: ignore[arg-type]
    )

    assert discovery.provider == "acme"
    assert len(discovery.sources) == 1
    assert discovery.artifacts[0].candidates[0].source_url.startswith("https://")
    assert Path(discovery.output_path).is_file()
