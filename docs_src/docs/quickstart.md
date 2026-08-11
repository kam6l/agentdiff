# Quickstart

Run your first AgentDiff transaction in under 2 minutes.

## Prerequisites

- Python 3.11+
- Linux or macOS (Windows via WSL2)
- `git` for installation

---

## 1. Install AgentDiff

```bash tab="From source (recommended)"
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
pip install -e .
```

```bash tab="Binary (coming soon)"
# Pre-built binaries will be available on GitHub Releases
curl -fsSL https://agentdiff.dev/install.sh | bash
```

```bash tab="Docker"
docker run --rm -it -v $(pwd):/workspace ghcr.io/kam6l/agentdiff:latest \
  agentdiff run -- python3 /workspace/agent.py
```

Verify installation:
```bash
agentdiff --version
# agentdiff 0.1.0
```

---

## 2. Initialize a Policy

```bash
agentdiff policy init
```

This creates `agentdiff-policy.yaml` in your current directory:

```yaml
schema_version: 1
filesystem:
  allow_write:
    - "src/**"
    - "tests/**"
  review:
    - "pyproject.toml"
    - "requirements*.txt"
    - "Cargo.toml"
    - "package.json"
  deny:
    - ".env*"
    - "*.pem"
    - "*.key"
    - ".ssh/**"
    - ".aws/**"
  default: review
limits:
  max_owned_processes: 5
  max_observed_ports: 10
backup:
  enabled: true
  compression: zstd
```

> **Tip:** Run `agentdiff policy explain <path>` to see which rule matches a specific file.

---

## 3. Create a Test Agent

Create a simple script that makes some "mistakes":

```python
# agent.py
import os
import subprocess

# Intended change
with open("src/main.py", "w") as f:
    f.write('print("Hello, AgentDiff!")\n')

# Accidental dependency change (review)
with open("pyproject.toml", "w") as f:
    f.write('[tool.poetry]\nname = "demo"\n')

# Protected file creation (deny)
with open(".env", "w") as f:
    f.write('SECRET_KEY="oops"\n')

# Spawn a subprocess
subprocess.run(["sleep", "0.1"])
```

```bash
mkdir -p src
```

---

## 4. Run Under Observation

```bash
agentdiff run \
  --task "Demo: show mutations" \
  -- python3 agent.py
```

Output:
```
agentdiff: capturing pre-run manifest…
agentdiff: executing argv…
agentdiff: capturing post-run manifest…
agentdiff: evaluating policy…
agentdiff: computing blast radius…

Run ID: a1b2c3d4
Task: Demo: show mutations
Status: DENY (blast radius: 77/100)

Mutations:
  M  src/main.py           allow      (intended)
  M  pyproject.toml        review     (dependency manifest)
  +  .env                  deny       (protected environment file)

Processes: 1 owned descendant observed
Ports: 0 new listening ports

Evidence capsule: .agentdiff/runs/a1b2c3d4/
```

---

## 5. Inspect the Evidence

```bash
# Human-readable summary
agentdiff inspect a1b2c3d4

# Machine-readable JSON
agentdiff inspect a1b2c3d4 --format json

# Just the policy decisions
agentdiff inspect a1b2c3d4 --section policy
```

---

## 6. Recover Safely

```bash
# Dry run - see what would be reverted
agentdiff rollback a1b2c3d4 --safe-only --dry-run

# Revert only "safe" collateral (unchanged, non-conflicting)
agentdiff rollback a1b2c3d4 --safe-only

# Full rollback (requires confirmation)
agentdiff rollback a1b2c3d4
```

The `--safe-only` flag preserves:
- Files with **allow** decisions (your intended work)
- Files that were **modified after the run** (conflicts)
- Files matching **deny** that were later edited by you

---

## Next Steps

| Goal | Guide |
|------|-------|
| Understand the runtime model | [Runtime Model](concepts/runtime.md) |
| Write custom policies | [Mutation Policy](concepts/policy.md) |
| Learn blast-radius scoring | [Blast-Radius Scoring](concepts/blast-radius.md) |
| Use selective recovery | [Selective Recovery](concepts/recovery.md) |
| Full CLI reference | [CLI Reference](cli.md) |
| Python API | [Python API](api.md) |