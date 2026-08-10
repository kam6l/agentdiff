# Competitive landscape

> Research date: 2026-08-10. This is a source review, not an independent security audit. A check mark means the linked project documents the capability; it does not mean AgentDiff maintainers reproduced every claim.

## Executive conclusion

AgentDiff should not compete as another sandbox, trace UI, prompt evaluator, governance megasuite, or provenance tool. Mature projects already lead those categories:

- Microsoft Agent Governance Toolkit (AGT) has broad deterministic tool-call policy, identity, audit, MCP, runtime, and SRE surfaces.[4]
- E2B and Daytona provide isolated execution infrastructure; Daytona's public OSS repository became unmaintained in June 2026 as core development moved private.[5][6]
- Langfuse, Phoenix, OpenInference, and LangSmith have much broader tracing, evaluation, and observability ecosystems.[7][8][9][21]
- OpenHands runs coding agents across local, Docker, VM, and cloud backends.[10]
- Promptfoo and DeepEval are mature evaluation/red-team frameworks rather than machine-state recovery layers.[11][12]
- Agent Diff Bench evaluates agents against deterministic replicas of third-party APIs.[20]
- TracePact records, replays, and diffs tool-call behavior contracts.[19]
- MCP proxies already intercept protocol traffic and apply policy at that boundary.[14][15]
- AgentBranch isolates coding sessions in disposable Lima VMs and syncs work back through Git.[18]

The credible wedge is narrower:

> **Local-first evidence of real filesystem mutations, deterministic scope decisions, explainable blast radius, and conflict-safe selective recovery around an arbitrary child process.**

We did not find another active project in this review documenting that exact combination. This is not proof that none exists. Sandboxes provide isolation and snapshots, AgentBranch provides coarse session sync/discard, and governance/proxy products provide interception; AgentDiff should integrate with those strengths rather than recreate them.

## Capability matrix

Legend: **Y** documented; **P** partial, adapter-specific, or narrower than the column; **Ext** delegated to an external runtime; **—** not found in reviewed primary documentation; **N/A** outside the product's stated scope.

### Execution and state

| Project | Core problem | Executes agents | Sandbox | Filesystem state | Process state | Network state/control | Environment | API/DB state | Tool calls |
|---|---|---:|---|---|---|---|---|---|---|
| Microsoft AGT [4] | Application-layer agent governance | P | P / container recommended | P | P | P | — | P via governed tools | **Y, intercepted** |
| agentdiff-ai/agentdiff [1] | PR-time behavior/capability change review | P via harness | Explicitly no | Source/worktree evidence | — | — | — | P via normalized traces | **Y** |
| Agent Diff Bench [20] | Agent eval/RL against replica SaaS APIs | **Y** | API replicas | — | — | No real network side effects | — | **Y, deterministic replicas** | **Y** |
| codeprakhar25/agentdiff [2] | Signed Git-native AI code provenance | No | No | Git line attribution | — | — | — | — | P via agent hooks |
| E2B [5] | Managed isolated code execution | **Y** | **Cloud microVM** | **Y** | **Y** | **Y** | Runtime config | — | Command API |
| Daytona [6] | Managed development sandboxes | **Y** | **Container/compute plane** | **Y** | **Y** | Network limits | Runtime config | — | Process/toolbox API |
| OpenHands [10] | Coding-agent execution/control center | **Y** | Local/Docker/VM/cloud | Workspace | Runtime-dependent | Runtime-dependent | Runtime-dependent | Integrations | **Y** |
| AgentBranch [18] | Disposable coding-agent sessions | **Y** | **Lima VM** | Git sync/discard | VM-contained | VM-contained | VM-contained | — | Agent CLI |
| TracePact [19] | Behavioral contracts for agents | P | No | — | — | — | — | Tool-result cassettes | **Y, record/replay** |
| Langfuse [7] | LLM observability/evaluation | No | No | — | — | — | — | — | **Y, instrumented traces** |
| Phoenix [8] | AI observability/evaluation/troubleshooting | No | Ext for code evaluators | — | — | — | — | — | **Y, OTel traces** |
| OpenInference [9] | AI semantic conventions/instrumentation | No | No | — | — | — | — | — | **Y, instrumentation** |
| LangSmith [21] | Hosted tracing, debugging, and monitoring | No | No | — | — | — | — | — | **Y, instrumented traces** |
| Promptfoo [11] | LLM evals and red teaming | P test providers | P provider-specific | — | — | — | — | — | P |
| DeepEval [12] | Pytest-like LLM/agent evaluation | P user harness | No | — | — | — | — | — | **Y, evaluated trajectory** |
| mcp-watchdog [14] | MCP attack detection/proxy | Runs upstream MCP server | No | P scope monitor | — | P argument/SSRF checks | — | — | **Y, intercepted** |
| MCP Security Proxy [15] | Deny-by-default MCP policy boundary | Runs upstream MCP server | Explicitly no | Argument-level only | — | Argument-level only | — | — | **Y, intercepted** |

### Control, recovery, evidence, and operations

| Project | Deterministic policy | Rollback | Selective rollback | CI | MCP | Replay | Provenance/audit | Observability | Public benchmark | Offline/privacy | Framework lock-in | License / install UX |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Microsoft AGT [4] | **Y** | P saga/compensation | P | **Y** | **Y** | P | **Strong audit/identity** | **Y** | Conformance/security suites | Local core available | Low; many adapters | MIT; packaged in several ecosystems |
| agentdiff-ai/agentdiff [1] | **Y, PR capability plan** | — | — | **First-class** | — | Recorded harness | Evidence hashes/reports | PR reports | Deterministic zoo/lab | Local/BYOK | JS/TS strongest | AGPL-3.0; GitHub Action/local clone |
| Agent Diff Bench [20] | Assertions/contracts | Reset replica state | Scenario-level reset | P | — | Deterministic API state | Run diffs | Eval reports | **Core product** | Self-host option | SDK/adapters | MIT; Python/TS SDK |
| codeprakhar25/agentdiff [2] | Attribution policy | — | — | **Y** | P hook | — | **Signed line provenance** | Reports | — | Local-first | Coding-agent hooks | MIT/Apache; source installer |
| E2B [5] | Runtime controls | Snapshot/reset | Environment-level | P | — | Template/snapshot reuse | Runtime logs | Runtime metrics | — | Cloud by default; self-host infra | Low | Apache-2.0 SDK + API key |
| Daytona [6] | Platform/runtime limits | Snapshots | Environment-level | P | MCP server | Snapshot reuse | Audit logs | OTel | — | Managed product; old OSS code available | Low | Public OSS repo unmaintained |
| OpenHands [10] | Runtime-dependent | Workspace/session | Git/workspace-level | P | P | Session history | Run history | UI | SWE benchmarks adjacent | Local/self-host/cloud | ACP lowers lock-in | MIT; npm/Docker/source |
| AgentBranch [18] | Session policy | Discard VM | Sync or discard session | P | — | Checkpoint resume | Git bundle/session record | CLI | — | Local | Codex/Claude/Gemini | Apache-2.0; source build |
| TracePact [19] | Diff policy | — | — | **Y** | P | **First-class** | Cassettes/diffs | CLI reports | Contract tests | Local | JS/TS integrations | MIT; npm/npx |
| Langfuse [7] | Eval rules, not runtime policy | — | — | P | — | Trace/playground | Trace audit | **First-class** | Datasets/evals | Self-host or cloud | Low | MIT except enterprise folders; SDK/cloud |
| Phoenix [8] | Eval rules, not runtime policy | — | — | P | Read/query server | Trace replay/evals | Traces | **First-class** | Datasets/experiments | Local/self-host/cloud | Low | Elastic-2.0; `uvx`/pip |
| OpenInference [9] | No runtime policy | — | — | P | Instrumentation | — | Span semantics | Export standard | — | Local exporters possible | **Very low** | Apache-2.0; libraries |
| LangSmith [21] | Automations/evals, not OS policy | — | — | P | P | Trace/debug tools | Hosted traces | **First-class** | Datasets/evals | Hosted service | Low | Commercial service/SDK |
| Promptfoo [11] | Test/red-team assertions | — | — | **Y** | P | Eval reruns | Reports | UI/reports | **Y** | Evals local; providers may be remote | Low | MIT; npm/brew/pip |
| DeepEval [12] | Test assertions | — | — | **Y** | Eval metrics | Eval reruns | Test results | Optional platform | **Y** | Core local; judges/providers vary | Low | Apache-2.0; pip |
| mcp-watchdog [14] | **Y** | — | — | P | **Core product** | P drift baseline | JSON-RPC/security logs | Security events | Attack suite claimed | Local; optional LLM classifier | MCP-specific | MIT; source/PyPI |
| MCP Security Proxy [15] | **Y, deny by default** | — | — | **Y** | **Core product** | — | Redacted JSONL audit | Ops metrics optional | Compatibility fixtures | Local | MCP-specific | Apache-2.0; npm alpha |

## What others do better—and what to learn

| Group | What they do better today | Learn | Do not copy | Integration direction |
|---|---|---|---|---|
| Microsoft AGT [4] | Breadth, formal specs, fail-closed tool policy, identity, audit, conformance, adapters | Versioned contracts, explicit trust boundaries, evidence codes, honest middleware boundary | A sprawling multi-package governance platform | Export AgentDiff mutation evidence into AGT decisions/audit; do not duplicate identity/SRE |
| E2B and Daytona [5][6] | Isolation, runtime lifecycle, remote filesystem/process APIs, snapshots | Treat isolation as a backend protocol | Build another VM/cloud control plane | `AgentDiff + E2B`; evaluate a maintained Daytona API before advertising support |
| OpenHands and AgentBranch [10][18] | Agent execution UX and disposable workspaces | Explicit sync/discard, backend capability descriptions, warnings for unsandboxed mode | Build an agent IDE/control center | Wrap OpenHands/ACP commands; future VM backend adapter |
| Langfuse, Phoenix, OpenInference, LangSmith [7][8][9][21] | Tracing schemas, dashboards, datasets, broad framework integration | Export standard spans and keep telemetry optional | Build a hosted trace UI | OTel/OpenInference exporter into Phoenix/Langfuse-compatible collectors |
| agentdiff-ai [1] | PR-native reports, trusted-workspace integrity, capability-plan UX, deterministic evidence zoo | Put decisions where review happens; label integrity checks precisely | JS/TS import-graph analysis or sticky-comment platform first | Consume AgentDiff run artifacts in CI; keep product scopes clearly distinct |
| Agent Diff Bench [20] | Deterministic third-party API replicas and agent/RL benchmark | Scenario contracts and resettable external state | Recreate SaaS API simulators | Use Agent Diff Bench as an external-state provider/benchmark adapter |
| TracePact, Promptfoo, DeepEval [11][12][19] | Replayable tool behavior and rich eval ecosystems | Stable fixtures, deterministic contracts, pytest/CI ergonomics | Another generic LLM judge framework | Attach AgentDiff state evidence to their test cases/results |
| MCP security tools [14][15] | Protocol interception, deny-by-default policy, redaction, explicit non-sandbox disclaimers | Typed decision evidence and bounded payload handling | A second generic MCP firewall before the filesystem core is mature | Future MCP adapter should emit AgentDiff transaction events and defer protocol scanning where practical |
| Provenance AgentDiff [2] | Signed authorship and Git-native attribution | Durable, verifiable evidence and migration discipline | Line authorship | Cross-link run IDs and signed attribution as complementary evidence |

## AgentDiff strategy after research

### Build now

1. A generic argv-preserving local process wrapper.
2. Versioned local run artifacts with before/after filesystem manifests and redacted metadata.
3. Deterministic path policy with `allow`, `review`, and `deny` explanations.
4. Explainable blast-radius components.
5. Conservative file recovery: restore/delete only when current state still equals the recorded after-state.
6. Honest runtime capability reporting.

### Integrate later

- E2B or another maintained sandbox as a `RuntimeBackend`.
- OpenTelemetry/OpenInference export rather than a dashboard.
- OpenHands/ACP and coding-agent convenience adapters around the generic CLI.
- Agent Diff Bench for deterministic external-state scenarios.
- MCP policy/event adapters after the transaction core stabilizes.

### Intentionally do not build in the runtime-foundation release

- Universal network blocking on local Linux/macOS/Windows.
- A cloud sandbox service.
- A trace dashboard or hosted backend.
- LLM-as-final-policy authority.
- Arbitrary external-world rollback.
- A generic MCP attack scanner.
- Replay claims without a deterministic replay implementation.

## Post-implementation review criteria

Before calling the runtime foundation differentiated, verify all of the following in real tests:

- the wrapper preserves argv and never uses `shell=True`;
- a run produces complete, versioned, redacted artifacts;
- policy decisions are deterministic and explainable;
- rollback refuses to overwrite human edits after the run;
- symlinks, hardlinks, oversized files, and out-of-root paths fail safely;
- documented platform capabilities match `agentdiff doctor`;
- every advertised CLI example executes successfully.

## Sources

1. [agentdiff-ai/agentdiff](https://github.com/agentdiff-ai/agentdiff)
2. [codeprakhar25/agentdiff](https://github.com/codeprakhar25/agentdiff)
3. [sunilmallya/agentdiff](https://github.com/sunilmallya/agentdiff)
4. [Microsoft Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit)
5. [E2B](https://github.com/e2b-dev/E2B)
6. [Daytona](https://github.com/daytonaio/daytona)
7. [Langfuse](https://github.com/langfuse/langfuse)
8. [Arize Phoenix](https://github.com/Arize-ai/phoenix)
9. [OpenInference](https://github.com/Arize-ai/openinference)
10. [OpenHands](https://github.com/All-Hands-AI/OpenHands)
11. [Promptfoo](https://github.com/promptfoo/promptfoo)
12. [DeepEval](https://github.com/confident-ai/deepeval)
13. [Awesome Agent Runtime Security](https://github.com/bureado/awesome-agent-runtime-security)
14. [mcp-watchdog](https://github.com/bountyyfi/mcp-watchdog)
15. [MCP Security Proxy](https://github.com/0disoft/mcp-security-proxy)
16. [PyPI `agentdiff` registry endpoint](https://pypi.org/pypi/agentdiff/json)
17. [npm `agentdiff` registry endpoint](https://registry.npmjs.org/agentdiff)
18. [AgentBranch](https://github.com/REASY/agentbranch)
19. [TracePact](https://github.com/dcdeve/tracepact)
20. [Agent Diff Bench](https://github.com/agent-diff-bench/agent-diff)
21. [LangSmith Observability](https://docs.langchain.com/langsmith/observability)
