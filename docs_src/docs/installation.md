# Installation

Multiple ways to get AgentDiff running.

## From Source (Recommended)

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
pip install -e .
```

### Development Install

```bash
pip install -e ".[dev]"
pre-commit install
```

Run tests:
```bash
pytest -v
```

---

## Docker

```bash
# Latest stable
docker pull ghcr.io/kam6l/agentdiff:latest

# Specific version
docker pull ghcr.io/kam6l/agentdiff:v0.1.0

# Run with workspace mounted
docker run --rm -it \
  -v $(pwd):/workspace \
  -w /workspace \
  ghcr.io/kam6l/agentdiff:latest \
  agentdiff run -- python3 agent.py
```

### Docker Build from Source

```bash
docker build -t agentdiff:local .
docker run --rm -it -v $(pwd):/workspace -w /workspace agentdiff:local agentdiff --help
```

---

## Binary Releases (Coming Soon)

Pre-built binaries for Linux, macOS (Intel & Apple Silicon), and Windows will be available on [GitHub Releases](https://github.com/kam6l/agentdiff/releases).

```bash
# Linux x86_64
curl -fsSL https://github.com/kam6l/agentdiff/releases/download/v0.1.0/agentdiff-linux-x86_64.tar.gz | tar xz
sudo mv agentdiff /usr/local/bin/

# macOS (Apple Silicon)
curl -fsSL https://github.com/kam6l/agentdiff/releases/download/v0.1.0/agentdiff-darwin-arm64.tar.gz | tar xz
sudo mv agentdiff /usr/local/bin/

# Windows (via Scoop - coming)
scoop bucket add agentdiff https://github.com/kam6l/scoop-bucket
scoop install agentdiff
```

---

## Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.11 | 3.12+ |
| OS | Linux, macOS, WSL2 | Linux (kernel 5.10+) |
| Filesystem | ext4, APFS, NTFS | ext4 with `CAP_DAC_READ_SEARCH` |
| Memory | 256 MB | 512 MB+ |
| Disk | 50 MB | 200 MB+ (for run capsules) |

### Linux Capabilities

For full process observation, AgentDiff benefits from:

```bash
# Allow reading /proc/<pid>/stat for any process
sudo setcap cap_dac_read_search=+ep $(which python3)
```

Without this, process ancestry verification falls back to best-effort polling.

---

## Shell Completion

```bash tab="bash"
agentdiff completion bash > /etc/bash_completion.d/agentdiff
```

```bash tab="zsh"
agentdiff completion zsh > "${fpath[1]}/_agentdiff"
```

```bash tab="fish"
agentdiff completion fish > ~/.config/fish/completions/agentdiff.fish
```

---

## Verify Installation

```bash
agentdiff --version
agentdiff doctor
```

`agentdiff doctor` runs a self-check:
- Manifest scanner integrity
- Policy parser validation
- Blast-radius weight sanity
- Backup/restore round-trip
- Process observation capability

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `PermissionError` on `/proc` | Run with `CAP_DAC_READ_SEARCH` or as root |
| `zstd` not found | `pip install zstandard` or `apt install zstd` |
| Slow manifest scan | Exclude `node_modules`, `.git`, `target/` in policy |
| Docker: `Operation not permitted` | Run with `--cap-add=CAP_DAC_READ_SEARCH --security-opt apparmor=unconfined` |

---

## Next Steps

- [Quickstart](quickstart.md) — Run your first transaction
- [Mutation Policy](concepts/policy.md) — Customize allow/review/deny rules
- [CLI Reference](cli.md) — All commands and flags