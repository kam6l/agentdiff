"""CLI integration tests for `agentdiff api scan` and `agentdiff api check`."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentdiff.cli", *args],
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )


def test_cli_api_help(tmp_path: Path) -> None:
    result = run_cli("api", "--help", cwd=tmp_path)
    assert result.returncode == 0
    assert "scan" in result.stdout
    assert "check" in result.stdout


def test_cli_api_scan_summary(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "ai.py").write_text(
        "import openai\nopenai.ChatCompletion.create(model='gpt-3.5-turbo-0301')\n",
        encoding="utf-8",
    )
    (src / "pay.py").write_text(
        "import stripe\nstripe.Charge.create(amount=1000)\n",
        encoding="utf-8",
    )

    result = run_cli("api", "scan", "--root", str(tmp_path), "--format", "summary", cwd=tmp_path)
    assert result.returncode == 0
    assert "External API Scan" in result.stdout
    assert "openai" in result.stdout
    assert "stripe" in result.stdout
    assert "openai.ChatCompletion.create" in result.stdout
    assert "stripe.Charge.create" in result.stdout


def test_cli_api_scan_json(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        "import openai\nopenai.Completion.create(model='text-davinci-003')\n",
        encoding="utf-8",
    )

    result = run_cli("api", "scan", "--root", str(tmp_path), "--format", "json", cwd=tmp_path)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["count"] >= 2
    assert any(u["symbol"] == "openai.Completion.create" for u in payload["usages"])


def test_cli_api_check_detects_breaking_changes(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "legacy.py").write_text(
        "import openai\nimport stripe\n"
        "openai.ChatCompletion.create(model='gpt-3.5-turbo-0301')\n"
        "stripe.Charge.create(amount=2000)\n",
        encoding="utf-8",
    )

    result = run_cli("api", "check", "--root", str(tmp_path), "--format", "summary", cwd=tmp_path)
    assert result.returncode == 1
    assert "External API Breaking Change Check" in result.stdout
    assert "Breaking Changes & Deprecations Detected:" in result.stdout
    assert "openai.ChatCompletion.create" in result.stdout
    assert "stripe.Charge.create" in result.stdout

    result_json = run_cli("api", "check", "--root", str(tmp_path), "--format", "json", cwd=tmp_path)
    assert result_json.returncode == 1
    payload = json.loads(result_json.stdout)
    assert payload["affected_usages"] >= 2
    assert payload["blast_radius"]["score"] > 0


def test_cli_api_check_clean_repo(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "modern.py").write_text(
        "from openai import OpenAI\nimport stripe\n"
        "client = OpenAI()\n"
        "client.chat.completions.create(model='gpt-4o', messages=[])\n"
        "stripe.PaymentIntent.create(amount=1000, currency='usd')\n",
        encoding="utf-8",
    )

    result = run_cli("api", "check", "--root", str(tmp_path), "--fail-on", "high", cwd=tmp_path)
    assert result.returncode == 0
    assert "No breaking changes detected" in result.stdout


def test_cli_api_provider_filter(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "combo.py").write_text(
        "import openai\nimport stripe\n"
        "openai.ChatCompletion.create(model='gpt-4')\n"
        "stripe.PaymentIntent.create(amount=1000)\n",
        encoding="utf-8",
    )

    res_stripe = run_cli(
        "api",
        "scan",
        "--root",
        str(tmp_path),
        "--provider",
        "stripe",
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert res_stripe.returncode == 0
    data = json.loads(res_stripe.stdout)
    assert all(u["provider"] == "stripe" for u in data["usages"])

    res_openai = run_cli(
        "api",
        "check",
        "--root",
        str(tmp_path),
        "--provider",
        "openai",
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert res_openai.returncode == 1
    data_oai = json.loads(res_openai.stdout)
    assert all(m["usage"]["provider"] == "openai" for m in data_oai["matched_changes"])


def test_cli_api_fail_on_never(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "broken.py").write_text(
        "import openai\nopenai.ChatCompletion.create(model='text-davinci-003')\n",
        encoding="utf-8",
    )

    result = run_cli("api", "check", "--root", str(tmp_path), "--fail-on", "never", cwd=tmp_path)
    assert result.returncode == 0
