# AgentDiff Documentation

**Runtime evidence and conflict-safe recovery for autonomous agents.**

---

<div class="ad-home" data-agentdiff-home>
  <a class="ad-skip" href="#main-content">Skip to content</a>

  <nav class="ad-nav" aria-label="Primary navigation">
    <a class="ad-brand" href="./" aria-label="AgentDiff home">
      <svg class="ad-brand__mark" viewBox="0 0 40 40" aria-hidden="true"><path d="M7 7h15v6h-9v14h9v6H7V7Z"></path><path d="M33 7v26H18v-6h9V13h-9V7h15Z"></path></svg>
      <span>AgentDiff</span>
    </a>
    <div class="ad-nav__links">
      <a href="#how-it-works">How it works</a>
      <a href="docs/overview/">Docs</a>
      <a href="docs/cli/">CLI</a>
      <a class="ad-nav__github" href="https://github.com/kam6l/agentdiff" target="_blank" rel="noopener">GitHub <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5.2 3.5h7.3v7.3h-1.4V5.9l-7.6 7.6-1-1 7.6-7.6H5.2V3.5Z"></path></svg></a>
    </div>
  </nav>

  <main id="main-content">
    <section class="ad-hero" aria-labelledby="hero-title">
      <div class="ad-hero__copy ad-reveal">
        <p class="ad-eyebrow"><span></span> Open source · Alpha · Local runtime</p>
        <h1 id="hero-title">See what the agent changed.<br><em>Undo only the collateral.</em></h1>
        <p class="ad-hero__lede">AgentDiff wraps a command with secure state capture, deterministic mutation policy, explainable blast radius, durable evidence, and conflict-safe selective recovery.</p>
        <div class="ad-actions">
          <a class="ad-button ad-button--primary" href="docs/overview/">Read the docs <span aria-hidden="true">→</span></a>
          <a class="ad-button ad-button--secondary" href="https://github.com/kam6l/agentdiff" target="_blank" rel="noopener">View source</a>
        </div>
        <div class="ad-install" aria-label="Install from source">
          <span class="ad-install__prompt" aria-hidden="true">$</span>
          <code id="install-command">git clone https://github.com/kam6l/agentdiff.git</code>
          <button class="ad-copy" type="button" data-copy-target="install-command" aria-label="Copy install command"><span class="ad-copy__label">Copy</span></button>
        </div>
      </div>

      <div class="ad-demo-wrap ad-reveal" style="--reveal-delay: 120ms">
        <div class="ad-demo-label"><span>Illustrative transaction</span><span>Run #example</span></div>
        <article class="ad-demo" aria-label="Illustrative AgentDiff transaction">
          <header class="ad-demo__header">
            <div class="ad-window-dots" aria-hidden="true"><i></i><i></i><i></i></div>
            <code>agentdiff run</code>
            <span class="ad-demo__live"><i></i> captured</span>
          </header>
          <div class="ad-demo__task">
            <div><span class="ad-micro">Task</span><strong>Fix the parser</strong></div>
            <div class="ad-demo__switch" role="group" aria-label="Illustrative run state">
              <button type="button" data-demo-state="clean" aria-pressed="false">Scoped run</button>
              <button class="is-active" type="button" data-demo-state="messy" aria-pressed="true">Actual run</button>
            </div>
          </div>
          <div class="ad-demo__score-row">
            <div class="ad-score" aria-live="polite"><span class="ad-score__value" data-demo-score>77</span><span class="ad-score__unit">/100</span></div>
            <div class="ad-score__context">
              <span class="ad-micro">Blast radius</span>
              <strong data-demo-summary>2 unexpected / 3 mutations</strong>
              <div class="ad-meter"><span data-demo-meter style="width:77%"></span></div>
            </div>
          </div>
          <div class="ad-demo__mutations" data-demo-mutations aria-live="polite">
            <div class="ad-mutation is-target"><span class="ad-mutation__type">M</span><code>src/parser.py</code><span>allow</span></div>
            <div class="ad-mutation is-warning"><span class="ad-mutation__type">M</span><code>pyproject.toml</code><span>review</span></div>
            <div class="ad-mutation is-warning"><span class="ad-mutation__type">+</span><code>.env</code><span>deny</span></div>
          </div>
          <footer class="ad-demo__footer"><span><i class="ad-verdict-dot"></i> Policy outcome</span><strong data-demo-verdict>DENY · CRITICAL</strong></footer>
        </article>
        <p class="ad-demo-note">Example data. The score is a deterministic sum of visible evidence.</p>
      </div>
    </section>

    <section class="ad-proof" aria-labelledby="proof-title">
      <div class="ad-section-heading ad-reveal">
        <p class="ad-kicker">01 / The missing runtime layer</p>
        <h2 id="proof-title">A correct answer can still leave an unsafe workspace.</h2>
      </div>
      <div class="ad-compare ad-reveal">
        <article class="ad-compare__panel ad-compare__panel--plain">
          <header><span>Task evaluation</span><span class="ad-status ad-status--pass">PASS</span></header>
          <div class="ad-compare__body">
            <p class="ad-micro">Agent response</p>
            <blockquote>"Parser fixed. All tests pass."</blockquote>
            <div class="ad-test-line"><span>✓</span><code>18 passed</code></div>
          </div>
          <footer>The requested outcome succeeded.</footer>
        </article>
        <div class="ad-compare__arrow" aria-hidden="true">+</div>
        <article class="ad-compare__panel ad-compare__panel--signal">
          <header><span>Runtime evidence</span><span class="ad-status ad-status--fail">DENY</span></header>
          <div class="ad-compare__body">
            <p class="ad-micro">Observed aftermath</p>
            <ul>
              <li><span class="is-good">01</span> allowed source file changed</li>
              <li><span class="is-bad">01</span> dependency manifest changed</li>
              <li><span class="is-bad">01</span> protected environment file created</li>
            </ul>
          </div>
          <footer>Keep the intended fix. Review or recover the rest.</footer>
        </article>
      </div>
    </section>

    <section class="ad-inspect" id="how-it-works" aria-labelledby="inspect-title">
      <div class="ad-section-heading ad-section-heading--split ad-reveal">
        <div><p class="ad-kicker">02 / Auditable evidence</p><h2 id="inspect-title">A decision for every mutation.</h2></div>
        <p>The local transaction combines no-follow manifests, exact rule provenance, process identity evidence, and versioned artifacts. It reports uncertainty instead of turning partial observation into ownership claims.</p>
      </div>

      <div class="ad-inspector ad-reveal">
        <div class="ad-inspector__tabs" role="tablist" aria-label="Runtime evidence layers">
          <button class="is-active" id="tab-manifest" role="tab" aria-selected="true" aria-controls="panel-manifest" data-inspector-tab="manifest"><span>01</span><strong>Manifest</strong><small>create · modify · delete</small></button>
          <button id="tab-policy" role="tab" aria-selected="false" aria-controls="panel-policy" data-inspector-tab="policy"><span>02</span><strong>Policy</strong><small>allow · review · deny</small></button>
          <button id="tab-recovery" role="tab" aria-selected="false" aria-controls="panel-recovery" data-inspector-tab="recovery"><span>03</span><strong>Recovery</strong><small>restore · retain · conflict</small></button>
          <button id="tab-processes" role="tab" aria-selected="false" aria-controls="panel-processes" data-inspector-tab="processes"><span>04</span><strong>Processes</strong><small>PID · creation time</small></button>
          <button id="tab-ports" role="tab" aria-selected="false" aria-controls="panel-ports" data-inspector-tab="ports"><span>05</span><strong>Ports</strong><small>machine-wide observation</small></button>
        </div>
        <div class="ad-inspector__stage">
          <header><span class="ad-micro">Run capsule evidence</span><span class="ad-inspector__count" data-inspector-count>3 changes</span></header>
          <div class="ad-inspector__panel" id="panel-manifest" role="tabpanel" aria-labelledby="tab-manifest" data-inspector-panel="manifest">
            <div class="ad-table-head"><span>Change</span><span>Resource</span><span>Decision</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--modify">M</span><code>src/parser.py</code><span class="ad-class ad-class--target">allow</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--modify">M</span><code>pyproject.toml</code><span class="ad-class ad-class--warning">review</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--create">+</span><code>.env</code><span class="ad-class ad-class--danger">deny</span></div>
          </div>
          <div class="ad-inspector__panel" id="panel-policy" role="tabpanel" aria-labelledby="tab-policy" data-inspector-panel="policy" hidden>
            <div class="ad-table-head"><span>Action</span><span>Rule</span><span>Pattern</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--create">A</span><code>filesystem.allow_write[0]</code><span class="ad-class ad-class--target">src/**</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--modify">R</span><code>filesystem.review[0]</code><span class="ad-class ad-class--warning">pyproject.toml</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--delete">D</span><code>filesystem.deny[0]</code><span class="ad-class ad-class--danger">.env</span></div>
          </div>
          <div class="ad-inspector__panel" id="panel-recovery" role="tabpanel" aria-labelledby="tab-recovery" data-inspector-panel="recovery" hidden>
            <div class="ad-table-head"><span>Path</span><span>Condition</span><span>Action</span></div>
            <div class="ad-table-row"><span class="ad-step-index">01</span><code>src/parser.py</code><span class="ad-class ad-class--target">retain allowed</span></div>
            <div class="ad-table-row"><span class="ad-step-index">02</span><code>.env</code><span class="ad-class ad-class--danger">delete if unchanged</span></div>
            <p class="ad-inspector__privacy">A later edit becomes a conflict and is preserved.</p>
          </div>
          <div class="ad-inspector__panel" id="panel-processes" role="tabpanel" aria-labelledby="tab-processes" data-inspector-panel="processes" hidden>
            <div class="ad-table-head"><span>Relation</span><span>Identity</span><span>Cleanup</span></div>
            <div class="ad-table-row"><span class="ad-step-index">01</span><code>PID + create_time</code><span class="ad-class ad-class--target">verified</span></div>
            <p class="ad-inspector__privacy">Polling is best effort; PID reuse or ambiguity causes refusal.</p>
          </div>
          <div class="ad-inspector__panel" id="panel-ports" role="tabpanel" aria-labelledby="tab-ports" data-inspector-panel="ports" hidden>
            <div class="ad-table-head"><span>Change</span><span>Endpoint</span><span>Attribution</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--create">+</span><code>127.0.0.1:8080</code><span class="ad-class ad-class--warning">machine-wide</span></div>
            <p class="ad-inspector__privacy">Observation only. AgentDiff does not claim child ownership or network enforcement.</p>
          </div>
          <footer><code>schema_version: 1</code><span>private local capsule</span></footer>
        </div>
      </div>
    </section>

    <section class="ad-metric" aria-labelledby="metric-title">
      <div class="ad-metric__intro ad-reveal">
        <p class="ad-kicker">03 / Explainable blast radius</p>
        <h2 id="metric-title">One score. Every point accounted for.</h2>
        <p>AgentDiff adds deterministic weights for protected paths, deletions, dependency files, mode changes, process residue, observed ports, and budget violations. The raw components remain visible.</p>
        <a class="ad-text-link" href="docs/concepts/blast-radius/">Read the scoring model <span aria-hidden="true">→</span></a>
      </div>
      <div class="ad-equation ad-reveal" style="--reveal-delay: 100ms">
        <div class="ad-equation__formula"><span>blast radius</span><strong>=</strong><div><b>Σ evidence weights</b><hr><b>capped at 100</b></div></div>
        <div class="ad-equation__example"><span class="ad-micro">Example</span><code>30 + 35 + 12 = 77</code><span class="ad-equation__gate">critical · inspect components</span></div>
      </div>
    </section>

    <section class="ad-workflow" aria-labelledby="workflow-title">
      <div class="ad-section-heading ad-section-heading--split ad-reveal">
        <div><p class="ad-kicker">04 / Framework neutral</p><h2 id="workflow-title">Wrap the command you already run.</h2></div>
        <p>No agent SDK is required. AgentDiff launches an explicit argument vector, records evidence, and leaves isolation to a real sandbox when one is needed.</p>
      </div>
      <div class="ad-workflow__body">
        <ol class="ad-steps ad-reveal">
          <li><span>01</span><div><strong>Declare boundaries</strong><p>Version allow, review, deny, limits, and backup policy.</p></div></li>
          <li><span>02</span><div><strong>Run locally</strong><p>Use shell-free argv execution with timeout and owned-process evidence.</p></div></li>
          <li><span>03</span><div><strong>Inspect evidence</strong><p>Review paths, rule provenance, score components, and warnings.</p></div></li>
          <li><span>04</span><div><strong>Recover selectively</strong><p>Retain allowed work; revert only unchanged collateral files.</p></div></li>
        </ol>
        <div class="ad-code-card ad-reveal" style="--reveal-delay: 100ms">
          <header><span>terminal</span><button type="button" class="ad-copy ad-copy--dark" data-copy-target="runtime-example"><span class="ad-copy__label">Copy</span></button></header>
          <pre id="runtime-example"><code><span class="c-comment"># Create a strict starter policy</span>
## What is AgentDiff?

AgentDiff is a local-first runtime layer that wraps any command an agent runs. It captures a secure **no-follow filesystem manifest** before and after execution, evaluates every mutation against a **versioned policy** (allow · review · deny), computes an **explainable blast-radius score**, and offers **conflict-safe selective recovery** — keeping intended changes while reverting only unchanged collateral.

## Why AgentDiff?

| Traditional Evaluation | AgentDiff |
|------------------------|-----------|
| "Did tests pass?" | "What exactly changed?" |
| Binary pass/fail | Quantified blast radius (0-100) |
| No visibility into side effects | Every mutation has a policy decision |
| All-or-nothing rollback | Keep intended work, revert only collateral |
| Framework-specific | Framework-neutral (wraps any argv) |

## Core Concepts

| Concept | Description |
|---------|-------------|
| **[Runtime Model](docs/concepts/runtime.md)** | Secure manifests, owned-process evidence, machine-wide port observation |
| **[Mutation Policy](docs/concepts/policy.md)** | Versioned allow/review/deny rules with exact rule provenance |
| **[Blast-Radius Scoring](docs/concepts/blast-radius.md)** | Deterministic additive weights, capped at 100, fully explainable |
| **[Selective Recovery](docs/concepts/recovery.md)** | Conflict-safe rollback that preserves later edits to reverted files |

## Quick Example

```bash
# Initialize a starter policy
agentdiff policy init

# Explain what a path would match
agentdiff policy explain .env

# Run any command under observation
agentdiff run \
  --task "Fix the parser" \
  -- python3 agent.py

<span class="c-comment"># Inspect and recover collateral files</span>
agentdiff inspect <run-id>
agentdiff rollback <run-id> --safe-only</code></pre>
          <footer><span>No-follow manifest</span><span>Versioned evidence</span><span>Conflict-safe recovery</span></footer>
        </div>
      </div>
    </section>

    <section class="ad-cta ad-reveal" aria-labelledby="cta-title">
      <p class="ad-kicker">Alpha, by design</p>
      <h2 id="cta-title">Evidence is useful only when its limits are visible.</h2>
      <p>The local backend is not a sandbox and does not block networking. Start in a disposable workspace, inspect the doctor report, and pair AgentDiff with real isolation for untrusted code.</p>
      <div class="ad-actions ad-actions--center"><a class="ad-button ad-button--light" href="docs/overview/">Start with the docs <span aria-hidden="true">→</span></a><a class="ad-button ad-button--outline-light" href="https://github.com/kam6l/agentdiff/issues" target="_blank" rel="noopener">Open an issue</a></div>
    </section>
  </main>

  <footer class="ad-footer">
    <a class="ad-brand ad-brand--footer" href="./"><svg class="ad-brand__mark" viewBox="0 0 40 40" aria-hidden="true"><path d="M7 7h15v6h-9v14h9v6H7V7Z"></path><path d="M33 7v26H18v-6h9V13h-9V7h15Z"></path></svg><span>AgentDiff</span></a>
    <p>Runtime evidence and conflict-safe recovery for autonomous agents.</p>
    <div><a href="docs/overview/">Documentation</a><a href="https://github.com/kam6l/agentdiff">GitHub</a><a href="https://github.com/kam6l/agentdiff/blob/main/SECURITY.md">Security</a></div>
    <span>© 2026 AgentDiff contributors</span>
  </footer>
</div>
=======
# Inspect the run capsule
agentdiff inspect <run-id>

# Recover only safe collateral
agentdiff rollback <run-id> --safe-only
```

## Next Steps

- **[Quickstart](docs/quickstart.md)** — Run your first observed transaction in 2 minutes
- **[Installation](docs/installation.md)** — Binary install, from source, or Docker
- **[Concepts](docs/concepts/runtime.md)** — Deep dive into the runtime model
- **[CLI Reference](docs/cli.md)** — Complete command documentation
