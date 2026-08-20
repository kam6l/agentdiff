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

    /* Smooth scroll for anchor links */
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

    /* Evidence inspector tabs (if present on page) */
    const tabs = selectAll(root, "[data-evidence-tab]");
    const panels = selectAll(root, "[data-evidence-panel]");
    if (tabs.length && panels.length) {
      const selectTab = (tab, focus = false) => {
        const name = tab.dataset.evidenceTab;
        tabs.forEach((candidate) => {
          const selected = candidate === tab;
          candidate.setAttribute("aria-selected", String(selected));
          candidate.tabIndex = selected ? 0 : -1;
        });
        panels.forEach((panel) => {
          panel.hidden = panel.dataset.evidencePanel !== name;
        });
        if (focus) tab.focus();
      };

      tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => selectTab(tab));
        tab.addEventListener("keydown", (event) => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          let nextIndex = index;
          if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
          if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
          if (event.key === "Home") nextIndex = 0;
          if (event.key === "End") nextIndex = tabs.length - 1;
          selectTab(tabs[nextIndex], true);
        });
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
