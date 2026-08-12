---
title: Policy commands
description: Initialize, validate, and explain AgentDiff mutation policy.
---

<span class="ad-doc-eyebrow">CLI · Policy</span>

# Policy commands

Policy maps observed evidence to deterministic `allow`, `review`, or `deny` outcomes. The CLI provides three implemented subcommands.

## Initialize

```bash
agentdiff policy init [--output PATH] [--force]
```

By default, this writes a conservative `agentdiff.yaml` in the current directory and refuses to overwrite an existing file.

```bash
agentdiff policy init
agentdiff policy init --output config/agentdiff.yaml
```

Use `--force` only when replacing the destination is intentional.

## Validate

```bash
agentdiff policy validate [--policy PATH]
```

```bash
agentdiff policy validate --policy agentdiff.yaml
```

Validation checks schema version, supported actions and modes, numeric limits, and rule structure before a transaction uses the policy.

## Explain a path

```bash
agentdiff policy explain <path> [--policy PATH] [--format summary|json]
```

```bash
agentdiff policy explain .env --policy agentdiff.yaml
agentdiff policy explain src/parser.py --format json
```

The result includes the selected action and exact matching rule, which is useful for policy reviews and debugging precedence.

## Rule order

Filesystem decisions use the defined precedence and preserve rule provenance. See [Mutation policy](../concepts/policy.md) for the schema, path normalization, and fail-closed behavior.

!!! info "Policy is evaluation in local mode"
    A deny outcome does not turn the local observer into a filesystem sandbox. Command-level policy can block launch; mutation policy classifies the state observed around execution.
