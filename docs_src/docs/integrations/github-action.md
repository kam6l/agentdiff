---
title: GitHub Action
description: Experimental deterministic trust report, JSON, and capsule artifact.
---

# GitHub Action (Experimental)

The repository includes a thin composite `action.yml`. It accepts an existing isolated run ID, verifies the capsule, runs clean-room proof, writes a GitHub step summary, emits `agentdiff-trust-report.json`, and uploads the complete capsule.

During repository development it can be exercised from a local action path:

```yaml
- name: AgentDiff trust report
  uses: ./
  with:
    run-id: ${{ steps.agent.outputs.run-id }}
    root: .
```

The intended distribution surface is:

```yaml
- uses: kam6l/agentdiff-action@v1
```

That standalone repository/tag is **Planned**, not published by this source PR. Until it exists, a consumer can pin a reviewed full commit SHA of this repository (`kam6l/agentdiff@<full-sha>`). The local `./` form is only for a workflow in a checkout of this repository.

The workflow run itself is the GitHub check. Proof/report steps are allowed to finish so `NOT_PROVEN` still produces a step summary and artifact; a final step enforces the verdict. The renderer makes both immediate and future risk, proof, tests, hidden state, integrity, and final verdict available as machine JSON and a downloadable artifact. There is no hosted dashboard.
