"""Verified Campaigns bind a fleet rollup to independent repository proof."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from agentdiff.api import (
    FleetConfig,
    MigrationEngine,
    migrate_fleet,
    simulate_fleet,
    verify_campaign_report,
    write_campaign_report,
)
from agentdiff.api.certificate import CertificateStatus
from agentdiff.api.generators import DeterministicASTGenerator
from tests.fake_proof import fake_env_factory

if TYPE_CHECKING:
    from pathlib import Path


def _repository(root: Path, *, affected: bool = True) -> Path:
    source = root / "src"
    source.mkdir(parents=True)
    code = (
        """from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
)
print(response.choices[0].message.content)
"""
        if affected
        else "print('no provider usage')\n"
    )
    (source / "app.py").write_text(code, encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname='fleet-fixture'\nversion='0.1.0'\n", encoding="utf-8"
    )
    return root


def _config(root: Path, repositories: list[tuple[str, Path]]) -> Path:
    payload = {
        "version": 1,
        "campaign": "openai-responses-2026",
        "provider": "openai",
        "change": "chat_to_responses",
        "repositories": [{"name": name, "path": str(path)} for name, path in repositories],
    }
    path = root / "fleet.yaml"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _fake_engine(**kwargs: Any) -> MigrationEngine:
    return MigrationEngine(**kwargs, proof_environment_factory=fake_env_factory())


def test_simulation_is_read_only_and_marks_unaffected(tmp_path: Path) -> None:
    affected = _repository(tmp_path / "affected")
    unaffected = _repository(tmp_path / "unaffected", affected=False)
    config = FleetConfig.load(
        _config(tmp_path, [("billing-api", affected), ("status-api", unaffected)])
    )
    before = (affected / "src" / "app.py").read_bytes()

    result = simulate_fleet(config)

    assert result.verdict == "SAFE_TO_ATTEMPT"
    assert [repository.status for repository in result.repositories] == [
        "SAFE_TO_ATTEMPT",
        "UNAFFECTED",
    ]
    assert (affected / "src" / "app.py").read_bytes() == before
    assert not (affected / ".agentdiff").exists()


def test_campaign_verifies_child_certificates_and_detects_tampering(tmp_path: Path) -> None:
    affected = _repository(tmp_path / "affected")
    unaffected = _repository(tmp_path / "unaffected", affected=False)
    config = FleetConfig.load(
        _config(tmp_path, [("billing-api", affected), ("status-api", unaffected)])
    )

    result = migrate_fleet(
        config,
        generator=DeterministicASTGenerator(),
        engine_factory=_fake_engine,
    )
    report = write_campaign_report(result, tmp_path / "campaign.json")

    assert result.verdict == "PROVEN"
    assert [repository.status for repository in result.repositories] == [
        "PROVEN",
        "UNAFFECTED",
    ]
    assert verify_campaign_report(report)[0] is CertificateStatus.VALID

    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["repositories"][0]["proof_digest"] = "0" * 64
    report.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_campaign_report(report) == (
        CertificateStatus.INVALID,
        "campaign digest mismatch",
    )


def test_campaign_rejects_symlinked_config_and_report(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repository")
    config_path = _config(tmp_path, [("api", repository)])
    config_link = tmp_path / "fleet-link.yaml"
    config_link.symlink_to(config_path)
    with pytest.raises(ValueError, match="non-symlink"):
        FleetConfig.load(config_link)

    result = simulate_fleet(FleetConfig.load(config_path))
    report = write_campaign_report(result, tmp_path / "campaign.json")
    report_link = tmp_path / "campaign-link.json"
    report_link.symlink_to(report)
    assert verify_campaign_report(report_link)[0] is CertificateStatus.INVALID


def test_cli_fleet_simulate_emits_machine_readable_rollup(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repository")
    config = _config(tmp_path, [("api", repository)])

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentdiff.cli",
            "fleet",
            "simulate",
            "--config",
            str(config),
            "--format",
            "json",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["verdict"] == "SAFE_TO_ATTEMPT"
    assert payload["repositories"][0]["name"] == "api"
    assert payload["campaign_digest"]
