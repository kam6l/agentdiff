#!/usr/bin/env python3
"""Evaluate MCP-style calls without implementing or dispatching MCP transport."""

from __future__ import annotations

import json
from pathlib import Path

from agentdiff.integrations import MCPPolicyHook
from agentdiff.policy import load_policy_file


def main() -> None:
    policy = load_policy_file(Path(__file__).with_name("agentdiff.yaml"))
    hook = MCPPolicyHook(policy)
    examples = [
        hook.evaluate("filesystem.write_file", {"path": "src/app.py", "content": "..."}),
        hook.evaluate("filesystem.write_file", {"path": ".env", "content": "not retained"}),
        hook.evaluate("vendor.unknown", {"credential": "not retained"}),
    ]
    print(json.dumps([decision.to_dict() for decision in examples], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
