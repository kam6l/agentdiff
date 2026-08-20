"""Adversarial and negative tests for API scanner, matcher, and version detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from agentdiff.api.matcher import APIMatcher
from agentdiff.api.scanner import APIScanner
from agentdiff.api.version_detector import (
    SDKVersionInfo,
    detect_installed_sdk_versions,
    is_version_affected,
)


def test_custom_classes_without_imports_not_detected() -> None:
    """User-defined classes matching provider symbol names must NEVER be detected."""
    code = """
class Charge:
    @classmethod
    def create(cls, amount=100):
        return {"id": "ch_custom", "amount": amount}

class Completion:
    @classmethod
    def create(cls, prompt="hello"):
        return {"text": "custom"}

class Plan:
    @classmethod
    def create(cls, name="basic"):
        return {"plan": name}

# Calls on user's own classes without any stripe/openai imports
c = Charge.create(amount=500)
comp = Completion.create(prompt="test")
p = Plan.create(name="pro")
"""
    scanner = APIScanner()
    usages = scanner.scan_code(code)
    assert len(usages) == 0


def test_unrelated_libraries_not_detected() -> None:
    """Methods on unrelated packages must not be falsely attributed to OpenAI/Stripe."""
    code = """
import my_billing_framework
from my_ai_engine import ChatCompletion, OpenAI

res1 = my_billing_framework.Charge.create(amount=200)
res2 = ChatCompletion.create(model="custom-model")
client = OpenAI()
"""
    scanner = APIScanner()
    usages = scanner.scan_code(code)
    assert len(usages) == 0


def test_strings_and_comments_not_detected() -> None:
    """Symbol names in docstrings, strings, or comments must not be detected as API calls."""
    code = '''
# import openai
# stripe.Charge.create(amount=100)

DOC = """
You can use openai.ChatCompletion.create() or stripe.Charge.create()
"""

msg = "openai.ChatCompletion.create(model='gpt-4')"
log_entry = 'stripe.Charge.create'
'''
    scanner = APIScanner()
    usages = scanner.scan_code(code)
    assert len(usages) == 0


def test_aliased_imports_detected_with_provenance() -> None:
    """Deep aliases must resolve to canonical symbols."""
    code = """
import openai as oai
import stripe as st

response = oai.ChatCompletion.create(model="gpt-4", messages=[])
charge = st.Charge.create(amount=1000, currency="usd")
"""
    scanner = APIScanner()
    usages = scanner.scan_code(code)

    assert len(usages) >= 2
    symbols = {u.symbol for u in usages if u.call_type == "call"}
    assert "openai.ChatCompletion.create" in symbols
    assert "stripe.Charge.create" in symbols


def test_aliased_from_imports_detected() -> None:
    """Aliased from-imports must resolve to canonical symbols."""
    code = """
from openai import ChatCompletion as CC
from stripe import Charge as StripeCharge

r = CC.create(model="gpt-4", messages=[])
c = StripeCharge.create(amount=2000)
"""
    scanner = APIScanner()
    usages = scanner.scan_code(code)

    symbols = {u.symbol for u in usages if u.call_type == "call"}
    assert "openai.ChatCompletion.create" in symbols
    assert "stripe.Charge.create" in symbols


def test_class_instance_attribute_clients_detected() -> None:
    """Client stored as self.client or self._client must be tracked accurately."""
    code = """
from openai import OpenAI
import stripe

class AIService:
    def __init__(self):
        self.client = OpenAI()
        self.stripe_client = stripe.StripeClient("key_123")

    def run_prompt(self, prompt: str):
        return self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
        )

    def process_payment(self, amount: int):
        return self.stripe_client.charges.create(amount=amount)
"""
    scanner = APIScanner()
    usages = scanner.scan_code(code)

    calls = [u for u in usages if u.call_type == "call"]
    call_symbols = {c.symbol for c in calls}
    assert "client.chat.completions.create" in call_symbols
    assert "client.charges.create" in call_symbols


def test_syntax_error_handled_gracefully() -> None:
    """Files with syntax errors must not crash scanner."""
    broken_code = """
def broken_syntax(
    this is not valid python code !!!
"""
    scanner = APIScanner()
    usages = scanner.scan_code(broken_code, filepath="broken.py")
    assert usages == []


def test_version_detector_uv_lock(tmp_path: Path) -> None:
    """Version detector must extract exact versions from uv.lock."""
    lock_content = """
version = 1
revision = 3

[[package]]
name = "openai"
version = "0.28.1"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "stripe"
version = "7.8.0"
"""
    (tmp_path / "uv.lock").write_text(lock_content, encoding="utf-8")
    detected = detect_installed_sdk_versions(tmp_path)

    assert "openai" in detected
    assert detected["openai"].exact_version == "0.28.1"
    assert detected["openai"].is_exact is True

    assert "stripe" in detected
    assert detected["stripe"].exact_version == "7.8.0"
    assert detected["stripe"].is_exact is True


def test_version_detector_pyproject_and_requirements(tmp_path: Path) -> None:
    """Version detector parses requirements.txt and pyproject.toml constraints."""
    req_content = """
# Dependencies
openai==1.45.0
stripe>=7.0.0
pytest>=8.0.0
"""
    (tmp_path / "requirements.txt").write_text(req_content, encoding="utf-8")
    detected = detect_installed_sdk_versions(tmp_path)

    assert "openai" in detected
    assert detected["openai"].exact_version == "1.45.0"
    assert "stripe" in detected
    assert detected["stripe"].version_specifier == ">=7.0.0"


def test_breaking_version_constraint_enforcement() -> None:
    """Breaking version constraints must filter changes on compatible installed versions."""
    # When project is pinned to legacy openai==0.28.1:
    sdk_v0 = SDKVersionInfo(
        provider="openai",
        library="openai",
        exact_version="0.28.1",
        version_specifier="==0.28.1",
        source_file="uv.lock",
        is_exact=True,
    )

    # Change requiring >= 1.0.0 should NOT match as a breaking change for installed 0.28.1
    assert is_version_affected(sdk_v0, ">=1.0.0") is False

    # When project has openai==1.50.0:
    sdk_v1 = SDKVersionInfo(
        provider="openai",
        library="openai",
        exact_version="1.50.0",
        version_specifier="==1.50.0",
        source_file="uv.lock",
        is_exact=True,
    )
    assert is_version_affected(sdk_v1, ">=1.0.0") is True

    # Unconditional change (empty specifier) always matches
    assert is_version_affected(sdk_v0, "") is True
    assert is_version_affected(sdk_v1, "") is True


def test_matcher_respects_installed_sdk_version(tmp_path: Path) -> None:
    """APIMatcher must use detected SDK versions to suppress/flag breaking changes."""
    # Scenario A: Code uses legacy ChatCompletion.create on pinned openai==0.28.1
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "openai"\nversion = "0.28.1"\n',
        encoding="utf-8",
    )
    code = "import openai\nopenai.ChatCompletion.create(model='gpt-4')\n"
    scanner = APIScanner()
    usages = scanner.scan_code(code, filepath="app.py")

    matcher = APIMatcher()
    impact_v0 = matcher.calculate_impact(usages, root=tmp_path)
    # Since installed is 0.28.1, >=1.0.0 removal is not active on this installed version
    assert impact_v0.affected_usages == 0

    # Scenario B: Code uses legacy ChatCompletion.create on pinned openai==1.30.0
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "openai"\nversion = "1.30.0"\n',
        encoding="utf-8",
    )
    impact_v1 = matcher.calculate_impact(usages, root=tmp_path)
    assert impact_v1.affected_usages == 1
    assert impact_v1.matched_changes[0].change.change_id == "openai-v1-chat-completion-create"


def test_impact_status_explicit_on_nonexistent_or_errored_root() -> None:
    """APIMatcher must return explicit impact_status without swallowing errors."""
    matcher = APIMatcher()
    impact = matcher.calculate_impact([], root=None)
    assert impact.impact_status == "skipped"
    assert impact.impact_error is None

    # Path that is a file, not a directory
    impact_file = matcher.calculate_impact([], root="/nonexistent/directory/12345")
    assert impact_file.impact_status == "skipped"
