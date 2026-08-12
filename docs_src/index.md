---
title: See what the agent changed
hide:
  - navigation
  - toc
  - footer
description: See exactly what an AI agent changed and selectively undo only the collateral damage.
---

<div class="ad-home" data-agentdiff-home>
  <a class="ad-skip" href="#main-content">Skip to content</a>

  <header class="ad-site-header" data-site-header>
    <nav class="ad-site-nav" aria-label="Main navigation">
      <a class="ad-wordmark" href="./" aria-label="AgentDiff home">
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <path d="M10 5H5v22h5M22 5h5v22h-5" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
          <path d="M13 12h6M13 20h6" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
        </svg>
        <span>AgentDiff</span>
      </a>

      <button class="ad-menu-button" type="button" aria-expanded="false" aria-controls="ad-nav-links" data-menu-toggle>
        <span></span><span></span>
        <span class="ad-visually-hidden">Toggle navigation</span>
      </button>

      <div class="ad-site-nav__links" id="ad-nav-links" data-menu>
        <a href="#evidence">Evidence</a>
        <a href="#recovery">Recovery</a>
        <a href="#trust">Trust model</a>
        <a href="docs/">Docs</a>
        <a class="ad-nav-cta" href="https://github.com/kam6l/agentdiff">GitHub <span aria-hidden="true">↗</span></a>
      </div>
    </nav>
  </header>

  <main id="main-content">
    <section class="ad-hero" aria-labelledby="ad-hero-title">
      <div class="ad-hero__texture" aria-hidden="true"></div>
      <div class="ad-hero__copy">
        <p class="ad-pill"><span></span> Open source · alpha · local-first</p>
        <h1 id="ad-hero-title">See what the agent changed.<br><em>Undo only the collateral.</em></h1>
        <p class="ad-hero__lede">AgentDiff wraps any command with secure state capture, deterministic mutation policy, explainable blast-radius scoring, durable evidence, and conflict-safe selective recovery.</p>
        <div class="ad-hero__actions">
          <a class="ad-button ad-button--light" href="docs/quickstart/">Run your first transaction <span aria-hidden="true">→</span></a>
          <a class="ad-button ad-button--ghost" href="https://github.com/kam6l/agentdiff">View source <span aria-hidden="true">↗</span></a>
        </div>
        <div class="ad-command" aria-label="Install from source">
          <span class="ad-command__prompt" aria-hidden="true">$</span>
          <code id="ad-install-command">git clone https://github.com/kam6l/agentdiff.git</code>
          <button type="button" data-copy-target="ad-install-command"><span data-copy-label>Copy</span></button>
        </div>
        <p class="ad-hero__note">Observation by default. External sandbox enforcement when you explicitly choose it.</p>
      </div>

      <div class="ad-proof-stage" aria-label="Real AgentDiff transaction example">
        <div class="ad-proof-stage__topline">
          <span>REAL LOCAL TRANSACTION</span>
          <span>RUN · E45C0D69</span>
        </div>
        <article class="ad-run-card" data-run-card>
          <header class="ad-run-card__header">
            <div class="ad-window-dots" aria-hidden="true"><i></i><i></i><i></i></div>
            <code>agentdiff / evidence capsule</code>
            <span class="ad-runtime-status"><i></i> recorded</span>
          </header>

          <div class="ad-run-card__task">
            <div>
              <span class="ad-ui-label">TASK</span>
              <strong>Update the parser</strong>
            </div>
            <div class="ad-state-switch" role="group" aria-label="Transaction state">
              <button type="button" class="is-active" aria-pressed="true" data-run-state="observed">Observed</button>
              <button type="button" aria-pressed="false" data-run-state="recovered">Recovered</button>
            </div>
          </div>

          <div class="ad-run-card__body">
            <div class="ad-mutation-table">
              <div class="ad-table-head"><span>CHANGE</span><span>RESOURCE</span><span>POLICY</span></div>
              <div data-run-mutations>
                <div class="ad-mutation-row is-deny"><b>+</b><code>.env</code><span>deny</span></div>
                <div class="ad-mutation-row is-review"><b>+</b><code>pyproject.toml</code><span>review</span></div>
                <div class="ad-mutation-row is-allow"><b>+</b><code>src/parser.py</code><span>allow</span></div>
              </div>
            </div>
            <div class="ad-score-block">
              <span class="ad-ui-label" data-score-label>BLAST RADIUS</span>
              <div class="ad-score-line"><strong data-run-score>81</strong><span>/100</span></div>
              <div class="ad-score-track"><i data-run-meter style="width:81%"></i></div>
              <b class="ad-verdict" data-run-verdict>DENY · CRITICAL</b>
            </div>
          </div>
          <footer class="ad-run-card__footer">
            <code data-run-summary>3 mutations · exit code 0</code>
            <span data-run-action>inspect evidence →</span>
          </footer>
        </article>
        <p class="ad-proof-stage__caption">Generated from an actual AgentDiff run. Example values are committed to the documentation.</p>
      </div>
    </section>

    <section class="ad-proof-strip" aria-label="Verified capabilities" tabindex="0">
      <span>Wraps any explicit argv</span>
      <span>No-follow manifests</span>
      <span>Deterministic policy</span>
      <span>0–100 explainable score</span>
      <span>Conflict-safe rollback</span>
    </section>
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

    <section class="ad-problem ad-section" id="evidence">
      <div class="ad-section-label"><span>01</span> The missing runtime layer</div>
      <div class="ad-problem__heading">
        <h2>The command succeeded.<br><em>The workspace didn’t.</em></h2>
        <p>Tests and traces can tell you what an agent returned. AgentDiff records the state it left behind—then gives every mutation a decision you can audit.</p>
      </div>
      <div class="ad-problem__grid">
        <article class="ad-story-card ad-story-card--light">
          <div class="ad-story-card__meta"><span>WITHOUT AGENTDIFF</span><span>EXIT 0</span></div>
          <p class="ad-story-card__quote">“Parser fixed.”</p>
          <div class="ad-terminal-fragment">
            <span class="is-green">✓</span> <code>tests/test_parser.py</code><br>
            <span class="is-green">✓</span> 42 passed in 1.8s
          </div>
          <footer>Outcome visible. Side effects invisible.</footer>
        </article>
        <article class="ad-story-card ad-story-card--dark">
          <div class="ad-story-card__meta"><span>WITH AGENTDIFF</span><span>3 MUTATIONS</span></div>
          <ul class="ad-change-list">
            <li><b class="is-deny">DENY</b><code>.env</code><span>created</span></li>
            <li><b class="is-review">REVIEW</b><code>pyproject.toml</code><span>created</span></li>
            <li><b class="is-allow">ALLOW</b><code>src/parser.py</code><span>created</span></li>
          </ul>
          <footer>Every decision includes the matching rule.</footer>
        </article>
      </div>
    </section>

    <section class="ad-inspector ad-section" aria-labelledby="ad-inspector-title">
      <div class="ad-section-label"><span>02</span> Auditable evidence</div>
      <div class="ad-inspector__intro">
        <h2 id="ad-inspector-title">One capsule.<br>Every relevant layer.</h2>
        <p>Secure manifests, policy provenance, score components, process identity, machine-wide port observations, and recovery events stay together in a versioned local capsule.</p>
      </div>

      <div class="ad-inspector__shell">
        <div class="ad-inspector__tabs" role="tablist" aria-label="Evidence layers">
          <button id="evidence-tab-manifest" role="tab" aria-selected="true" aria-controls="evidence-panel-manifest" tabindex="0" data-evidence-tab="manifest"><span>01</span> Manifest</button>
          <button id="evidence-tab-policy" role="tab" aria-selected="false" aria-controls="evidence-panel-policy" tabindex="-1" data-evidence-tab="policy"><span>02</span> Policy</button>
          <button id="evidence-tab-score" role="tab" aria-selected="false" aria-controls="evidence-panel-score" tabindex="-1" data-evidence-tab="score"><span>03</span> Score</button>
          <button id="evidence-tab-recovery" role="tab" aria-selected="false" aria-controls="evidence-panel-recovery" tabindex="-1" data-evidence-tab="recovery"><span>04</span> Recovery</button>
        </div>
        <div class="ad-inspector__content">
          <div class="ad-inspector__titlebar"><span>RUN CAPSULE · 20260811T110755Z-E45C0D69A41E</span><span data-evidence-count>3 filesystem mutations</span></div>

          <section id="evidence-panel-manifest" role="tabpanel" aria-labelledby="evidence-tab-manifest" data-evidence-panel="manifest">
            <div class="ad-evidence-grid">
              <div><span>before.json</span><strong>secure manifest</strong><small>lstat · no-follow opens</small></div>
              <div><span>after.json</span><strong>secure manifest</strong><small>created · modified · deleted</small></div>
              <div><span>integrity.json</span><strong>9 files verified</strong><small>SHA-256 checksum manifest</small></div>
            </div>
          </section>

          <section id="evidence-panel-policy" role="tabpanel" aria-labelledby="evidence-tab-policy" data-evidence-panel="policy" hidden>
            <div class="ad-policy-lines">
              <div><code>.env</code><b class="is-deny">deny</b><span>filesystem.deny → .env</span></div>
              <div><code>pyproject.toml</code><b class="is-review">review</b><span>filesystem.review → pyproject.toml</span></div>
              <div><code>src/parser.py</code><b class="is-allow">allow</b><span>filesystem.allow_write → src/**</span></div>
            </div>
          </section>

          <section id="evidence-panel-score" role="tabpanel" aria-labelledby="evidence-tab-score" data-evidence-panel="score" hidden>
            <div class="ad-score-breakdown">
              <div><span>Denied mutation</span><i style="--amount:44%"></i><b>+45</b></div>
              <div><span>Dependency file</span><i style="--amount:34%"></i><b>+35</b></div>
              <div><span>Created resources</span><i style="--amount:1%"></i><b>+1</b></div>
              <div class="is-total"><span>Blast radius</span><i style="--amount:81%"></i><b>81</b></div>
            </div>
          </section>

          <section id="evidence-panel-recovery" role="tabpanel" aria-labelledby="evidence-tab-recovery" data-evidence-panel="recovery" hidden>
            <div class="ad-recovery-log">
              <p><b>removed</b><code>.env</code><span>current state matched recorded post-run state</span></p>
              <p><b>removed</b><code>pyproject.toml</code><span>current state matched recorded post-run state</span></p>
              <p><b class="is-kept">kept</b><code>src/parser.py</code><span>allowed work preserved</span></p>
            </div>
          </section>
        </div>
      </div>
    </section>

    <section class="ad-score-story ad-section" aria-labelledby="ad-score-title">
      <div class="ad-section-label ad-section-label--light"><span>03</span> Explainable blast radius</div>
      <div class="ad-score-story__layout">
        <div>
          <h2 id="ad-score-title">A score you can<br><em>actually interrogate.</em></h2>
          <p>AgentDiff adds deterministic weights for evidence it observed. The total is capped at 100, but the raw components remain visible—so a number never replaces the evidence.</p>
          <a href="docs/concepts/blast-radius/">Read the scoring model <span aria-hidden="true">→</span></a>
        </div>
        <div class="ad-equation" aria-label="Example blast-radius calculation">
          <span>denied mutation</span><strong>45</strong>
          <span>dependency file</span><strong>35</strong>
          <span>created resources</span><strong>01</strong>
          <hr>
          <span>blast radius</span><strong class="is-total">81</strong>
          <small>CRITICAL · EVERY POINT ACCOUNTED FOR</small>
        </div>
      </div>
    </section>

    <section class="ad-recovery ad-section" id="recovery" aria-labelledby="ad-recovery-title">
      <div class="ad-section-label"><span>04</span> Selective recovery</div>
      <div class="ad-recovery__heading">
        <h2 id="ad-recovery-title">Keep the fix.<br><em>Remove the collateral.</em></h2>
        <p>Safe rollback targets only review and deny mutations, and only when the current path still matches the exact post-run state. Later human edits become conflicts and are preserved.</p>
      </div>
      <div class="ad-recovery__flow" aria-label="Selective recovery flow">
        <article>
          <span>01 · RECORD</span>
          <strong>Before + after state</strong>
          <p>Capture recoverable evidence before the command starts.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article>
          <span>02 · COMPARE</span>
          <strong>Current = recorded after?</strong>
          <p>Refuse recovery if a person or later process changed the path.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article>
          <span>03 · RECOVER</span>
          <strong>2 removed · 1 kept</strong>
          <p>Undo collateral while preserving the allowed parser fix.</p>
        </article>
      </div>
      <div class="ad-recovery__command"><code>$ agentdiff rollback &lt;run-id&gt; --safe-only</code><span>Actions: 2 · Conflicts: 0 · Skipped: 1</span></div>
    </section>

    <section class="ad-fit ad-section" aria-labelledby="ad-fit-title">
      <div class="ad-section-label"><span>05</span> Fits the stack you already have</div>
      <div class="ad-fit__heading">
        <h2 id="ad-fit-title">Not another agent framework.<br><em>Not a pretend sandbox.</em></h2>
        <p>AgentDiff is the evidence and recovery layer beside your tests, Git history, tracing, and real isolation boundary.</p>
      </div>
      <div class="ad-fit__table">
        <div class="ad-fit__head"><span>Layer</span><span>What it answers</span><span>How AgentDiff fits</span></div>
        <div><b>Tests</b><span>Did expected behavior pass?</span><em>Adds workspace side-effect evidence.</em></div>
        <div><b>Git</b><span>What tracked text changed?</span><em>Adds untracked files, process and port observations.</em></div>
        <div><b>Tracing</b><span>What did the model and tools do?</span><em>Adds deterministic runtime state.</em></div>
        <div><b>Sandboxes</b><span>What is isolated or blocked?</span><em>Records evidence inside or outside the boundary.</em></div>
      </div>
    </section>
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
# Inspect the run capsule
agentdiff inspect <run-id>
    <section class="ad-trust ad-section" id="trust" aria-labelledby="ad-trust-title">
      <div class="ad-trust__mark" aria-hidden="true">[ ! ]</div>
      <div>
        <div class="ad-section-label ad-section-label--light"><span>06</span> Honest capability boundaries</div>
        <h2 id="ad-trust-title">Evidence, not<br>security theater.</h2>
      </div>
      <div class="ad-trust__content">
        <p>The local runtime observes a subprocess. It does not become a kernel isolation boundary just because an AI agent launched it.</p>
        <ul>
          <li><span>Does</span> capture no-follow filesystem state and versioned evidence</li>
          <li><span>Does</span> enforce command policy before local process launch</li>
          <li><span>Does not</span> block network access in local observation mode</li>
          <li><span>Does not</span> claim causal ownership of machine-wide port changes</li>
        </ul>
        <a href="https://github.com/kam6l/agentdiff/blob/main/SECURITY.md">Read the full trust model <span aria-hidden="true">↗</span></a>
      </div>
    </section>

    <section class="ad-final-cta">
      <div class="ad-final-cta__noise" aria-hidden="true"></div>
      <p>Wrap the command you already run.</p>
      <h2>Make every agent run<br><em>accountable.</em></h2>
      <div>
        <a class="ad-button ad-button--light" href="docs/quickstart/">Start with the quickstart <span aria-hidden="true">→</span></a>
        <a class="ad-button ad-button--ghost" href="docs/">Explore the docs</a>
      </div>
    </section>
  </main>

  <footer class="ad-site-footer">
    <div class="ad-site-footer__brand">
      <a class="ad-wordmark" href="./" aria-label="AgentDiff home">
        <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M10 5H5v22h5M22 5h5v22h-5" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><path d="M13 12h6M13 20h6" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>
        <span>AgentDiff</span>
      </a>
      <p>Local-first runtime evidence for autonomous agents.</p>
    </div>
    <div><b>Learn</b><a href="docs/">Documentation</a><a href="docs/quickstart/">Quickstart</a><a href="docs/cli/">CLI</a></div>
    <div><b>Project</b><a href="https://github.com/kam6l/agentdiff">GitHub</a><a href="https://github.com/kam6l/agentdiff/issues">Issues</a><a href="https://github.com/kam6l/agentdiff/blob/main/CONTRIBUTING.md">Contributing</a></div>
    <div><b>Trust</b><a href="https://github.com/kam6l/agentdiff/blob/main/SECURITY.md">Security</a><a href="docs/concepts/runtime/">Runtime model</a><a href="docs/concepts/recovery/">Recovery</a></div>
    <small>MIT licensed · AgentDiff contributors · 2026</small>
  </footer>
</div>
- **[Quickstart](docs/quickstart.md)** — Run your first observed transaction in 2 minutes
- **[Installation](docs/installation.md)** — Binary install, from source, or Docker
- **[Concepts](docs/concepts/runtime.md)** — Deep dive into the runtime model
- **[CLI Reference](docs/cli.md)** — Complete command documentation
