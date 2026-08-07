# AgentDiff - Project Plan

## Vision
**The open-source standard for full-state trajectory evaluation of AI agents** — detecting not just *what the agent said*, but *what the agent did to the world*.

## Unique Differentiators (What We Have That Nobody Else Does)

| Feature | AgentDiff | Promptfoo | DeepEval | agentbranch | LangSmith |
|---------|-----------|-----------|----------|-------------|-----------|
| Filesystem diff (content hashes) | ✅ | ❌ | ❌ | ❌ | ⚠️ traces only |
| Environment variable diff | ✅ | ❌ | ❌ | ❌ | ❌ |
| Process tree diff | ✅ | ❌ | ❌ | ❌ | ❌ |
| Open port diff | ✅ | ❌ | ❌ | ❌ | ❌ |
| Cleanliness Score (target vs unintended) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Side effect classification (CRITICAL/WARNING/INFO) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Framework-agnostic (no SDK lock-in) | ✅ | ⚠️ | ⚠️ | ❌ | ❌ |
| Record & replay trajectories | ✅ | ⚠️ traces | ❌ | ❌ | ✅ |
| CI/CD friendly (exit codes, JSON) | ✅ | ✅ | ✅ | ❌ | ⚠️ |
| Pure Python, zero heavy deps | ✅ | ❌ Node | ❌ heavy | ❌ Next.js | ❌ |

## Core Features (Implemented)

### 1. DiffEngine (`diff_engine.py`)
- **Filesystem snapshots**: SHA256 content hashes, metadata (mode, size, mtime), directory trees
- **Environment snapshots**: Full env var capture with filtering
- **Process snapshots**: PID, PPID, cmdline, memory, CPU
- **Network snapshots**: Open ports (TCP/UDP), listening processes
- **Diff computation**: Added/Modified/Deleted with type classification

### 2. TrajectoryTracker (`trajectory.py`)
- **StepRecorder**: thought → tool_call → observation → result
- **Loop detection**: Detects repeated tool calls, circular reasoning
- **Token tracking**: Input/output tokens per step
- **Save/Load**: JSON serialization for regression testing

### 3. AgentDiffEvaluator (`evaluator.py`)
- **Cleanliness Score** = Target Mutations / Total Mutations
- **Efficiency Score** = Penalizes loops, failures, redundant steps
- **Side Effect Classification**: 
  - CRITICAL: File deletions, process kills, port closes, env var removal
  - WARNING: Unexpected file modifications, creations, env additions
  - INFO: Expected changes, read operations
- **Pass/Fail**: Configurable thresholds

## Missing Features (To Implement)

### High Priority (Community Requested)
1. **Framework Adapters** - LangChain, CrewAI, AutoGen, LangGraph, OpenAI Assistants callbacks
2. **Database/API Diffing** - SQL state, REST/GraphQL response diffing
3. **CLI Enhancement** - `agentdiff eval`, `agentdiff diff`, `agentdiff replay`
4. **GitHub Action** - Ready-to-use workflow
5. **Pre-commit Hook** - Local trajectory validation

### Medium Priority
6. **Visual Diff Report** - HTML report with side-by-side diffs
7. **MCP Server** - For Claude Code / Cursor integration
8. **Web Dashboard** - Optional, for trajectory visualization
9. **Plugin System** - Custom diff types, custom graders

### Lower Priority
10. **Multi-agent Trajectory** - Cross-agent state correlation
11. **Time-travel Debugging** - Step back to any snapshot
12. **Cost Tracking** - API cost per trajectory

## Open Source Readiness Checklist

### Documentation
- [ ] README.md with quickstart, architecture, examples
- [ ] CONTRIBUTING.md
- [ ] CODE_OF_CONDUCT.md
- [ ] docs/architecture.md
- [ ] docs/api_reference.md
- [ ] docs/framework_integration.md
- [ ] examples/ (LangChain, CrewAI, raw Python)

### CI/CD
- [ ] GitHub Actions: test, lint, typecheck, build
- [ ] Release workflow (semantic versioning)
- [ ] PyPI publishing
- [ ] Dependabot / Renovate config

### Community
- [ ] Issue templates (bug, feature, question)
- [ ] PR template
- [ ] Discussion categories (Ideas, Q&A, Show and Tell)
- [ ] Discord/Slack link
- [ ] Badge: PyPI version, license, tests, coverage

### Quality
- [ ] Type hints throughout (pyright/strict)
- [ ] Test coverage > 85%
- [ ] Pre-commit: ruff, mypy, pytest
- [ ] Security: bandit, pip-audit

## Target Users & Use Cases

| User | Use Case | Entry Point |
|------|----------|-------------|
| Agent Framework Dev | Regress agent behavior across versions | `agentdiff eval` in CI |
| AI Engineer | Debug why agent broke production | `agentdiff replay trajectory.json` |
| Researcher | Measure "collateral damage" of agents | Cleanliness Score metric |
| QA/Platform Team | Gate agent deployments | GitHub Action + threshold |
| Open Source Maintainer | Verify PR doesn't break agent behavior | Pre-commit + CI |

## Roadmap

### v0.1 (Current) - Core Engine ✅
- DiffEngine, TrajectoryTracker, Evaluator
- Basic demo, 10 passing tests

### v0.2 - Developer Experience
- CLI commands (`eval`, `diff`, `replay`, `init`)
- Framework adapters (LangChain, CrewAI, AutoGen)
- GitHub Action template
- HTML report generator

### v0.3 - Ecosystem
- MCP server for Claude Code
- Pre-commit hook
- Plugin system for custom diffs
- Web dashboard (optional, separate repo)

### v1.0 - Production Ready
- Database/API diffing
- Multi-agent support
- Stability guarantees
- 1.0 release, semantic versioning

## Success Metrics

- **GitHub Stars**: 500+ in 6 months
- **PyPI Downloads**: 10k+/month
- **Framework Adapters**: 5+ community contributed
- **CI Integration**: Used in 3+ major agent frameworks
- **Academic Citations**: Referenced in agent evaluation papers