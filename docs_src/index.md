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
        <p class="ad-pill"><span></span> Open source · beta · local-first</p>
        <h1 id="ad-hero-title">See what the agent changed.<br><em>Undo only the collateral.</em></h1>
        <p class="ad-hero__lede">AgentDiff wraps any command with secure state capture, deterministic mutation policy, explainable blast-radius scoring, durable evidence, and conflict-safe selective recovery.</p>
        <div class="ad-hero__actions">
          <a class="ad-button ad-button--light" href="docs/quickstart/">Run your first transaction <span aria-hidden="true">→</span></a>
          <a class="ad-button ad-button--ghost" href="https://github.com/kam6l/agentdiff">View source <span aria-hidden="true">↗</span></a>
        </div>
        <div class="ad-command" aria-label="Run AgentDiff">
          <span class="ad-command__prompt" aria-hidden="true">$</span>
          <code id="ad-install-command">agentdiff run --task "Fix authentication" -- codex</code>
          <button type="button" data-copy-target="ad-install-command"><span data-copy-label>Copy</span></button>
        </div>
        <p class="ad-hero__note">Observation by default. External enforcement only through a separately configured runtime.</p>
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
            <code data-run-summary>1 expected · 1 unexpected · 1 protected</code>
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
