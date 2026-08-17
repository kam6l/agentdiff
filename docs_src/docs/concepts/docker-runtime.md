---
title: Docker isolation
description: DockerRuntime private workspace, security defaults, evidence, and limits.
---

# Docker runtime

`DockerRuntime` copies the observed source into a private temporary directory and mounts only that copy at `/workspace`. The original repository and Docker socket are not mounted.

```bash
agentdiff run \
  --runtime docker \
  --docker-image your-agent-image@sha256:<digest> \
  --task "Fix authentication" \
  -- codex
```

The image must contain `codex` (or whichever executable follows `--`). AgentDiff does not install an agent into the image or inherit credentials automatically.

## Requested defaults

| Control | Default |
|---|---|
| Container user | Current non-root POSIX UID/GID, otherwise `65532:65532` |
| Host repository | Not mounted |
| Docker socket | Not mounted |
| Container root | Read-only |
| Workspace | Private writable bind mount |
| Linux capabilities | `ALL` dropped |
| Privilege escalation | `no-new-privileges` |
| Network | `none` |
| CPU | `1.0` |
| Memory | `512m` |
| PIDs | `64` |
| Environment | No host variables unless repeated `--env NAME` |
| Lifetime | Container force-removed after result collection |

Use `--docker-network bridge`, `--docker-cpus`, `--docker-memory`, and `--docker-pids` only after reviewing the expanded risk. Raw allowlisted environment values are passed through Docker by name and are not written into runtime argv evidence.

## Evidence

Runtime evidence records the image reference/digest (when inspectable), user, mount posture, network mode, caps, NNP, resource limits, allowlist names, container ID, cleanup, and explicit capability levels.

`SANDBOXED` means the mutation stayed inside the configured container/private-workspace boundary. It does not mean virtual-machine isolation. A compromised daemon, kernel, image, or administrator policy remains outside the guarantee.

Run `agentdiff doctor --format json` to distinguish an installed Docker CLI from an available daemon.
