(() => {
  "use strict";

  const selectAll = (root, selector) => Array.from(root.querySelectorAll(selector));

  function labelThemeProgress() {
    document.querySelectorAll('[role="progressbar"]:not([aria-label])').forEach((progress) => {
      progress.setAttribute("aria-label", "Page loading progress");
    });
  }

  function setupLandingPage(root) {
    if (!root || root.dataset.enhanced === "true") return;
    root.dataset.enhanced = "true";
    document.body.classList.add("ad-home-page");

    // Mobile navigation toggle
    const menuButton = root.querySelector("[data-menu-toggle]");
    const menu = root.querySelector("[data-menu]");
    const closeMenu = () => {
      if (!menuButton || !menu) return;
      menu.classList.remove("is-open");
      menuButton.setAttribute("aria-expanded", "false");
    };

    if (menuButton && menu) {
      menuButton.addEventListener("click", () => {
        const next = menuButton.getAttribute("aria-expanded") !== "true";
        menuButton.setAttribute("aria-expanded", String(next));
        menu.classList.toggle("is-open", next);
      });
      selectAll(menu, "a").forEach((link) => link.addEventListener("click", closeMenu));
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeMenu();
      });
      document.addEventListener("click", (event) => {
        if (!menu.contains(event.target) && !menuButton.contains(event.target)) closeMenu();
      });
    }

    // Copy to clipboard
    selectAll(root, "[data-copy-target]").forEach((button) => {
      button.addEventListener("click", async () => {
        const target = document.getElementById(button.dataset.copyTarget);
        if (!target) return;
        const text = target.textContent.trim();
        const flashCopied = () => {
          const label = button.querySelector("[data-copy-label]") || button;
          const original = label.textContent;
          label.textContent = "Copied";
          window.setTimeout(() => { label.textContent = original; }, 1600);
        };
        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
          try {
            await navigator.clipboard.writeText(text);
            flashCopied();
            return;
          } catch (_) {}
        }
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(target);
        selection?.removeAllRanges();
        selection?.addRange(range);
        try {
          if (document.execCommand("copy")) {
            flashCopied();
          }
        } catch (_) {}
      });
    });

    // Smooth scroll for anchor links
    selectAll(root, 'a[href^="#"]').forEach((link) => {
      link.addEventListener("click", (event) => {
        const targetId = link.getAttribute("href")?.slice(1);
        if (!targetId) return;
        const target = document.getElementById(targetId);
        if (!target) return;
        event.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        history.replaceState(null, "", `#${targetId}`);
      });
    });

    // Interactive Hero Run Card State
    const runCard = root.querySelector("[data-run-card]");
    if (runCard) {
      const stateButtons = selectAll(runCard, "[data-run-state]");
      const mutationContainer = runCard.querySelector("[data-run-mutations]");
      const score = runCard.querySelector("[data-run-score]");
      const scoreLabel = runCard.querySelector("[data-score-label]");
      const scoreUnit = runCard.querySelector("[data-score-unit]");
      const meter = runCard.querySelector("[data-run-meter]");
      const verdict = runCard.querySelector("[data-run-verdict]");
      const summary = runCard.querySelector("[data-run-summary]");
      const action = runCard.querySelector("[data-run-action]");
      const runtimeStatus = runCard.querySelector("[data-run-status]");

      const states = {
        detected: {
          rows: [
            ["is-deny", "!", ".env", "deny"],
            ["is-review", "!", "pyproject.toml", "review"],
            ["is-allow", "✓", "src/llm.py", "allow"],
          ],
          label: "BLAST RADIUS",
          score: "72",
          unit: "/100",
          width: "72%",
          color: "var(--ad-orange)",
          verdict: "HIGH · PR BLOCKED",
          status: "<i></i> recorded",
          summary: "3 call sites · 1 unexpected mutation · 1 protected",
          action: "inspect proof capsule →",
        },
        verified: {
          rows: [
            ["is-allow", "✓", "src/llm.py", "ast-migrated"],
            ["is-allow", "✓", "tests/test_llm.py", "42 passed"],
            ["is-allow", "✓", "pyproject.toml", "bumped 1.0+"],
          ],
          label: "CLEAN-ROOM PROOF",
          score: "12",
          unit: "/100",
          width: "12%",
          color: "var(--ad-lime)",
          verdict: "LOW · PR READY",
          status: "<i style='background: var(--ad-lime);'></i> verified",
          summary: "3 AST transforms · 42 tests passed · 0 conflicts",
          action: "PR ready for merge ✓",
        },
      };

      const renderState = (name) => {
        const state = states[name];
        if (!state) return;
        stateButtons.forEach((button) => {
          const selected = button.dataset.runState === name;
          button.classList.toggle("is-active", selected);
          button.setAttribute("aria-pressed", String(selected));
        });
        if (mutationContainer) {
          mutationContainer.innerHTML = state.rows.map(([klass, symbol, path, result]) => (
            `<div class="ad-mutation-row ${klass}"><b>${symbol}</b><code>${path}</code><span>${result}</span></div>`
          )).join("");
        }
        if (scoreLabel) scoreLabel.textContent = state.label;
        if (score) score.textContent = state.score;
        if (scoreUnit) scoreUnit.textContent = state.unit;
        if (meter) {
          meter.style.width = state.width;
          meter.style.background = state.color;
        }
        if (verdict) {
          verdict.textContent = state.verdict;
          verdict.style.color = name === "verified" ? "var(--ad-lime)" : "var(--ad-orange-dark)";
        }
        if (summary) summary.textContent = state.summary;
        if (action) {
          action.textContent = state.action;
          action.style.color = name === "verified" ? "var(--ad-lime)" : "var(--ad-orange-dark)";
        }
        if (runtimeStatus) runtimeStatus.innerHTML = state.status;
      };

      stateButtons.forEach((button) => {
        button.addEventListener("click", () => renderState(button.dataset.runState));
      });
    }
  }

  function boot() {
    labelThemeProgress();
    const landing = document.querySelector("[data-agentdiff-home]");
    if (landing) setupLandingPage(landing);
  }

  document.addEventListener("DOMContentLoaded", boot);
  if (typeof window.document$ !== "undefined") {
    window.document$.subscribe(boot);
  }
})();
