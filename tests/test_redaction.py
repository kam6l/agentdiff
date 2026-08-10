from __future__ import annotations

import json

from agentdiff.redaction import fingerprint, redact_argv, redact_data, safe_display


def test_fingerprint_is_stable_and_never_contains_the_value() -> None:
    first = fingerprint("visible-value")
    assert first == fingerprint("visible-value")
    assert first.startswith("sha256:")
    assert "visible-value" not in first


def test_redact_argv_handles_separate_and_inline_secret_flags() -> None:
    command = [
        "agent",
        "--api-key",
        "sk-secret",
        "--token=token-secret",
        "--name",
        "safe",
        "--password",
        "pass-secret",
    ]

    redacted = redact_argv(command)

    assert redacted == [
        "agent",
        "--api-key",
        "<redacted>",
        "--token=<redacted>",
        "--name",
        "safe",
        "--password",
        "<redacted>",
    ]
    assert "secret" not in json.dumps(redacted)


def test_redact_data_recurses_by_sensitive_key_without_logging_values() -> None:
    payload = {
        "tool": "filesystem.read_file",
        "arguments": {
            "path": "src/app.py",
            "authorization": "Bearer abc",
            "nested": [{"client_secret": "hidden"}, {"safe": "visible"}],
        },
    }

    redacted = redact_data(payload)
    serialized = json.dumps(redacted)

    assert redacted["arguments"]["authorization"] == "<redacted>"
    assert redacted["arguments"]["nested"][0]["client_secret"] == "<redacted>"
    assert redacted["arguments"]["nested"][1]["safe"] == "visible"
    assert "Bearer abc" not in serialized
    assert "hidden" not in serialized


def test_safe_display_escapes_terminal_control_sequences() -> None:
    malicious = "normal\x1b[31mred\x07\nnext"

    displayed = safe_display(malicious)

    assert "\x1b" not in displayed
    assert "\x07" not in displayed
    assert "\\x1b" in displayed
    assert "\\x07" in displayed
    assert "\n" in displayed
