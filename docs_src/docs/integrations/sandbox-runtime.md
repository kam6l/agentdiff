# Anthropic Sandbox Runtime Integration

Run AgentDiff transactions inside Anthropic's `srt` sandbox for true isolation.

## Overview

AgentDiff's **local runtime** provides evidence and policy evaluation but **does not enforce** filesystem or network boundaries. For untrusted code, pair it with the [Anthropic Sandbox Runtime](https://github.com/anthropics/sandbox-runtime) (`srt`) which provides kernel-level isolation.

```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENTDIFF + SRT                              │
├─────────────────────────────────────────────────────────────────┤
│  AgentDiff (outside sandbox)                                    │
│  ├── Manifest capture (pre/post)                                │
│  ├── Policy evaluation                                          │
│  ├── Blast-radius scoring                                       │
│  └── Selective recovery                                         │
│                              ↑                                  │
│                              │ wraps                            │
│                              ↓                                  │
│  SRT Sandbox (inside)                                          │
│  ├── Filesystem isolation (deny-by-default)                     │
│  ├── Network isolation (allowlist)                              │
│  ├── Process limits (cgroups)                                   │
│  └── Resource quotas (CPU, memory, disk)                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Installation

```bash
# Install srt (Anthropic Sandbox Runtime)
# See: https://github.com/anthropics/sandbox-runtime

# Verify srt is available
srt --version
```

```bash
# Install AgentDiff with sandbox extras
pip install "agentdiff[sandbox]"
```

---

## Quickstart

### 1. Configure Sandbox Settings

Create `sandbox-settings.json`:

```json
{
  "filesystem": {
    "allow_read": ["/workspace"],
    "allow_write": ["/workspace"]
  },
  "network": {
    "allow": ["api.github.com", "pypi.org"]
  },
  "resources": {
    "cpu_limit": 2.0,
    "memory_limit_mb": 2048,
    "disk_limit_mb": 4096
  },
  "process": {
    "max_processes": 50
  }
}
```

### 2. Create AgentDiff Policy

```yaml
# agentdiff-policy.yaml
schema_version: 1
filesystem:
  allow_write:
    - "src/**"
    - "tests/**"
  review:
    - "pyproject.toml"
    - "requirements*.txt"
  deny:
    - ".env*"
    - "*.pem"
    - "*.key"
  default: review
limits:
  max_owned_processes: 5
  max_observed_ports: 10
backup:
  enabled: true
```

### 3. Run Under SRT + AgentDiff

```bash
agentdiff run \
  --task "Fix parser in sandbox" \
  --sandbox-executable srt \
  --sandbox-settings sandbox-settings.json \
  -- python3 agent.py
```

### 4. What Happens

1. AgentDiff captures **pre-run manifest** (host filesystem)
2. AgentDiff launches `srt --settings sandbox-settings.json -- python3 agent.py`
3. SRT executes command in **isolated sandbox**
4. AgentDiff captures **post-run manifest** (host filesystem)
5. AgentDiff evaluates policy, computes blast radius, creates capsule
6. Results available via `agentdiff inspect <run-id>`

---

## Configuration

### CLI Flags

| Flag | Description |
|------|-------------|
| `--sandbox-executable PATH` | Path to `srt` binary (default: `srt` in PATH) |
| `--sandbox-settings PATH` | Sandbox settings JSON file |
| `--sandbox-timeout SECONDS` | Sandbox timeout (default: 300) |

### Python API

```python
from agentdiff.integrations import SandboxRuntimeAdapter

adapter = SandboxRuntimeAdapter(
    executable="srt",
    settings="sandbox-settings.json",
    observe_ports=True,
    poll_interval_seconds=0.05,
)

result = adapter.run(
    argv=["python3", "agent.py"],
    task_description="Fix parser in sandbox",
    timeout_seconds=300,
)

# Result includes both AgentDiff evidence AND sandbox enforcement logs
print(f"Sandbox exit code: {result.sandbox_exit_code}")
print(f"Sandbox logs: {result.sandbox_logs_path}")
```

---

## Sandbox Settings Reference

```json
{
  "filesystem": {
    "allow_read": ["/workspace", "/etc/ssl/certs"],
    "allow_write": ["/workspace"],
    "deny": ["/workspace/.env*", "/workspace/*.pem"]
  },
  "network": {
    "allow": ["api.github.com:443", "pypi.org:443", "registry.npmjs.org:443"],
    "deny": ["*:22", "*:3389"]
  },
  "resources": {
    "cpu_limit": 2.0,
    "memory_limit_mb": 2048,
    "disk_limit_mb": 4096,
    "pids_limit": 100
  },
  "process": {
    "max_processes": 50,
    "default_user": "sandbox"
  },
  "timeouts": {
    "exec": 300,
    "idle": 60
  }
}
```

---

## Evidence Correlation

When using SRT, AgentDiff correlates **host-level observation** with **sandbox enforcement**:

| Layer | What It Sees |
|-------|--------------|
| **SRT (enforcement)** | Blocked writes, denied network, killed processes |
| **AgentDiff (evidence)** | Actual mutations, observed ports, process tree |

### Combined Report

```bash
agentdiff inspect <run-id> --section all
```

Output includes:
```
Sandbox Enforcement:
  Filesystem: 3 writes blocked (deny list)
  Network: 1 connection denied (api.evil.com)
  Processes: 0 killed

AgentDiff Evidence:
  Mutations: 2 allowed, 1 review, 0 deny
  Blast radius: 12/100 (LOW)
  Processes: 3 owned descendants
  Ports: 1 new (localhost:8080)
```

---

## Best Practices

1. **Use SRT for untrusted code** — AgentDiff alone is observation, not enforcement
2. **Align policies** — Sandbox `deny` list should match AgentDiff `filesystem.deny`
3. **Share workspace** — Mount same `/workspace` in both for consistent paths
4. **Capture sandbox logs** -- `--sandbox-logs` flag saves SRT output for debugging

---

## Limitations

| Limitation | Workaround |
|------------|------------|
| SRT must be pre-installed | Bundle in Docker image |
| Path mapping between host/sandbox | Use same `/workspace` mount |
| SRT doesn't expose process tree to host | AgentDiff polls host `/proc` (best effort) |
| Network observation is host-level | Use SRT allowlist for enforcement |

---

## Next Steps

- [MCP Policy Hook](mcp-policy.md) — Block tool calls at MCP level
- [Custom Frameworks](custom.md) — Integrate with your agent framework
- [Runtime Model](../concepts/runtime.md) — Understand the evidence model