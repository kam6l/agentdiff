document.documentElement.classList.add("js");

(() => {
  "use strict";

  const demoStates = {
    messy: {
      score: "77",
      meter: "77%",
      summary: "2 unexpected / 3 mutations",
      verdict: "DENY · CRITICAL",
      clean: false,
      mutations: [
        ["M", "src/parser.py", "allow", "is-target"],
        ["M", "pyproject.toml", "review", "is-warning"],
        ["+", ".env", "deny", "is-warning"],
      ],
    },
    clean: {
      score: "0",
      meter: "0%",
      summary: "0 unexpected / 1 mutation",
      verdict: "ALLOW · LOW",
      clean: true,
      mutations: [["M", "src/parser.py", "allow", "is-target"]],
    },
  };

  const inspectorCounts = {
    manifest: "3 changes",
    policy: "3 decisions",
    recovery: "2 selected paths",
    processes: "identity evidence",
    ports: "1 observed endpoint",
  };

  function buildMutation([type, path, label, className]) {
    const row = document.createElement("div");
    row.className = `ad-mutation ${className}`;

    const typeNode = document.createElement("span");
    typeNode.className = "ad-mutation__type";
    typeNode.textContent = type;

    const pathNode = document.createElement("code");
    pathNode.textContent = path;

    const labelNode = document.createElement("span");
    labelNode.textContent = label;

    row.append(typeNode, pathNode, labelNode);
    return row;
  }

  function setDemoState(home, name) {
    const state = demoStates[name];
    const demo = home.querySelector(".ad-demo");
    const score = home.querySelector("[data-demo-score]");
    const meter = home.querySelector("[data-demo-meter]");
    const summary = home.querySelector("[data-demo-summary]");
    const verdict = home.querySelector("[data-demo-verdict]");
    const mutations = home.querySelector("[data-demo-mutations]");

    if (!state || !demo || !score || !meter || !summary || !verdict || !mutations) {
      return;
    }

    score.textContent = state.score;
    meter.style.width = state.meter;
    summary.textContent = state.summary;
    verdict.textContent = state.verdict;
    demo.classList.toggle("is-clean", state.clean);
    mutations.replaceChildren(...state.mutations.map(buildMutation));

    home.querySelectorAll("[data-demo-state]").forEach((button) => {
      const active = button.dataset.demoState === name;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  async function copyText(button, target) {
    const label = button.querySelector(".ad-copy__label");
    const original = label ? label.textContent : "Copy";
    const value = target.textContent.trim();

    try {
      await navigator.clipboard.writeText(value);
      if (label) label.textContent = "Copied";
    } catch (_error) {
      const input = document.createElement("textarea");
      input.value = value;
      input.setAttribute("readonly", "");
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.append(input);
      input.select();
      document.execCommand("copy");
      input.remove();
      if (label) label.textContent = "Copied";
    }

    window.setTimeout(() => {
      if (label) label.textContent = original;
    }, 1600);
  }

  function activateInspectorTab(home, selected) {
    const name = selected.dataset.inspectorTab;
    if (!name) return;

    home.querySelectorAll("[data-inspector-tab]").forEach((tab) => {
      const active = tab === selected;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });

    home.querySelectorAll("[data-inspector-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.inspectorPanel !== name;
    });

    const count = home.querySelector("[data-inspector-count]");
    if (count) count.textContent = inspectorCounts[name] || "";
  }

  function initializeHome() {
    const home = document.querySelector("[data-agentdiff-home]");
    if (!home || home.dataset.initialized === "true") return;
    home.dataset.initialized = "true";

    home.querySelectorAll("[data-demo-state]").forEach((button) => {
      button.addEventListener("click", () => setDemoState(home, button.dataset.demoState));
    });

    home.querySelectorAll("[data-copy-target]").forEach((button) => {
      button.addEventListener("click", () => {
        const target = document.getElementById(button.dataset.copyTarget);
        if (target) copyText(button, target);
      });
    });

    const tabs = [...home.querySelectorAll("[data-inspector-tab]")];
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => activateInspectorTab(home, tab));
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft"].includes(event.key)) {
          return;
        }
        event.preventDefault();
        const direction = ["ArrowDown", "ArrowRight"].includes(event.key) ? 1 : -1;
        const next = tabs[(index + direction + tabs.length) % tabs.length];
        activateInspectorTab(home, next);
        next.focus();
      });
    });

    const reveals = home.querySelectorAll(".ad-reveal");
    if (!("IntersectionObserver" in window)) {
      reveals.forEach((element) => element.classList.add("is-visible"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -8%", threshold: 0.08 },
    );
    reveals.forEach((element) => observer.observe(element));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeHome, { once: true });
  } else {
    initializeHome();
  }

  if (typeof window.document$ !== "undefined") {
    window.document$.subscribe(initializeHome);
  }
})();
