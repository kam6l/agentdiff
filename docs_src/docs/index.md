---
title: Documentation
description: Learn how AgentDiff records agent mutations, evaluates policy, scores blast radius, and performs conflict-safe recovery.
---

<span class="ad-doc-eyebrow">Getting started</span>

# AgentDiff Documentation

<div class="ad-doc-lede">AgentDiff is a local-first runtime transaction system for AI-agent commands. It records what changed, evaluates every mutation against deterministic policy, explains the run's blast radius, and can selectively undo unchanged collateral.</div>

<div class="ad-doc-notice" markdown>
<strong>Capability boundary:</strong> the local runtime observes a subprocess; it is not a kernel sandbox. Use an explicit sandbox runtime when you need isolation or network enforcement. [Read the trust model](trust.md).
</div>

## Start here

<div class="ad-doc-card-grid">
<a class="ad-doc-card ad-doc-card--featured" href="quickstart/">
<span>01 · Quickstart</span>
<strong>Record your first transaction</strong>
<p>Initialize policy, wrap a real command, inspect the evidence, and safely recover collateral.</p>
<em>About 5 minutes →</em>
</a>
<a class="ad-doc-card" href="concepts/runtime/">
<span>02 · Mental model</span>
<strong>Understand the runtime</strong>
<p>Learn what AgentDiff observes, what it can prove, and where enforcement begins and ends.</p>
<em>Read the runtime model →</em>
</a>
<a class="ad-doc-card" href="concepts/policy/">
<span>03 · Governance</span>
<strong>Decide before you score</strong>
<p>Give each path an allow, review, or deny result with exact rule provenance.</p>
<em>Write a policy →</em>
</a>
<a class="ad-doc-card" href="concepts/recovery/">
<span>04 · Recovery</span>
<strong>Undo only the collateral</strong>
<p>Preserve allowed work and refuse to overwrite paths changed after the run.</p>
<em>See safe rollback →</em>
</a>
</div>

## The transaction loop

<div class="ad-doc-steps">
<div><span>1</span><strong>Capture</strong><p>Build a no-follow filesystem manifest and record the runtime baseline.</p></div>
<div><span>2</span><strong>Execute</strong><p>Launch the explicit argv under local observation or a selected sandbox backend.</p></div>
<div><span>3</span><strong>Evaluate</strong><p>Diff state, apply policy, score blast radius, and persist an integrity manifest.</p></div>
<div><span>4</span><strong>Recover</strong><p>Conflict-check current state before restoring or removing eligible collateral.</p></div>
</div>

## Feature status

| Status | Implemented surface |
|---|---|
| **Beta** | Local transactions, policy, capsules, verification, scoring, and regular-file recovery |
| **Experimental** | `srt` adapter, MCP policy hook, LangChain callback, and legacy evaluator |
| **Planned** | Published packages, authenticated capsules, telemetry export, and a maintained hosted sandbox integration |

There is no HTTP server, hosted dashboard, Docker backend, bundled sandbox, or claimed PyPI release.

## A complete local run

The following shape is taken from a real repository run. AgentDiff reported a successful process exit, but denied the transaction because it created a protected environment file.

=== "Observe"

    ```bash
    agentdiff run \
      --task "Update the parser" \
      -- python3 agent_task.py
    ```

    ```text
    Task completed

    Expected changes:   1
    Unexpected changes: 1
    Protected changes:  1

    Blast Radius: CRITICAL (81/100)
    Recovery available: YES
    Policy outcome: DENY

    Status: denied (deny)
    Mutations: 3
      deny   created  .env
      review created  pyproject.toml
      allow  created  src/parser.py
    ```

=== "Inspect"

    ```bash
    agentdiff inspect <run-id>
    agentdiff verify <run-id>
    ```

    ```text
    Status: denied (deny)
    Blast radius: 81/100
    Capsule integrity: true
    ```

=== "Recover"

    ```bash
    agentdiff rollback <run-id> --safe-only
    ```

    ```text
    Actions: 2
      removed  .env
      removed  pyproject.toml
    Conflicts: 0
    Skipped: 1
    ```

## Choose your next path

<div class="ad-doc-link-list" markdown>
- **Install AgentDiff** — supported source installation and requirements. [Installation →](installation.md)
- **Use the CLI** — exact commands and flags implemented in `v0.1.0`. [CLI reference →](cli/index.md)
- **Integrate a command or framework** — use the transaction API, or the separately labeled experimental compatibility hooks. [Integrations →](integrations/custom.md)
- **Review the security boundary** — explicit guarantees, observations, and non-goals. [Security & limits →](trust.md)
</div>
