---
hide:
  - navigation
  - toc
  - footer
---

<div class="ad-home" data-agentdiff-home>
  <a class="ad-skip" href="#main-content">Skip to content</a>

  <nav class="ad-nav" aria-label="Primary navigation">
    <a class="ad-brand" href="./" aria-label="AgentDiff home">
      <svg class="ad-brand__mark" viewBox="0 0 40 40" aria-hidden="true">
        <path d="M7 7h15v6h-9v14h9v6H7V7Z"></path>
        <path d="M33 7v26H18v-6h9V13h-9V7h15Z"></path>
      </svg>
      <span>AgentDiff</span>
    </a>
    <div class="ad-nav__links">
      <a href="#how-it-works">How it works</a>
      <a href="quickstart/">Docs</a>
      <a href="cli/">CLI</a>
      <a class="ad-nav__github" href="https://github.com/kam6l/agentdiff" target="_blank" rel="noopener">
        GitHub
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5.2 3.5h7.3v7.3h-1.4V5.9l-7.6 7.6-1-1 7.6-7.6H5.2V3.5Z"></path></svg>
      </a>
    </div>
  </nav>

  <main id="main-content">
    <section class="ad-hero" aria-labelledby="hero-title">
      <div class="ad-hero__copy ad-reveal">
        <p class="ad-eyebrow"><span></span> Open source · Alpha · Python 3.10+</p>
        <h1 id="hero-title">The agent passed.<br><em>The environment disagrees.</em></h1>
        <p class="ad-hero__lede">AgentDiff evaluates what an AI agent changed—not just what it returned. Capture the before and after state, inspect the trajectory, and measure the collateral damage.</p>
        <div class="ad-actions">
          <a class="ad-button ad-button--primary" href="quickstart/">Read the quickstart <span aria-hidden="true">→</span></a>
          <a class="ad-button ad-button--secondary" href="https://github.com/kam6l/agentdiff" target="_blank" rel="noopener">View source</a>
        </div>
        <div class="ad-install" aria-label="Install from source">
          <span class="ad-install__prompt" aria-hidden="true">$</span>
          <code id="install-command">git clone https://github.com/kam6l/agentdiff.git</code>
          <button class="ad-copy" type="button" data-copy-target="install-command" aria-label="Copy install command">
            <span class="ad-copy__label">Copy</span>
          </button>
        </div>
      </div>

      <div class="ad-demo-wrap ad-reveal" style="--reveal-delay: 120ms">
        <div class="ad-demo-label"><span>Interactive example</span><span>Run #AD-042</span></div>
        <article class="ad-demo" aria-label="Example AgentDiff evaluation">
          <header class="ad-demo__header">
            <div class="ad-window-dots" aria-hidden="true"><i></i><i></i><i></i></div>
            <code>agentdiff eval</code>
            <span class="ad-demo__live"><i></i> captured</span>
          </header>
          <div class="ad-demo__task">
            <div>
              <span class="ad-micro">Task</span>
              <strong>Fix the calculator bug</strong>
            </div>
            <div class="ad-demo__switch" role="group" aria-label="Example run state">
              <button type="button" data-demo-state="clean" aria-pressed="false">Clean run</button>
              <button class="is-active" type="button" data-demo-state="messy" aria-pressed="true">Actual run</button>
            </div>
          </div>
          <div class="ad-demo__score-row">
            <div class="ad-score" aria-live="polite">
              <span class="ad-score__value" data-demo-score>33</span><span class="ad-score__unit">%</span>
            </div>
            <div class="ad-score__context">
              <span class="ad-micro">Cleanliness score</span>
              <strong data-demo-summary>1 intended / 3 total mutations</strong>
              <div class="ad-meter"><span data-demo-meter style="width:33%"></span></div>
            </div>
          </div>
          <div class="ad-demo__mutations" data-demo-mutations aria-live="polite">
            <div class="ad-mutation is-target">
              <span class="ad-mutation__type">M</span>
              <code>src/calculator.py</code>
              <span>intended</span>
            </div>
            <div class="ad-mutation is-warning">
              <span class="ad-mutation__type">M</span>
              <code>config.json</code>
              <span>outside scope</span>
            </div>
            <div class="ad-mutation is-warning">
              <span class="ad-mutation__type">+</span>
              <code>debug.log</code>
              <span>unexpected</span>
            </div>
          </div>
          <footer class="ad-demo__footer">
            <span><i class="ad-verdict-dot"></i> Verdict</span>
            <strong data-demo-verdict>FAIL · threshold 80%</strong>
          </footer>
        </article>
        <p class="ad-demo-note">A task-level pass can still hide a system-level failure.</p>
      </div>
    </section>

    <section class="ad-proof" aria-labelledby="proof-title">
      <div class="ad-section-heading ad-reveal">
        <p class="ad-kicker">01 / The missing test layer</p>
        <h2 id="proof-title">Tests inspect the answer.<br>AgentDiff inspects the aftermath.</h2>
      </div>
      <div class="ad-compare ad-reveal">
        <article class="ad-compare__panel ad-compare__panel--plain">
          <header><span>Output evaluation</span><span class="ad-status ad-status--pass">PASS</span></header>
          <div class="ad-compare__body">
            <p class="ad-micro">Agent response</p>
            <blockquote>“Fixed the calculator and all tests pass.”</blockquote>
            <div class="ad-test-line"><span>✓</span><code>18 passed in 0.42s</code></div>
          </div>
          <footer>Correct answer. No visibility into side effects.</footer>
        </article>
        <div class="ad-compare__arrow" aria-hidden="true">+</div>
        <article class="ad-compare__panel ad-compare__panel--signal">
          <header><span>State evaluation</span><span class="ad-status ad-status--fail">FAIL</span></header>
          <div class="ad-compare__body">
            <p class="ad-micro">Observed aftermath</p>
            <ul>
              <li><span class="is-good">01</span> intended file changed</li>
              <li><span class="is-bad">02</span> unintended files changed</li>
              <li><span class="is-bad">01</span> listening port opened</li>
            </ul>
          </div>
          <footer>Correct answer. Unclean execution.</footer>
        </article>
      </div>
    </section>

    <section class="ad-inspect" id="how-it-works" aria-labelledby="inspect-title">
      <div class="ad-section-heading ad-section-heading--split ad-reveal">
        <div>
          <p class="ad-kicker">02 / Full-state diff</p>
          <h2 id="inspect-title">Watch the blast radius.</h2>
        </div>
        <p>AgentDiff takes state snapshots around an agent run and turns every observed change into a reviewable diff.</p>
      </div>

      <div class="ad-inspector ad-reveal">
        <div class="ad-inspector__tabs" role="tablist" aria-label="Captured state layers">
          <button class="is-active" id="tab-filesystem" role="tab" aria-selected="true" aria-controls="panel-filesystem" data-inspector-tab="filesystem">
            <span>01</span><strong>Filesystem</strong><small>create · modify · delete</small>
          </button>
          <button id="tab-environment" role="tab" aria-selected="false" aria-controls="panel-environment" data-inspector-tab="environment">
            <span>02</span><strong>Environment</strong><small>added · changed · removed</small>
          </button>
          <button id="tab-processes" role="tab" aria-selected="false" aria-controls="panel-processes" data-inspector-tab="processes">
            <span>03</span><strong>Processes</strong><small>spawned · terminated</small>
          </button>
          <button id="tab-network" role="tab" aria-selected="false" aria-controls="panel-network" data-inspector-tab="network">
            <span>04</span><strong>Network</strong><small>ports opened · closed</small>
          </button>
          <button id="tab-trajectory" role="tab" aria-selected="false" aria-controls="panel-trajectory" data-inspector-tab="trajectory">
            <span>05</span><strong>Trajectory</strong><small>steps · tools · loops</small>
          </button>
        </div>
        <div class="ad-inspector__stage">
          <header>
            <span class="ad-micro">Observed mutations</span>
            <span class="ad-inspector__count" data-inspector-count>3 changes</span>
          </header>
          <div class="ad-inspector__panel" id="panel-filesystem" role="tabpanel" aria-labelledby="tab-filesystem" data-inspector-panel="filesystem">
            <div class="ad-table-head"><span>Change</span><span>Resource</span><span>Classification</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--modify">M</span><code>src/calculator.py</code><span class="ad-class ad-class--target">target</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--modify">M</span><code>config.json</code><span class="ad-class ad-class--warning">warning</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--create">+</span><code>debug.log</code><span class="ad-class ad-class--warning">warning</span></div>
          </div>
          <div class="ad-inspector__panel" id="panel-environment" role="tabpanel" aria-labelledby="tab-environment" data-inspector-panel="environment" hidden>
            <div class="ad-table-head"><span>Change</span><span>Variable</span><span>Classification</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--create">+</span><code>DEBUG_MODE</code><span class="ad-class ad-class--warning">warning</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--modify">M</span><code>APP_ENV</code><span class="ad-class ad-class--warning">warning</span></div>
            <p class="ad-inspector__privacy">Secret-like keys are excluded from snapshots by default.</p>
          </div>
          <div class="ad-inspector__panel" id="panel-processes" role="tabpanel" aria-labelledby="tab-processes" data-inspector-panel="processes" hidden>
            <div class="ad-table-head"><span>Change</span><span>Process</span><span>Classification</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--create">+</span><code>PID 4821</code><span class="ad-class ad-class--warning">spawned</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--delete">−</span><code>PID 4768</code><span class="ad-class ad-class--danger">terminated</span></div>
          </div>
          <div class="ad-inspector__panel" id="panel-network" role="tabpanel" aria-labelledby="tab-network" data-inspector-panel="network" hidden>
            <div class="ad-table-head"><span>Change</span><span>Listening port</span><span>Classification</span></div>
            <div class="ad-table-row"><span class="ad-change ad-change--create">+</span><code>TCP :8080</code><span class="ad-class ad-class--warning">opened</span></div>
          </div>
          <div class="ad-inspector__panel" id="panel-trajectory" role="tabpanel" aria-labelledby="tab-trajectory" data-inspector-panel="trajectory" hidden>
            <div class="ad-table-head"><span>Step</span><span>Tool call</span><span>Result</span></div>
            <div class="ad-table-row"><span class="ad-step-index">01</span><code>read_file</code><span class="ad-class ad-class--target">success</span></div>
            <div class="ad-table-row"><span class="ad-step-index">02</span><code>write_file</code><span class="ad-class ad-class--target">success</span></div>
            <div class="ad-table-row"><span class="ad-step-index">03–05</span><code>run_tests × 3</code><span class="ad-class ad-class--warning">loop</span></div>
          </div>
          <footer>
            <code>sha256: 8f5d...c19a</code>
            <span>snapshot Δ 1.24s</span>
          </footer>
        </div>
      </div>
    </section>

    <section class="ad-metric" aria-labelledby="metric-title">
      <div class="ad-metric__intro ad-reveal">
        <p class="ad-kicker">03 / One useful number</p>
        <h2 id="metric-title">A precision score for agent behavior.</h2>
        <p>Declare what the agent was allowed to change. AgentDiff compares that scope with every observed mutation, then applies your threshold as a repeatable quality gate.</p>
        <a class="ad-text-link" href="concepts/cleanliness/">Understand cleanliness <span aria-hidden="true">→</span></a>
      </div>
      <div class="ad-equation ad-reveal" style="--reveal-delay: 100ms">
        <div class="ad-equation__formula">
          <span>cleanliness</span>
          <strong>=</strong>
          <div><b>intended mutations</b><hr><b>all mutations</b></div>
        </div>
        <div class="ad-equation__example">
          <span class="ad-micro">Example</span>
          <code>1 / 3 = 0.33</code>
          <span class="ad-equation__gate">below 0.80 threshold → fail</span>
        </div>
      </div>
    </section>

    <section class="ad-workflow" aria-labelledby="workflow-title">
      <div class="ad-section-heading ad-section-heading--split ad-reveal">
        <div>
          <p class="ad-kicker">04 / Framework agnostic</p>
          <h2 id="workflow-title">Wrap the run you already have.</h2>
        </div>
        <p>No agent rewrite is required. Snapshot around any Python, shell, LangChain, CrewAI, AutoGen, or custom workflow.</p>
      </div>
      <div class="ad-workflow__body">
        <ol class="ad-steps ad-reveal">
          <li><span>01</span><div><strong>Snapshot before</strong><p>Hash watched files and capture enabled system state.</p></div></li>
          <li><span>02</span><div><strong>Run your agent</strong><p>Record tool calls and steps directly or through an adapter.</p></div></li>
          <li><span>03</span><div><strong>Snapshot after</strong><p>Compute semantic filesystem and environment changes.</p></div></li>
          <li><span>04</span><div><strong>Gate the result</strong><p>Review JSON output or fail below a cleanliness threshold.</p></div></li>
        </ol>
        <div class="ad-code-card ad-reveal" style="--reveal-delay: 100ms">
          <header>
            <span>quickstart.py</span>
            <button type="button" class="ad-copy ad-copy--dark" data-copy-target="python-example"><span class="ad-copy__label">Copy</span></button>
          </header>
          <pre id="python-example"><code><span class="c-purple">from</span> agentdiff <span class="c-purple">import</span> AgentDiffConfig, AgentDiffSession

config = AgentDiffConfig(
    root=<span class="c-string">"workspace"</span>,
    target_paths=[<span class="c-string">"calculator.py"</span>],
)

<span class="c-purple">with</span> AgentDiffSession(<span class="c-string">"Fix calculator"</span>, config) <span class="c-purple">as</span> run:
    run_agent(<span class="c-string">"Fix calculator.py"</span>)
    run.record(
        <span class="c-string">"Applied the fix"</span>,
        <span class="c-string">"edit_file"</span>,
        {<span class="c-string">"path"</span>: <span class="c-string">"calculator.py"</span>},
    )

result = run.evaluate()
result.print_summary()</code></pre>
          <footer><span>JSON serializable</span><span>State snapshots</span><span>CI ready</span></footer>
        </div>
      </div>
    </section>

    <section class="ad-cta ad-reveal" aria-labelledby="cta-title">
      <p class="ad-kicker">Run the demo locally</p>
      <h2 id="cta-title">See what your agent leaves behind.</h2>
      <p>AgentDiff is an early-stage open-source project. Try the scripted demo, inspect the implementation, and help shape the evaluation layer agents are missing.</p>
      <div class="ad-actions ad-actions--center">
        <a class="ad-button ad-button--light" href="quickstart/">Start with the docs <span aria-hidden="true">→</span></a>
        <a class="ad-button ad-button--outline-light" href="https://github.com/kam6l/agentdiff/issues" target="_blank" rel="noopener">Open an issue</a>
      </div>
    </section>
  </main>

  <footer class="ad-footer">
    <a class="ad-brand ad-brand--footer" href="./">
      <svg class="ad-brand__mark" viewBox="0 0 40 40" aria-hidden="true"><path d="M7 7h15v6h-9v14h9v6H7V7Z"></path><path d="M33 7v26H18v-6h9V13h-9V7h15Z"></path></svg>
      <span>AgentDiff</span>
    </a>
    <p>Full-state trajectory evaluation for AI agents.</p>
    <div><a href="quickstart/">Documentation</a><a href="https://github.com/kam6l/agentdiff">GitHub</a><a href="https://github.com/kam6l/agentdiff/blob/main/LICENSE">MIT License</a></div>
    <span>© 2026 AgentDiff contributors</span>
  </footer>
</div>
