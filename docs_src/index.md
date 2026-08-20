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
        <a href="#engine">Under the hood</a>
        <a href="#roadmap">Roadmap</a>
        <a href="docs/">Docs</a>
        <a class="ad-nav-cta" href="https://github.com/kam6l/agentdiff" target="_blank" rel="noopener noreferrer">GitHub <span aria-hidden="true">↗</span></a>
      </div>
    </nav>
  </header>

  <main id="main-content">

    <!-- ═══════════════════════════════════════════════════════════════
         HERO SECTION
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-hero" aria-labelledby="ad-hero-title">
      <div class="ad-hero__texture" aria-hidden="true"></div>
      <div class="ad-hero__copy">
        <p class="ad-pill"><span></span> Open source · beta · local-first</p>
        <h1 id="ad-hero-title">AI writes the code.<br><em>AgentDiff decides if it ships.</em></h1>
        <p class="ad-hero__lede">When APIs break, dependencies change, or agents generate code — AgentDiff detects affected call sites, proves the patch in an isolated clean room, and delivers a verified PR with cryptographic evidence.</p>
        <div class="ad-hero__actions">
          <a class="ad-button ad-button--light" href="#demo">See how it works <span aria-hidden="true">↓</span></a>
          <a class="ad-button ad-button--ghost" href="https://github.com/kam6l/agentdiff" target="_blank" rel="noopener noreferrer">View on GitHub <span aria-hidden="true">↗</span></a>
        </div>
        <div class="ad-command" aria-label="Install AgentDiff from source">
          <span class="ad-command__prompt" aria-hidden="true">$</span>
          <code id="ad-install-command">git clone https://github.com/kam6l/agentdiff.git &amp;&amp; cd agentdiff &amp;&amp; uv tool install .</code>
          <button type="button" data-copy-target="ad-install-command"><span data-copy-label>Copy</span></button>
        </div>
        <p class="ad-hero__note">Deterministic verification · Real-state observation · Zero false claims</p>
      </div>

      <!-- Real Interactive Verification Card -->
      <div class="ad-proof-stage" aria-label="Real AgentDiff transaction example">
        <div class="ad-proof-stage__topline">
          <span>REAL-TIME VERIFICATION</span>
          <span>RUN · E45C0D69</span>
        </div>
        <article class="ad-run-card" data-run-card>
          <header class="ad-run-card__header">
            <div class="ad-window-dots" aria-hidden="true"><i></i><i></i><i></i></div>
            <code>agentdiff / verification capsule</code>
            <span class="ad-runtime-status" data-run-status><i></i> recorded</span>
          </header>

          <div class="ad-run-card__task">
            <div>
              <span class="ad-ui-label">TRIGGER</span>
              <strong>openai 0.28 → 1.0 migration</strong>
            </div>
            <div class="ad-state-switch" role="group" aria-label="Transaction state">
              <button type="button" class="is-active" aria-pressed="true" data-run-state="detected">Detected</button>
              <button type="button" aria-pressed="false" data-run-state="verified">Verified</button>
            </div>
          </div>

          <div class="ad-run-card__body">
            <div class="ad-mutation-table">
              <div class="ad-table-head"><span>CHANGE</span><span>RESOURCE</span><span>POLICY</span></div>
              <div data-run-mutations>
                <div class="ad-mutation-row is-deny"><b>!</b><code>.env</code><span>deny</span></div>
                <div class="ad-mutation-row is-review"><b>!</b><code>pyproject.toml</code><span>review</span></div>
                <div class="ad-mutation-row is-allow"><b>✓</b><code>src/llm.py</code><span>allow</span></div>
              </div>
            </div>
            <div class="ad-score-block">
              <span class="ad-ui-label" data-score-label>BLAST RADIUS</span>
              <div class="ad-score-line"><strong data-run-score>72</strong><span data-score-unit>/100</span></div>
              <div class="ad-score-track"><i data-run-meter style="width:72%; background: var(--ad-orange);"></i></div>
              <b class="ad-verdict" data-run-verdict>HIGH · PR BLOCKED</b>
            </div>
          </div>
          <footer class="ad-run-card__footer">
            <code data-run-summary>3 call sites · 1 unexpected mutation · 1 protected</code>
            <span data-run-action>inspect proof capsule →</span>
          </footer>
        </article>
        <p class="ad-proof-stage__caption">Click "Detected" and "Verified" to switch between initial risk evaluation and clean-room proof.</p>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         TICKER STRIP
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-proof-strip" aria-label="Verified capabilities" tabindex="0">
      <span>AST-based API scanning</span>
      <span>Deterministic policy</span>
      <span>0–100 blast radius</span>
      <span>Clean-room proof</span>
      <span>Conflict-safe recovery</span>
      <span>Migration certificates</span>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         PRODUCT DEMO — Connected Pipeline Flow
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-pipeline-section ad-section" id="demo" aria-labelledby="ad-demo-title">
      <div class="ad-section-label"><span>01</span> 30-Second Product Tour</div>
      <div class="ad-problem__heading">
        <h2 id="ad-demo-title">From API change<br><em>to trusted PR.</em></h2>
        <p>What happens when an upstream dependency introduces a breaking change? AgentDiff automates the entire trust pipeline without human guesswork.</p>
      </div>

      <div class="ad-pipeline-flow" aria-label="AgentDiff 6-step automated pipeline">
        <!-- ROW 1: Detection & Impact -->
        <div class="ad-pipeline-flow__row">
          <article class="ad-pipeline-card">
            <div class="ad-pipeline-card__header">
              <span class="ad-pipeline-card__num">01 · DETECT</span>
              <h3>API change detected</h3>
              <p>Provider deprecation matched against structured change catalogs with SDK version awareness.</p>
            </div>
            <div class="ad-pipeline-card__terminal">
              <span class="ad-pipeline-card__dot is-warn"></span>
              <code>openai 0.28 → 1.0 (ChatCompletion)</code>
            </div>
          </article>

          <i class="ad-pipeline-flow__arrow" aria-hidden="true">→</i>

          <article class="ad-pipeline-card">
            <div class="ad-pipeline-card__header">
              <span class="ad-pipeline-card__num">02 · SCAN</span>
              <h3>Affected code found</h3>
              <p>AST analysis locates every call site in your repository. Provenance-tracked, zero false positives.</p>
            </div>
            <div class="ad-pipeline-card__terminal">
              <span class="ad-pipeline-card__dot"></span>
              <code>src/llm.py:42 · 3 call sites</code>
            </div>
          </article>

          <i class="ad-pipeline-flow__arrow" aria-hidden="true">→</i>

          <article class="ad-pipeline-card">
            <div class="ad-pipeline-card__header">
              <span class="ad-pipeline-card__num">03 · SCORE</span>
              <h3>Blast radius computed</h3>
              <p>Deterministic 0–100 score accounting for affected files, dependency risk, and policy rules.</p>
            </div>
            <div class="ad-pipeline-card__terminal ad-pipeline-card__terminal--score">
              <div class="ad-pipeline-card__score-num"><strong>72</strong><small>/100</small></div>
              <span class="ad-pipeline-card__score-badge">HIGH IMPACT</span>
            </div>
          </article>
        </div>

        <!-- CONNECTOR BETWEEN ROWS -->
        <div class="ad-pipeline-flow__bridge" aria-hidden="true">
          <span>↓</span>
        </div>

        <!-- ROW 2: Generation, Verification & Delivery -->
        <div class="ad-pipeline-flow__row">
          <article class="ad-pipeline-card">
            <div class="ad-pipeline-card__header">
              <span class="ad-pipeline-card__num">04 · GENERATE</span>
              <h3>Migration generated</h3>
              <p>Deterministic AST transforms for known patterns; supervised agent fallback for complex logic.</p>
            </div>
            <div class="ad-pipeline-card__terminal">
              <span class="ad-pipeline-card__dot is-info"></span>
              <code>AST transform: 3 files · 0 hallucinated</code>
            </div>
          </article>

          <i class="ad-pipeline-flow__arrow" aria-hidden="true">→</i>

          <article class="ad-pipeline-card">
            <div class="ad-pipeline-card__header">
              <span class="ad-pipeline-card__num">05 · VERIFY</span>
              <h3>Clean-room proof</h3>
              <p>Patch replayed in an isolated worktree. Syntax, types, targeted tests, and full suite executed.</p>
            </div>
            <div class="ad-pipeline-card__terminal ad-pipeline-card__terminal--success">
              <span class="ad-pipeline-card__dot is-success"></span>
              <code>V0 syntax ✓ · V1 types ✓ · V2 tests ✓</code>
            </div>
          </article>

          <i class="ad-pipeline-flow__arrow" aria-hidden="true">→</i>

          <article class="ad-pipeline-card ad-pipeline-card--final">
            <div class="ad-pipeline-card__header">
              <span class="ad-pipeline-card__num is-verified">06 · DELIVER</span>
              <h3>Trusted PR delivered</h3>
              <p>PR opened with machine-readable Migration Certificate, test results, digest, and rollback instructions.</p>
            </div>
            <div class="ad-pipeline-card__terminal ad-pipeline-card__terminal--verified">
              <b>VERIFIED BY AGENTDIFF</b>
              <code>sha256:e45c0d69...</code>
            </div>
          </article>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         PRODUCT STORY — 5 Core Pillars
         ═══════════════════════════════════════════════════════════════ -->

    <!-- 01 DETECT -->
    <section class="ad-section ad-detect" id="how-it-works" aria-labelledby="ad-detect-title">
      <div class="ad-section-label"><span>02</span> Detect</div>
      <div class="ad-problem__heading">
        <h2 id="ad-detect-title">An API changed.<br><em>Who's affected?</em></h2>
        <p>AgentDiff scans Python AST to pinpoint every third-party API call across your codebase. Not regex or grep. Provenance-tracked, SDK-version aware, zero false positives.</p>
      </div>
      <div class="ad-detect__demo">
        <div class="ad-story-card ad-story-card--dark">
          <div class="ad-story-card__meta"><span>LEGACY CALL SITE</span><span>OPENAI 0.28</span></div>
          <div class="ad-terminal-fragment ad-terminal-fragment--dark">
            <code><span class="is-red"># Deprecated pattern in src/llm.py</span></code><br>
            <code>response = openai.ChatCompletion.create(</code><br>
            <code>    model="gpt-4",</code><br>
            <code>    messages=[{"role": "user", "content": prompt}]</code><br>
            <code>)</code>
          </div>
          <footer>Detected: 3 files · 7 call sites · SDK version &lt; 1.0.0</footer>
        </div>
        <div class="ad-story-card ad-story-card--dark">
          <div class="ad-story-card__meta"><span>AST-TRANSFORMED FIX</span><span>OPENAI 1.0+</span></div>
          <div class="ad-terminal-fragment ad-terminal-fragment--dark">
            <code><span class="is-green"># Verified AST migration</span></code><br>
            <code>client = openai.OpenAI()</code><br>
            <code>response = client.chat.completions.create(</code><br>
            <code>    model="gpt-4",</code><br>
            <code>    messages=[{"role": "user", "content": prompt}]</code><br>
            <code>)</code>
          </div>
          <footer>Deterministic transform matched to breaking catalog</footer>
        </div>
      </div>
      <div class="ad-detect__command">
        <code>$ agentdiff api scan --root . &amp;&amp; agentdiff api check --root . --fail-on high</code>
      </div>
    </section>

    <!-- 02 UNDERSTAND IMPACT -->
    <section class="ad-score-story ad-section" id="understand" aria-labelledby="ad-score-title">
      <div class="ad-section-label ad-section-label--light"><span>03</span> Understand Impact</div>
      <div class="ad-score-story__layout">
        <div>
          <h2 id="ad-score-title">Blast radius,<br><em>not guesswork.</em></h2>
          <p>AgentDiff computes an explainable 0–100 score from real filesystem observations, dependency changes, and policy outcomes. Every point is accounted for—no opaque model confidence scores.</p>
          <a href="docs/concepts/blast-radius/">Explore the blast-radius scoring model <span aria-hidden="true">→</span></a>
        </div>
        <div class="ad-equation" aria-label="Example blast-radius calculation">
          <span>denied mutation (.env)</span><strong>45</strong>
          <span>dependency file (pyproject.toml)</span><strong>35</strong>
          <span>created resources</span><strong>01</strong>
          <hr>
          <span>blast radius</span><strong class="is-total">81</strong>
          <small>CRITICAL · PR PROMOTION BLOCKED UNTIL RESOLVED</small>
        </div>
      </div>
    </section>

    <!-- 03 GENERATE CHANGES -->
    <section class="ad-section ad-generate" aria-labelledby="ad-generate-title">
      <div class="ad-section-label"><span>04</span> Generate Changes</div>
      <div class="ad-problem__heading">
        <h2 id="ad-generate-title">Deterministic transforms.<br><em>Agent fallback.</em></h2>
        <p>Known migrations use deterministic AST transforms with 100% precision. Complex migrations fall back to a supervised coding agent. Either way: <strong>the patch is untrusted until AgentDiff proves it.</strong></p>
      </div>
      <div class="ad-generate__grid">
        <article>
          <span>DETERMINISTIC</span>
          <strong>AST Transforms</strong>
          <p>Provider-extensible transforms for known breaking changes. Zero hallucination risk, exact AST syntax trees.</p>
        </article>
        <article>
          <span>SUPERVISED</span>
          <strong>Agent Fallback</strong>
          <p>Coding agents handle arbitrary multi-file refactoring, but output is sandboxed and treated as unproven input.</p>
        </article>
        <article>
          <span>POLICY CORE</span>
          <strong>Untrusted by Default</strong>
          <p>Regardless of source, no code reaches your repository without passing the deterministic verification engine.</p>
        </article>
      </div>
    </section>

    <!-- 04 VERIFY SAFELY -->
    <section class="ad-section ad-verify" aria-labelledby="ad-verify-title">
      <div class="ad-section-label"><span>05</span> Verify Safely</div>
      <div class="ad-problem__heading">
        <h2 id="ad-verify-title">Clean-room proof.<br><em>No shortcuts.</em></h2>
        <p>Every generated patch is replayed in an isolated worktree. Tests, types, and linters run in a clean environment, completely detached from the generation process. If tests fail, the bounded repair loop steps in.</p>
      </div>
      <div class="ad-verify__flow" aria-label="Verification ladder">
        <article>
          <span>V0 · SYNTAX</span>
          <strong>AST Validity</strong>
          <p>Parses without errors across all modified files.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article>
          <span>V1 · TYPES</span>
          <strong>Static Analysis</strong>
          <p>Type checks and imports verified in clean room.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article>
          <span>V2 · TARGETED</span>
          <strong>Impact Tests</strong>
          <p>Targeted test suite for affected call sites passes.</p>
        </article>
        <i aria-hidden="true">→</i>
        <article>
          <span>V3 · FULL</span>
          <strong>Repo Suite</strong>
          <p>Entire repository test suite passes cleanly.</p>
        </article>
      </div>
      <div class="ad-recovery__command"><code>$ agentdiff prove &lt;run-id&gt; &amp;&amp; agentdiff promote &lt;run-id&gt;</code><span>Clean-room proof → conflict-safe promotion</span></div>
    </section>

    <!-- 05 DELIVER PR -->
    <section class="ad-section ad-deliver" aria-labelledby="ad-deliver-title">
      <div class="ad-section-label"><span>06</span> Deliver PR</div>
      <div class="ad-problem__heading">
        <h2 id="ad-deliver-title">One PR.<br><em>Full evidence.</em></h2>
        <p>The verified patch is promoted to a pull request with an attached Migration Certificate detailing the upstream change, affected files, test results, proof digest, and rollback command.</p>
      </div>
      <div class="ad-deliver__cert">
        <div class="ad-deliver__cert-header">
          <div class="ad-window-dots" aria-hidden="true"><i></i><i></i><i></i></div>
          <code>Migration Certificate · openai 0.28 → 1.0</code>
          <span class="ad-runtime-status"><i></i> verified</span>
        </div>
        <div class="ad-deliver__cert-body">
          <div><span>Trigger</span><strong>openai SDK 0.28 → 1.0 (ChatCompletion removal)</strong></div>
          <div><span>Affected files</span><strong>3 files · 7 call sites detected via AST</strong></div>
          <div><span>Migration method</span><strong>Deterministic AST transform (zero hallucinations)</strong></div>
          <div><span>Blast radius</span><strong>12/100 · LOW (safe for automated promotion)</strong></div>
          <div><span>Verification</span><strong>V3 Passed (42/42 targeted + full suite green)</strong></div>
          <div><span>Proof digest</span><strong><code>sha256:e45c0d69a41e9b28...</code></strong></div>
          <div><span>Rollback</span><strong><code>agentdiff rollback &lt;id&gt; --safe-only</code></strong></div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         DIFFERENTIATION MATRIX
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-compare ad-section" id="compare" aria-labelledby="ad-compare-title">
      <div class="ad-section-label"><span>07</span> Differentiation</div>
      <div class="ad-fit__heading">
        <h2 id="ad-compare-title">Not another coding agent.<br><em>The trust layer.</em></h2>
        <p>Coding agents generate code. Dependabot bumps versions. Neither scores blast radius, verifies changes in clean rooms, or attaches cryptographic proof. AgentDiff is the verifier between generation and deployment.</p>
      </div>
      <div class="ad-fit__table ad-compare__table">
        <div class="ad-fit__head"><span>Capability</span><span>Copilot / Cursor</span><span>Dependabot</span><span>AgentDiff</span></div>
        <div><b>Blast radius scoring</b><span>—</span><span>—</span><em>0–100 deterministic score</em></div>
        <div><b>Policy enforcement</b><span>—</span><span>Basic branch rules</span><em>allow / review / deny per path</em></div>
        <div><b>Clean-room proof</b><span>—</span><span>CI pass/fail only</span><em>Replay in isolated worktree</em></div>
        <div><b>Selective rollback</b><span>Undo all changes</span><span>Revert whole PR</span><em>Conflict-safe per-file recovery</em></div>
        <div><b>Independent verification</b><span>Self-reporting model</span><span>—</span><em>External verification engine</em></div>
        <div><b>Migration certificates</b><span>—</span><span>—</span><em>Machine-readable audit capsules</em></div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         UNDER THE HOOD — Deep Technical Details
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-cortex ad-section" id="engine" aria-labelledby="ad-engine-title">
      <div class="ad-section-label"><span>08</span> Under The Hood</div>
      <div class="ad-cortex__heading">
        <h2 id="ad-engine-title">Trust engine<br><em>architecture.</em></h2>
        <p>Built on deterministic foundations: no-follow filesystem scanning, tamper-evident SHA-256 digests, warm isolated workspaces, and safe promotion.</p>
      </div>
      <div class="ad-cortex__providers">
        <article>
          <span>PROOF ENGINE</span>
          <strong>Clean-Room Replay</strong>
          <p>Every patch is replayed in a fresh, isolated worktree. Syntax, types, and test suites run from scratch with zero leakage from the agent environment.</p>
        </article>
        <article>
          <span>EVIDENCE</span>
          <strong>Durable Capsules</strong>
          <p>Captures before/after manifests, SHA-256 checksums, policy provenance, blast-radius components, and process identifiers in a versioned local capsule.</p>
        </article>
        <article>
          <span>RECOVERY</span>
          <strong>Selective Rollback</strong>
          <p>Targeted undo for review and deny mutations without blowing away allowed work. Human edits become conflicts and are safely preserved.</p>
        </article>
      </div>
      <div class="ad-underhood__row">
        <article>
          <span>REPAIR LOOP</span>
          <strong>Bounded Retries</strong>
          <p>When proof fails, the automatic repair loop retries the patch—strictly bounded to the initial task scope. No infinite agent loops.</p>
        </article>
        <article>
          <span>POLICY ENGINE</span>
          <strong>Deterministic Rules</strong>
          <p>Fine-grained path rules with explicit provenance. Every mutation is categorized with allow, review, or deny and audit trail.</p>
        </article>
        <article>
          <span>WARM WORKSPACES</span>
          <strong>Zero Cold Starts</strong>
          <p>Pre-warmed workspace snapshots enable sub-second clean-room verification runs without costly dependency reinstallations.</p>
        </article>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         TRUST MODEL
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-trust ad-section" id="trust" aria-labelledby="ad-trust-title">
      <div class="ad-trust__mark" aria-hidden="true">[ ! ]</div>
      <div>
        <div class="ad-section-label ad-section-label--light"><span>09</span> Honest Boundaries</div>
        <h2 id="ad-trust-title">Evidence, not<br>security theater.</h2>
      </div>
      <div class="ad-trust__content">
        <p>The local runtime observes a subprocess. It does not pretend to be a kernel sandbox just because an AI agent executed the command.</p>
        <ul>
          <li><span>Does</span> capture no-follow filesystem state and versioned evidence</li>
          <li><span>Does</span> enforce command mutation policy before local process launch</li>
          <li><span>Does not</span> block network access in local observation mode</li>
          <li><span>Does not</span> claim causal ownership of machine-wide port changes</li>
        </ul>
        <a href="https://github.com/kam6l/agentdiff/blob/main/SECURITY.md" target="_blank" rel="noopener noreferrer">Read the full security trust model <span aria-hidden="true">↗</span></a>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         CURRENT CAPABILITIES & ROADMAP
         ═══════════════════════════════════════════════════════════════ -->
    <section class="ad-status ad-section" id="roadmap" aria-labelledby="ad-status-title">
      <div class="ad-section-label"><span>10</span> Transparency</div>
      <div class="ad-fit__heading">
        <h2 id="ad-status-title">What works today.<br><em>What's coming next.</em></h2>
        <p>AgentDiff is in public beta. Here is an honest accounting of current production capabilities and our near-term roadmap.</p>
      </div>
      <div class="ad-status__grid">
        <div class="ad-status__column">
          <div class="ad-status__header"><span></span> Current Capabilities (Beta)</div>
          <ul class="ad-status__list">
            <li><strong>AST-based API scanning</strong> Zero-false-positive call site detection (OpenAI &amp; Stripe)</li>
            <li><strong>Dependency &amp; SDK matching</strong> Catalog matching with version awareness</li>
            <li><strong>Blast radius scoring</strong> Deterministic 0–100 impact scoring</li>
            <li><strong>Clean-room verification</strong> Isolated worktree proof engine</li>
            <li><strong>Policy engine</strong> Allow / review / deny rules with provenance</li>
            <li><strong>Evidence capsules</strong> Tamper-evident manifests with SHA-256 hashes</li>
            <li><strong>Selective recovery</strong> Conflict-safe per-file rollback (<code>--safe-only</code>)</li>
            <li><strong>Zero-touch wrapper</strong> Automated agent execution via <code>agentdiff wrap</code></li>
          </ul>
        </div>
        <div class="ad-status__column ad-status__column--future">
          <div class="ad-status__header ad-status__header--future"><span></span> Roadmap (In Progress)</div>
          <ul class="ad-status__list">
            <li><strong>Automated AST migrations</strong> Built-in transforms for major SDK transitions</li>
            <li><strong>Verified GitHub PRs</strong> Direct PR delivery with Migration Certificates</li>
            <li><strong>API Change Manifests</strong> Standardized machine-readable change format</li>
            <li><strong>Graduated proof ladder</strong> Verification levels V0 through V5</li>
            <li><strong>Expanded provider catalogs</strong> AWS SDK, Anthropic, LangChain, Twilio</li>
            <li><strong>Signed release artifacts</strong> PyPI Trusted Publishing with provenance</li>
            <li><strong>OpenTelemetry export</strong> Standardized evidence export to telemetry collectors</li>
          </ul>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         FINAL CALL TO ACTION
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
    <div><b>Learn</b><a href="docs/">Documentation</a><a href="docs/quickstart/">Quickstart</a><a href="docs/cli/">CLI Reference</a></div>
    <div><b>Project</b><a href="https://github.com/kam6l/agentdiff" target="_blank" rel="noopener noreferrer">GitHub</a><a href="https://github.com/kam6l/agentdiff/issues" target="_blank" rel="noopener noreferrer">Issues</a><a href="https://github.com/kam6l/agentdiff/blob/main/CONTRIBUTING.md" target="_blank" rel="noopener noreferrer">Contributing</a></div>
    <div><b>Trust</b><a href="https://github.com/kam6l/agentdiff/blob/main/SECURITY.md" target="_blank" rel="noopener noreferrer">Security Policy</a><a href="docs/concepts/runtime/">Runtime Model</a><a href="docs/concepts/recovery/">Recovery</a></div>
    <small>MIT licensed · AgentDiff contributors · 2026</small>
  </footer>
</div>
