"""Unit tests for AST-based APIScanner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentdiff.api.scanner import APIScanner

if TYPE_CHECKING:
    from pathlib import Path


def test_scanner_detects_direct_and_aliased_imports() -> None:
    code = """
import openai
import stripe as st
import os

def helper():
    pass
"""
    scanner = APIScanner()
    usages = scanner.scan_code(code, filepath="app.py")

    import_symbols = {u.symbol for u in usages if u.call_type == "import"}
    assert "openai" in import_symbols
    assert "stripe" in import_symbols


def test_scanner_detects_from_imports() -> None:
    code = """
from openai import OpenAI, ChatCompletion
from stripe import Charge, PaymentIntent as PI
"""
    scanner = APIScanner()
    usages = scanner.scan_code(code, filepath="services.py")

    symbols = {u.symbol for u in usages if u.call_type == "import"}
    assert "openai.OpenAI" in symbols
    assert "openai.ChatCompletion" in symbols
    assert "stripe.Charge" in symbols
    assert "stripe.PaymentIntent" in symbols


def test_scanner_detects_legacy_openai_calls() -> None:
    code = """
import openai

def ask_gpt(prompt):
    return openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0301",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
"""
    scanner = APIScanner()
    usages = scanner.scan_code(code, filepath="ai.py")

    calls = [u for u in usages if u.call_type == "call"]
    assert len(calls) == 1
    call = calls[0]
    assert call.provider == "openai"
    assert call.symbol == "openai.ChatCompletion.create"
    assert call.keyword_arguments.get("model") == "gpt-3.5-turbo-0301"
    assert call.keyword_arguments.get("temperature") == "0.7"
    assert call.enclosing_scope == "ask_gpt"


def test_scanner_detects_modern_openai_client_calls() -> None:
    code = """
from openai import OpenAI

client = OpenAI(api_key="sk-test")

def run():
    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
    )
    return res
"""
    scanner = APIScanner()
    usages = scanner.scan_code(code, filepath="agent.py")

    calls = [u for u in usages if u.call_type == "call"]
    symbols = [u.symbol for u in calls]
    assert any("chat.completions.create" in s for s in symbols)


def test_scanner_detects_stripe_calls() -> None:
    code = """
import stripe

def charge_customer(token, amount_cents):
    return stripe.Charge.create(
        amount=amount_cents,
        currency="usd",
        source=token,
        description="Test charge",
    )

def modern_checkout(customer_id):
    return stripe.PaymentIntent.create(
        amount=5000,
        currency="usd",
        customer=customer_id,
    )
"""
    scanner = APIScanner()
    usages = scanner.scan_code(code, filepath="billing.py")

    calls = [u for u in usages if u.call_type == "call"]
    symbols = {u.symbol for u in calls}
    assert "stripe.Charge.create" in symbols
    assert "stripe.PaymentIntent.create" in symbols

    charge_usage = next(u for u in calls if u.symbol == "stripe.Charge.create")
    assert charge_usage.keyword_arguments.get("currency") == "usd"
    assert charge_usage.keyword_arguments.get("source") == "token"
    assert charge_usage.enclosing_scope == "charge_customer"


def test_scanner_detects_attribute_configuration() -> None:
    code = """
import openai
import stripe

openai.api_key = "sk-12345"
stripe.api_version = "2020-08-27"
"""
    scanner = APIScanner()
    usages = scanner.scan_code(code, filepath="config.py")

    attrs = [u for u in usages if u.call_type == "attribute"]
    symbols = {u.symbol for u in attrs}
    assert "openai.api_key" in symbols
    assert "stripe.api_version" in symbols


def test_scanner_scans_directory_recursively(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text(
        "import openai\nopenai.ChatCompletion.create(model='gpt-4')\n",
        encoding="utf-8",
    )

    sub_dir = src_dir / "payments"
    sub_dir.mkdir()
    (sub_dir / "pay.py").write_text(
        "import stripe\nstripe.Charge.create(amount=100)\n",
        encoding="utf-8",
    )

    # Ignored directory
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "lib.py").write_text("import openai\n", encoding="utf-8")

    scanner = APIScanner()
    usages = scanner.scan_directory(tmp_path)

    filepaths = {u.filepath for u in usages}
    assert any("src/app.py" in f for f in filepaths)
    assert any("src/payments/pay.py" in f for f in filepaths)
    assert not any(".venv" in f for f in filepaths)
