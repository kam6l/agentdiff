---
title: The trust layer for autonomous software changes
hide:
  - navigation
  - toc
  - footer
description: AI writes code. AgentDiff decides if autonomous changes are safe to ship — with blast radius analysis, clean-room proof, and verified PRs.
search:
  exclude: true
---

<div class="ad-home" data-agentdiff-home>
  <a class="ad-skip" href="#main-content">Skip to content</a>

  <header class="ad-site-header" data-site-header>
    <nav class="ad-site-nav" aria-label="Main navigation">
      <a class="ad-wordmark" href="./" aria-label="AgentDiff home">
        <img src="assets/images/favicon.svg" alt="AgentDiff logo" class="ad-wordmark__logo" width="28" height="28">
        <span>AgentDiff</span>
      </a>

      <button class="ad-menu-button" type="button" aria-expanded="false" aria-controls="ad-nav-links" data-menu-toggle>
        <span></span><span></span>
        <span class="ad-visually-hidden">Toggle navigation</span>
      </button>

      <div class="ad-site-nav__links" id="ad-nav-links" data-menu>
        <a href="#how-it-works">How it works</a>
        <a href="#compare">Compare</a>
        <a href="#roadmap">Roadmap</a>
        <a href="docs/">Docs</a>
        <a class="ad-nav-cta" href="https://github.com/kam6l/agentdiff" target="_blank" rel="noopener noreferrer">GitHub <span aria-hidden="true">↗</span></a>
      </div>
    </nav>
  </header>

  <main id="main-content">

    <!-- ═══════════════════════════════════════════════════════════════
         HERO
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-hero" aria-labelledby="ad-hero-title">
      <div class="ad-hero__texture" aria-hidden="true"></div>
      <div class="ad-hero__copy">
        <p class="ad-pill"><span></span> Open source · beta · local-first</p>
        <h1 id="ad-hero-title">AI writes the code.<br><em>AgentDiff decides if it ships.</em></h1>
        <p class="ad-hero__lede">When APIs break, dependencies change, or agents rewrite your code — AgentDiff detects what's affected, verifies the fix is safe, and delivers a trusted PR with proof. The deterministic trust layer for autonomous software changes.</p>
        <div class="ad-hero__actions">
          <a class="ad-button ad-button--light" href="#demo">See how it works <span aria-hidden="true">↓</span></a>
          <a class="ad-button ad-button--ghost" href="https://github.com/kam6l/agentdiff" target="_blank" rel="noopener noreferrer">View on GitHub <span aria-hidden="true">↗</span></a>
        </div>
        <div class="ad-command" aria-label="Install AgentDiff from source">
          <span class="ad-command__prompt" aria-hidden="true">$</span>
          <code id="ad-install-command">git clone https://github.com/kam6l/agentdiff.git &amp;&amp; cd agentdiff &amp;&amp; uv tool install .</code>
          <button type="button" data-copy-target="ad-install-command"><span data-copy-label>Copy</span></button>
        </div>
        <p class="ad-hero__note">Observation by default. External enforcement only through a separately configured runtime.</p>
      </div>

      <div class="ad-hero__pitch" aria-label="How AgentDiff works">
        <div class="ad-hero__pitch-card">
          <div class="ad-hero__pitch-header">
            <span>THE PROBLEM</span>
          </div>
          <div class="ad-hero__pitch-body">
            <p class="ad-hero__pitch-big">AI agents can generate code.</p>
            <p class="ad-hero__pitch-sub">But who verifies the changes are safe?<br>Who checks what else was affected?<br>Who proves the fix actually works?</p>
          </div>
          <div class="ad-hero__pitch-header">
            <span>AGENTDIFF</span>
          </div>
          <div class="ad-hero__pitch-body ad-hero__pitch-body--answer">
            <p class="ad-hero__pitch-answer">Detects affected code. Scores blast radius. Verifies in a clean room. Delivers a PR with proof.</p>
          </div>
        </div>
      </div>
    </section>

    <section class="ad-proof-strip" aria-label="Core capabilities" tabindex="0">
      <span>AST-based API scanning</span>
      <span>Deterministic policy</span>
      <span>0–100 blast radius</span>
      <span>Clean-room proof</span>
      <span>Verified PRs</span>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         DEMO — 30-second product pipeline
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-pipeline-section ad-section" id="demo" aria-labelledby="ad-demo-title">
      <div class="ad-section-label"><span>◆</span> Product demo</div>
      <h2 id="ad-demo-title">From API change<br><em>to trusted PR.</em></h2>
      <p class="ad-pipeline-lede">A 30-second walkthrough of what AgentDiff does when an upstream API ships a breaking change.</p>

      <div class="ad-pipeline" aria-label="AgentDiff pipeline steps">
        <article class="ad-pipeline__step">
          <span>01</span>
          <strong>API change detected</strong>
          <div class="ad-pipeline__code"><code>openai>=1.0: ChatCompletion → client.chat.completions</code></div>
          <p>Provider ships a breaking SDK change. AgentDiff matches it against known catalogs.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article class="ad-pipeline__step">
          <span>02</span>
          <strong>Affected code found</strong>
          <div class="ad-pipeline__code"><code>src/llm.py:42 src/agent.py:118 tests/test_llm.py:7</code></div>
          <p>AST scanner finds every usage. Provenance-tracked, no false positives.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article class="ad-pipeline__step">
          <span>03</span>
          <strong>Blast radius scored</strong>
          <div class="ad-pipeline__score"><strong>72</strong><small>/100 · HIGH</small></div>
          <p>Deterministic 0–100 score. Every point accounted for. Policy decides: allow, review, or deny.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article class="ad-pipeline__step">
          <span>04</span>
          <strong>Migration generated</strong>
          <div class="ad-pipeline__code"><code>AST transform: 3 files · agent fallback: 0</code></div>
          <p>Known migrations use deterministic AST transforms. Complex ones use an agent — untrusted until proven.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article class="ad-pipeline__step">
          <span>05</span>
          <strong>Verified in clean room</strong>
          <div class="ad-pipeline__code"><code>syntax ✓ types ✓ targeted ✓ full ✓</code></div>
          <p>Patch replayed in isolated worktree. Syntax, types, targeted tests, full repo tests. All evidence recorded.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article class="ad-pipeline__step ad-pipeline__step--final">
          <span>06</span>
          <strong>Trusted PR delivered</strong>
          <div class="ad-pipeline__verdict"><b>VERIFIED</b></div>
          <p>Migration Certificate with blast radius, test results, proof digest, and rollback info. Conflict-safe promotion.</p>
        </article>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         HOW IT WORKS — 5 sections
         ═══════════════════════════════════════════════════════════════ -->

    <section class="ad-section ad-detect" id="how-it-works" aria-labelledby="ad-detect-title">
      <div class="ad-section-label"><span>01</span> Detect</div>
      <div class="ad-problem__heading">
        <h2 id="ad-detect-title">An API changed.<br><em>Who's affected?</em></h2>
        <p>AgentDiff scans your Python AST to find every third-party API usage — OpenAI, Stripe, and more. Not grep. Provenance-tracked, SDK-version-aware, zero false positives.</p>
      </div>
      <div class="ad-detect__demo">
        <div class="ad-story-card ad-story-card--dark">
          <div class="ad-story-card__meta"><span>BEFORE</span><span>openai 0.28</span></div>
          <div class="ad-terminal-fragment ad-terminal-fragment--dark">
            <code>response = openai.ChatCompletion.create(</code><br>
            <code>    model="gpt-4",</code><br>
            <code>    messages=[{"role": "user", "content": prompt}]</code><br>
            <code>)</code>
          </div>
          <footer>Old SDK pattern — found across 3 files, 7 call sites.</footer>
        </div>
        <div class="ad-story-card ad-story-card--dark">
          <div class="ad-story-card__meta"><span>DETECTED CHANGE</span><span>openai 1.0+</span></div>
          <div class="ad-terminal-fragment ad-terminal-fragment--dark">
            <code><span class="is-red">- openai.ChatCompletion.create(</span></code><br>
            <code><span class="is-green">+ client.chat.completions.create(</span></code><br>
            <code>      model="gpt-4",</code><br>
            <code>      messages=[...]</code><br>
            <code>  )</code>
          </div>
          <footer>Matched against known breaking-change catalog.</footer>
        </div>
      </div>
      <div class="ad-detect__command">
        <code>$ agentdiff api scan --root . && agentdiff api check --root . --fail-on high</code>
      </div>
    </section>

    <section class="ad-score-story ad-section" id="understand" aria-labelledby="ad-score-title">
      <div class="ad-section-label ad-section-label--light"><span>02</span> Understand impact</div>
      <div class="ad-score-story__layout">
        <div>
          <h2 id="ad-score-title">Blast radius,<br><em>not guesswork.</em></h2>
          <p>AgentDiff adds deterministic weights for every observed mutation. The total is capped at 100, but the raw components remain visible — so a number never replaces the evidence. Every change gets an allow, review, or deny decision with the matching rule.</p>
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

    <section class="ad-section ad-generate" aria-labelledby="ad-generate-title">
      <div class="ad-section-label"><span>03</span> Generate changes</div>
      <div class="ad-problem__heading">
        <h2 id="ad-generate-title">Deterministic transforms.<br><em>Agent fallback.</em></h2>
        <p>Known migrations — like OpenAI's Responses API or Stripe's PaymentIntents — use deterministic AST transforms. No model involved, no hallucination possible. Complex migrations fall back to a coding agent. Either way: <strong>the patch is untrusted until AgentDiff proves it.</strong></p>
      </div>
      <div class="ad-generate__grid">
        <article>
          <span>DETERMINISTIC</span>
          <strong>AST transforms</strong>
          <p>Registry-extensible by providers. Known input → known output. Provenance-tracked.</p>
        </article>
        <article>
          <span>PROBABILISTIC</span>
          <strong>Coding agent</strong>
          <p>For complex migrations. Output is captured but <em>never trusted</em> until clean-room verification passes.</p>
        </article>
        <article>
          <span>ALWAYS</span>
          <strong>Untrusted until proven</strong>
          <p>Both paths produce patches. AgentDiff's verification engine decides if the result is safe to ship.</p>
        </article>
      </div>
    </section>

    <section class="ad-section ad-verify" aria-labelledby="ad-verify-title">
      <div class="ad-section-label"><span>04</span> Verify safely</div>
      <div class="ad-problem__heading">
        <h2 id="ad-verify-title">Clean-room proof.<br><em>No shortcuts.</em></h2>
        <p>Every patch is replayed in an isolated worktree — completely independent of the agent that generated it. Syntax checks, type checks, targeted tests, full repo tests. If it fails, the automatic repair loop retries within scope. All evidence is recorded in a durable capsule.</p>
      </div>
      <div class="ad-verify__flow" aria-label="Verification flow">
        <article>
          <span>V0 · SYNTAX</span>
          <strong>Parses correctly</strong>
          <p>Basic AST validity check.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article>
          <span>V1 · TYPES</span>
          <strong>Type checks pass</strong>
          <p>Static analysis in the clean workspace.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article>
          <span>V2 · TARGETED</span>
          <strong>Affected tests pass</strong>
          <p>Only tests touched by the change.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article>
          <span>V3 · FULL</span>
          <strong>All tests pass</strong>
          <p>Complete test suite in clean room.</p>
        </article>
      </div>
      <div class="ad-recovery__command"><code>$ agentdiff prove &lt;run-id&gt; && agentdiff promote &lt;run-id&gt;</code><span>Clean-room proof → conflict-safe promotion</span></div>
    </section>

    <section class="ad-section ad-deliver" aria-labelledby="ad-deliver-title">
      <div class="ad-section-label"><span>05</span> Deliver PR</div>
      <div class="ad-problem__heading">
        <h2 id="ad-deliver-title">One PR.<br><em>Full evidence.</em></h2>
        <p>The verified patch is promoted to a pull request with a machine-readable Migration Certificate: which provider change triggered it, which files were affected, the blast radius score, every test that was executed, the proof digest, and rollback instructions. Conflict-safe — later human edits are preserved.</p>
      </div>
      <div class="ad-deliver__cert">
        <div class="ad-deliver__cert-header">
          <div class="ad-window-dots" aria-hidden="true"><i></i><i></i><i></i></div>
          <code>Migration Certificate · openai 0.28 → 1.0</code>
        </div>
        <div class="ad-deliver__cert-body">
          <div><span>Provider change</span><strong>openai SDK 0.28 → 1.0 (ChatCompletion removal)</strong></div>
          <div><span>Affected files</span><strong>3 files · 7 call sites</strong></div>
          <div><span>Migration method</span><strong>AST transform (deterministic)</strong></div>
          <div><span>Blast radius</span><strong>72/100 · HIGH</strong></div>
          <div><span>Verification</span><strong>V3 — full test suite passed</strong></div>
          <div><span>Proof digest</span><strong><code>sha256:e45c0d69...</code></strong></div>
          <div><span>Rollback</span><strong>agentdiff rollback &lt;id&gt; --safe-only</strong></div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         DIFFERENTIATION
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-compare ad-section" id="compare" aria-labelledby="ad-compare-title">
      <div class="ad-section-label"><span>◆</span> Not another coding agent</div>
      <div class="ad-fit__heading">
        <h2 id="ad-compare-title">AgentDiff is<br><em>the missing layer.</em></h2>
        <p>Coding agents generate. Dependabot bumps versions. Neither verifies that the change is safe, scores its blast radius, or delivers proof. AgentDiff is the trust layer that sits between generation and delivery.</p>
      </div>
      <div class="ad-fit__table ad-compare__table">
        <div class="ad-fit__head"><span>Capability</span><span>Copilot / Cursor</span><span>Dependabot</span><span>AgentDiff</span></div>
        <div><b>Blast radius analysis</b><span>—</span><span>—</span><em>0–100 deterministic score</em></div>
        <div><b>Policy enforcement</b><span>—</span><span>Auto-merge rules</span><em>allow / review / deny per path</em></div>
        <div><b>Proof & evidence</b><span>—</span><span>CI pass/fail</span><em>Clean-room replay + capsule</em></div>
        <div><b>Selective rollback</b><span>Undo all</span><span>Revert PR</span><em>Conflict-safe per-file recovery</em></div>
        <div><b>Independent verification</b><span>—</span><span>—</span><em>Isolated worktree, not agent self-report</em></div>
        <div><b>Migration certificates</b><span>—</span><span>—</span><em>Machine-readable audit trail</em></div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         UNDER THE HOOD — deep technical details
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-cortex ad-section" id="engine" aria-labelledby="ad-engine-title">
      <div class="ad-section-label"><span>◆</span> Under the hood</div>
      <div class="ad-cortex__heading">
        <h2 id="ad-engine-title">Trust engine<br><em>internals.</em></h2>
        <p>The infrastructure that makes verified autonomous changes possible. Independent real-state observation, deterministic policy, conflict-safe promotion, and bounded repair — all working together.</p>
      </div>
      <div class="ad-cortex__providers">
        <article>
          <span>PROOF</span>
          <strong>Clean-room replay</strong>
          <p>Every patch is replayed in a fresh worktree, completely independent of the agent. Syntax, types, and tests are verified from scratch.</p>
        </article>
        <article>
          <span>EVIDENCE</span>
          <strong>Durable capsules</strong>
          <p>Before/after filesystem manifests, SHA-256 checksums, policy provenance, score components, and process identity — all in a versioned local capsule.</p>
        </article>
        <article>
          <span>RECOVERY</span>
          <strong>Selective rollback</strong>
          <p>Undo only review and deny mutations. Only when current state matches exact post-run state. Human edits become conflicts and are preserved.</p>
        </article>
      </div>
      <div class="ad-underhood__row">
        <article>
          <span>REPAIR LOOP</span>
          <strong>Bounded retry</strong>
          <p>When proof fails, the automatic repair loop retries — but only while the repair stays within the original scope. No unbounded agent loops.</p>
        </article>
        <article>
          <span>POLICY ENGINE</span>
          <strong>Deterministic rules</strong>
          <p>Versioned allow/review/deny rules with provenance. Every decision includes the matching rule and is auditable. No probabilistic access control.</p>
        </article>
        <article>
          <span>WARM WORKSPACES</span>
          <strong>Fast isolation</strong>
          <p>Pre-built workspace snapshots for rapid clean-room verification. No cold-start penalty for proof runs.</p>
        </article>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         TRUST MODEL
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-trust ad-section" id="trust" aria-labelledby="ad-trust-title">
      <div class="ad-trust__mark" aria-hidden="true">[ ! ]</div>
      <div>
        <div class="ad-section-label ad-section-label--light"><span>◆</span> Honest capability boundaries</div>
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
        <a href="https://github.com/kam6l/agentdiff/blob/main/SECURITY.md" target="_blank" rel="noopener noreferrer">Read the full trust model <span aria-hidden="true">↗</span></a>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         CURRENT CAPABILITIES & ROADMAP
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-status ad-section" id="roadmap" aria-labelledby="ad-status-title">
      <div class="ad-section-label"><span>◆</span> Honest status</div>
      <div class="ad-fit__heading">
        <h2 id="ad-status-title">What works today.<br><em>What's next.</em></h2>
        <p>AgentDiff is beta software. Here's an honest look at current capabilities and the focused roadmap.</p>
      </div>
      <div class="ad-status__grid">
        <div class="ad-status__column">
          <div class="ad-status__header"><span></span> Current capabilities</div>
          <ul class="ad-status__list">
            <li><strong>API scanning</strong> AST-based detection for OpenAI and Stripe</li>
            <li><strong>Dependency analysis</strong> SDK version detection and breaking-change matching</li>
            <li><strong>Impact analysis</strong> Deterministic blast radius scoring (0–100)</li>
            <li><strong>Policy engine</strong> Versioned allow / review / deny rules</li>
            <li><strong>Verification engine</strong> Clean-room proof and replay</li>
            <li><strong>Evidence capsules</strong> Durable manifests with SHA-256 checksums</li>
            <li><strong>Selective recovery</strong> Conflict-safe per-file rollback</li>
            <li><strong>Zero-touch automation</strong> <code>agentdiff wrap -- &lt;agent&gt;</code></li>
          </ul>
        </div>
        <div class="ad-status__column ad-status__column--future">
          <div class="ad-status__header ad-status__header--future"><span></span> Roadmap</div>
          <ul class="ad-status__list">
            <li><strong>Automatic AST migrations</strong> Deterministic transforms for known provider changes</li>
            <li><strong>Verified PRs</strong> GitHub PR delivery with Migration Certificates</li>
            <li><strong>API Change Manifests</strong> Machine-readable upstream change format</li>
            <li><strong>Verification levels V0–V5</strong> Graduated proof from syntax to integration</li>
            <li><strong>More providers</strong> Beyond OpenAI and Stripe</li>
            <li><strong>PyPI & signed releases</strong> Published packages with provenance</li>
            <li><strong>Signed evidence export</strong> Shareable authenticated capsules</li>
          </ul>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         FINAL CTA
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-final-cta">
      <div class="ad-final-cta__noise" aria-hidden="true"></div>
      <p>The coding agent is probabilistic. The verifier is deterministic.</p>
      <h2>AI generates.<br><em>AgentDiff verifies.</em></h2>
      <div>
        <a class="ad-button ad-button--light" href="docs/quickstart/">Start with the quickstart <span aria-hidden="true">→</span></a>
        <a class="ad-button ad-button--ghost" href="docs/">Explore the docs</a>
      </div>
    </section>
  </main>

  <footer class="ad-site-footer">
    <div class="ad-site-footer__brand">
      <a class="ad-wordmark" href="./" aria-label="AgentDiff home">
        <img src="assets/images/favicon.svg" alt="AgentDiff logo" class="ad-wordmark__logo" width="28" height="28">
        <span>AgentDiff</span>
      </a>
      <p>The trust layer for autonomous software changes.</p>
    </div>
    <div><b>Learn</b><a href="docs/">Documentation</a><a href="docs/quickstart/">Quickstart</a><a href="docs/cli/">CLI</a></div>
    <div><b>Project</b><a href="https://github.com/kam6l/agentdiff" target="_blank" rel="noopener noreferrer">GitHub</a><a href="https://github.com/kam6l/agentdiff/issues" target="_blank" rel="noopener noreferrer">Issues</a><a href="https://github.com/kam6l/agentdiff/blob/main/CONTRIBUTING.md" target="_blank" rel="noopener noreferrer">Contributing</a></div>
    <div><b>Trust</b><a href="https://github.com/kam6l/agentdiff/blob/main/SECURITY.md" target="_blank" rel="noopener noreferrer">Security</a><a href="docs/concepts/runtime/">Runtime model</a><a href="docs/concepts/recovery/">Recovery</a></div>
    <small>MIT licensed · AgentDiff contributors · 2026</small>
  </footer>
</div>
