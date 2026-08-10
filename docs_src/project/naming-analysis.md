# Naming analysis

> Research date: 2026-08-10. This is product/registry research, not legal advice or trademark clearance.

## Finding

The `AgentDiff` name has a **severe search and category collision**, even though the exact package name was unclaimed on PyPI and npm when checked.

Active or recent uses include:

- `agentdiff-ai/agentdiff`: PR-time AI-agent behavior/capability diffs.[1]
- `agent-diff-bench/agent-diff`: a KDD 2026 project for deterministic state diffs over replica third-party APIs.[20]
- `codeprakhar25/agentdiff`: a regularly released, signed Git-native code-provenance CLI whose repository homepage is `getagentdiff.com`.[2]
- `sunilmallya/agentdiff`: another coding-agent attribution project.[3]
- several smaller GitHub projects using `agentdiff` for trajectory analysis, benchmarks, and review tools.

This creates three distinct confusions:

1. **Developer intent:** a search for “AgentDiff” can mean PR behavior review, API-state benchmarking, code provenance, or this repository's machine-state evaluator.
2. **CLI/package identity:** multiple projects document an `agentdiff` command. Even if only one currently owns a package registry name, shell-install distribution makes collisions real.
3. **Research/SEO identity:** Agent Diff Bench links a research paper and KDD proceedings, while other projects publish substantial product documentation under the same words.[20]

## Registry and domain facts

- PyPI returned HTTP 404 for `agentdiff` on 2026-08-10, so the exact Python distribution name was unclaimed at the time of the check.[16]
- npm returned HTTP 404 for `agentdiff` on 2026-08-10.[17]
- `codeprakhar25/agentdiff` identifies `https://getagentdiff.com` as its repository homepage and also uses `agentdiff.site` in its README.[2]
- Domain availability beyond those documented uses was not treated as verified; DNS/WHOIS probes were unavailable in this audit.

Package availability does **not** remove the branding collision. It only means this repository may still be able to reserve the Python package name before another project does.

## Trademark-risk screen

`AgentDiff` is highly descriptive: “agent” names the subject and “diff” names the operation. Descriptive names are usually harder to own distinctly, and the number of active uses increases confusion risk. No legal conclusion should be drawn from GitHub/package searches. Before a commercial launch or rename, obtain a proper trademark search in intended jurisdictions and classes.

## Options

### Option A — retain `AgentDiff` through the runtime-foundation release

Advantages:

- no import, CLI, URL, citation, or repository migration;
- the exact PyPI name was available when checked;
- existing users retain `AgentDiffConfig` and `AgentDiffSession` unchanged.

Costs:

- persistent SEO and CLI confusion;
- the strongest competing `agentdiff` projects already have clearer category associations;
- `getagentdiff.com` cannot serve as this project's unambiguous brand domain.

If retained, always pair it with a descriptor:

> **AgentDiff Runtime — local mutation evidence and conflict-safe recovery for autonomous agents.**

Do not call it simply “the AgentDiff standard.”

### Option B — rename before the first public package release

Advantages:

- clearer category ownership;
- less support confusion and fewer wrong-install incidents;
- a chance to encode the real product wedge rather than the old evaluator positioning.

Costs:

- atomic migration of repository metadata, import/package name, CLI, docs, badges, examples, CI, citations, and compatibility aliases;
- likely need for a deprecated `agentdiff` shim if a package has already been released;
- legal, registry, and domain clearance still required.

## Candidate directions

These are naming directions only; none is claimed available or legally cleared.

| Candidate | Strength | Risk |
|---|---|---|
| **AgentTxn** | Encodes the core agent-transaction model | Technical abbreviation; possible pronunciation friction |
| **StateFence** | Communicates state boundary and control | Broad security term; requires collision search |
| **RunFence** | Short and centered on bounded execution | May sound like sandboxing, which local mode cannot guarantee |
| **MutationGuard** | Directly describes the monitored risk | Long; “guard” may imply stronger blocking than observation mode |
| **ScopeFence** | Strong fit for intended-scope policy | Less explicit about recovery |
| **AgentAftermath** | Memorable and aligned with observed side effects | More editorial than infrastructure-oriented |
| **SafeRun** | Excellent CLI-level promise | Generic and likely difficult to own |
| **RevertAgent** | Makes recovery obvious | Understates observation, policy, and evidence |

## Recommendation

**Do not rename automatically in this implementation PR.** Preserve `AgentDiffConfig`, `AgentDiffSession`, repository URLs, and the CLI while the runtime architecture is still alpha.

However, make a deliberate go/no-go naming decision **before publishing the first `agentdiff` package or declaring a stable policy/artifact format**. The current collision is severe enough that postponing the decision until v1.0 would create unnecessary migration cost.

Near-term actions:

1. Use the descriptor **AgentDiff Runtime** in positioning.
2. Reserve the Python distribution name only through a reviewed release process; do not publish an empty placeholder.
3. Commission package/domain/trademark clearance for the short list.
4. If renaming, do it atomically with compatibility and migration documentation—never let two names coexist accidentally.

## Sources

1. [agentdiff-ai/agentdiff](https://github.com/agentdiff-ai/agentdiff)
2. [codeprakhar25/agentdiff](https://github.com/codeprakhar25/agentdiff)
3. [sunilmallya/agentdiff](https://github.com/sunilmallya/agentdiff)
16. [PyPI `agentdiff` registry endpoint](https://pypi.org/pypi/agentdiff/json)
17. [npm `agentdiff` registry endpoint](https://registry.npmjs.org/agentdiff)
20. [Agent Diff Bench](https://github.com/agent-diff-bench/agent-diff)
