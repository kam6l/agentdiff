# Anthropic Sandbox Runtime

AgentDiff can delegate command execution to a preinstalled [Anthropic Sandbox Runtime](https://github.com/anthropic-experimental/sandbox-runtime) (`srt`) process while retaining AgentDiff's filesystem evidence, policy evaluation, scoring, capsule, inspection, and recovery workflow.

This is an optional external adapter. AgentDiff does not vendor, configure, audit, or reimplement SRT's operating-system controls.

## Install the external runtime

Follow the upstream platform prerequisites, then install its CLI:

```bash
npm install -g @anthropic-ai/sandbox-runtime
srt --help
agentdiff doctor
```

The upstream project is a research preview and its APIs or configuration can change. AgentDiff reports whether `srt` is currently discoverable, but detection does not prove that a settings file is safe or that host prerequisites are correctly configured.

## Run through SRT

Create and review an SRT settings file using the upstream schema. Then run:

```bash
agentdiff run \
  --runtime srt \
  --srt-settings /absolute/path/to/srt-settings.json \
  --policy agentdiff.yaml \
  -- python3 agent.py
```

Use `--srt-executable /absolute/path/to/srt` when the binary is not on `PATH`.

The adapter constructs one argv sequence:

```text
srt --settings /absolute/path/to/srt-settings.json <command> <arg> ...
```

It does not invoke a shell. Runtime evidence labels the backend as `anthropic-sandbox-runtime`, records the redacted wrapper argv, and labels enforcement as delegated OS enforcement.

## Security boundary

- SRT, not AgentDiff, implements filesystem and network enforcement.
- AgentDiff's deterministic filesystem policy still evaluates the observed post-run diff; it is not converted into an SRT configuration.
- A successful `srt` launch does not prove the supplied configuration is sufficiently restrictive.
- AgentDiff's current CI uses a fake executable to verify argv preservation, CLI wiring, and evidence labels. It does not certify upstream isolation.
- Process and listening-port evidence retains the same best-effort and machine-wide limitations as local mode.
- Selective recovery remains limited to eligible regular files captured by AgentDiff.

Use pinned upstream versions and review upstream release notes before production deployment.
