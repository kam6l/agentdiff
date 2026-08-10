// E2B-style navigation for AgentDiff docs
// Handles: tab navigation, collapsible sidebar sections, search (Ctrl+K), theme toggle

(() => {
  "use strict";

  // State
  let searchIndex = null;
  let activeTab = "documentation";
  const tabs = ["documentation", "sdk-reference", "api-reference", "changelog"];

  // Initialize
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  function init() {
    setupTabs();
    setupSidebar();
    setupSearch();
    setupTheme();
    setupCodeTabs();
    setupCopyButtons();
    setupScrollSpy();
    setupGitHubStars();
  }

  // ============================================
  // TOP TABS (Documentation, SDK Reference, API Reference, Changelog)
  // ============================================
  function setupTabs() {
    const tabBar = document.querySelector(".md-tabs");
    if (!tabBar) return;

    // Find or create tab container
    let tabContainer = tabBar.querySelector(".e2b-tabs");
    if (!tabContainer) {
      tabContainer = document.createElement("div");
      tabContainer.className = "e2b-tabs";
      tabContainer.setAttribute("role", "tablist");
      tabContainer.style.cssText = `
        display: flex;
        gap: 4px;
        padding: 0 12px;
        height: 48px;
        align-items: center;
        border-bottom: 1px solid var(--md-default-fg-color--lightest);
      `;
      
      // Move existing tabs inside
      const existingTabs = tabBar.querySelector(".md-tabs__list");
      if (existingTabs) {
        tabContainer.appendChild(existingTabs);
      }
      tabBar.appendChild(tabContainer);
    }

    // Add our custom tabs if they don't exist
    if (!tabContainer.querySelector("[data-e2b-tab]")) {
      tabs.forEach((tab, index) => {
        const btn = document.createElement("button");
        btn.className = "e2b-tab" + (index === 0 ? " active" : "");
        btn.setAttribute("data-e2b-tab", tab);
        btn.setAttribute("role", "tab");
        btn.setAttribute("aria-selected", index === 0 ? "true" : "false");
        btn.tabIndex = index === 0 ? 0 : -1;
        btn.textContent = formatTabName(tab);
        btn.style.cssText = `
          background: none;
          border: none;
          color: var(--md-default-fg-color--light);
          font: inherit;
          font-size: 13px;
          font-weight: 600;
          padding: 8px 16px;
          border-radius: 6px;
          cursor: pointer;
          transition: color 150ms ease, background 150ms ease;
        `;
        btn.addEventListener("click", () => switchTab(tab));
        btn.addEventListener("keydown", (e) => handleTabKeydown(e, tabs));
        tabContainer.appendChild(btn);
      });
    }
  }

  function formatTabName(tab) {
    const names = {
      "documentation": "Documentation",
      "sdk-reference": "SDK Reference",
      "api-reference": "API Reference",
      "changelog": "Changelog"
    };
    return names[tab] || tab;
  }

  function switchTab(tabName) {
    activeTab = tabName;
    
    // Update button states
    document.querySelectorAll("[data-e2b-tab]").forEach(btn => {
      const isActive = btn.dataset.e2bTab === tabName;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-selected", isActive);
      btn.tabIndex = isActive ? 0 : -1;
    });

    // Update content visibility
    document.querySelectorAll(".md-nav__list").forEach(list => {
      const isDocTab = list.closest("[data-md-component=tabs]")?.dataset.mdTab === "documentation";
      // Material handles tab content switching; we just need to ensure our custom tabs sync
    });
  }

  function handleTabKeydown(e, tabList) {
    const currentIndex = tabList.indexOf(e.target.dataset.e2bTab);
    let nextIndex = currentIndex;
    
    if (e.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabList.length;
    else if (e.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabList.length) % tabList.length;
    else if (e.key === "Home") nextIndex = 0;
    else if (e.key === "End") nextIndex = tabList.length - 1;
    else return;
    
    e.preventDefault();
    const nextTab = document.querySelector(`[data-e2b-tab="${tabList[nextIndex]}"]`);
    if (nextTab) {
      nextTab.focus();
      nextTab.click();
    }
  }

  // ============================================
  // COLLAPSIBLE SIDEBAR SECTIONS
  // ============================================
  function setupSidebar() {
    const nav = document.querySelector(".md-nav");
    if (!nav) return;

    nav.querySelectorAll(".md-nav__item--section > .md-nav__link").forEach(link => {
      const title = link.textContent.trim();
      const list = link.nextElementSibling;
      
      if (!list || !list.classList.contains("md-nav__list")) return;

      // Make it a button instead of a link
      const btn = document.createElement("button");
      btn.className = "e2b-nav-section";
      btn.setAttribute("aria-expanded", "true");
      btn.setAttribute("type", "button");
      btn.innerHTML = `
        <span class="e2b-nav-section__title">${title}</span>
        <svg class="e2b-nav-section__icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
          <path fill="currentColor" d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/>
        </svg>
      `;
      btn.style.cssText = `
        display: flex;
        align-items: center;
        justify-content: space-between;
        width: 100%;
        background: none;
        border: none;
        color: inherit;
        font: inherit;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        padding: 8px 0;
        cursor: pointer;
        text-align: left;
      `;

      const icon = btn.querySelector(".e2b-nav-section__icon");
      icon.style.cssText = `
        transition: transform 200ms ease;
        flex-shrink: 0;
        color: var(--md-default-fg-color--light);
      `;

      // Replace link with button
      link.replaceWith(btn);
      list.style.transition = "max-height 250ms ease, opacity 200ms ease";
      list.dataset.e2bCollapsible = "true";

      btn.addEventListener("click", () => {
        const expanded = btn.getAttribute("aria-expanded") === "true";
        btn.setAttribute("aria-expanded", String(!expanded));
        icon.style.transform = expanded ? "rotate(-90deg)" : "";
        
        if (expanded) {
          list.style.maxHeight = list.scrollHeight + "px";
          requestAnimationFrame(() => {
            list.style.maxHeight = "0";
            list.style.opacity = "0";
          });
        } else {
          list.style.maxHeight = list.scrollHeight + "px";
          list.style.opacity = "1";
          list.addEventListener("transitionend", () => {
            if (!expanded) list.style.maxHeight = "none";
          }, { once: true });
        }
      });
    });
  }

  // ============================================
  // SEARCH (Ctrl+K)
  // ============================================
  function setupSearch() {
    // Check if Material search already exists
    const existingSearch = document.querySelector(".md-search");
    if (existingSearch) {
      // Enhance existing search with Ctrl+K
      document.addEventListener("keydown", (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "k") {
          e.preventDefault();
          const input = existingSearch.querySelector("input[type=search]");
          if (input) input.focus();
        }
      });
      return;
    }

    // Build custom search if needed
    const searchBtn = document.createElement("button");
    searchBtn.className = "e2b-search-trigger";
    searchBtn.setAttribute("aria-label", "Search (Ctrl+K)");
    searchBtn.innerHTML = `
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
        <path fill="currentColor" d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
      </svg>
      <span class="e2b-search-shortcut">Ctrl+K</span>
    `;
    searchBtn.style.cssText = `
      display: flex;
      align-items: center;
      gap: 6px;
      background: var(--md-default-bg-color);
      border: 1px solid var(--md-default-fg-color--lightest);
      border-radius: 8px;
      padding: 6px 12px;
      color: var(--md-default-fg-color--light);
      font: inherit;
      font-size: 12px;
      cursor: pointer;
      transition: border-color 150ms ease, background 150ms ease;
    `;

    const header = document.querySelector(".md-header__inner");
    if (header) {
      header.appendChild(searchBtn);
    }

    // Modal search
    searchBtn.addEventListener("click", openSearchModal);
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        openSearchModal();
      }
    });
  }

  function openSearchModal() {
    if (document.querySelector(".e2b-search-modal")) return;

    const modal = document.createElement("div");
    modal.className = "e2b-search-modal";
    modal.innerHTML = `
      <div class="e2b-search-modal__overlay"></div>
      <div class="e2b-search-modal__panel" role="dialog" aria-modal="true" aria-label="Search">
        <div class="e2b-search-modal__header">
          <label for="e2b-search-input" class="e2b-search-modal__label">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path fill="currentColor" d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
            </svg>
            <input type="search" id="e2b-search-input" placeholder="Search documentation..." autocomplete="off" spellcheck="false">
            <kbd class="e2b-search-modal__shortcut">Ctrl+K</kbd>
          </label>
          <button class="e2b-search-modal__close" aria-label="Close search">
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
          </button>
        </div>
        <div class="e2b-search-modal__results" id="e2b-search-results"></div>
        <div class="e2b-search-modal__footer">
          <kbd>↑</kbd><kbd>↓</kbd> navigate &nbsp;
          <kbd>Enter</kbd> open &nbsp;
          <kbd>Esc</kbd> close
        </div>
      </div>
    `;
    modal.style.cssText = `
      position: fixed;
      inset: 0;
      z-index: 10000;
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding-top: 10vh;
      animation: e2b-search-fade 150ms ease;
    `;

    const style = document.createElement("style");
    style.textContent = `
      @keyframes e2b-search-fade { from { opacity: 0; } to { opacity: 1; } }
      .e2b-search-modal__overlay {
        position: absolute;
        inset: 0;
        background: rgba(0,0,0,0.4);
        backdrop-filter: blur(4px);
      }
      .e2b-search-modal__panel {
        position: relative;
        width: min(720px, 90vw);
        background: var(--md-default-bg-color);
        border: 1px solid var(--md-default-fg-color--lightest);
        border-radius: 12px;
        box-shadow: 0 24px 48px rgba(0,0,0,0.15);
        overflow: hidden;
        animation: e2b-search-slide 200ms ease;
      }
      @keyframes e2b-search-slide { from { transform: translateY(-20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
      .e2b-search-modal__header { padding: 16px; }
      .e2b-search-modal__label {
        display: flex;
        align-items: center;
        gap: 10px;
        width: 100%;
        background: var(--md-default-bg-color);
        border: 1px solid var(--md-default-fg-color--lightest);
        border-radius: 10px;
        padding: 12px 16px;
        color: var(--md-default-fg-color);
        font: inherit;
        font-size: 15px;
      }
      .e2b-search-modal__label:focus-within {
        border-color: var(--md-primary-fg-color);
        box-shadow: 0 0 0 3px var(--md-primary-fg-color--light);
      }
      .e2b-search-modal__label svg { color: var(--md-default-fg-color--light); flex-shrink: 0; }
      .e2b-search-modal__label input {
        flex: 1;
        background: none;
        border: none;
        outline: none;
        color: inherit;
        font: inherit;
        font-size: inherit;
        width: 100%;
      }
      .e2b-search-modal__shortcut {
        background: var(--md-default-fg-color--lightest);
        color: var(--md-default-fg-color--light);
        font: inherit;
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 4px;
      }
      .e2b-search-modal__close {
        position: absolute;
        top: 16px;
        right: 16px;
        background: none;
        border: none;
        color: var(--md-default-fg-color--light);
        padding: 8px;
        cursor: pointer;
        border-radius: 6px;
      }
      .e2b-search-modal__close:hover { background: var(--md-default-fg-color--lightest); }
      .e2b-search-modal__results {
        max-height: 50vh;
        overflow-y: auto;
        padding: 0 16px 16px;
      }
      .e2b-search-result {
        display: block;
        padding: 12px 16px;
        text-decoration: none;
        color: inherit;
        border-radius: 8px;
        margin-bottom: 4px;
        transition: background 100ms ease;
      }
      .e2b-search-result:hover { background: var(--md-default-fg-color--lightest); }
      .e2b-search-result:focus-visible { outline: 2px solid var(--md-primary-fg-color); outline-offset: -2px; }
      .e2b-search-result__title { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
      .e2b-search-result__path { font: 11px var(--md-mono); color: var(--md-default-fg-color--light); text-transform: uppercase; letter-spacing: 0.05em; }
      .e2b-search-result__excerpt { font-size: 13px; color: var(--md-default-fg-color--light); margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
      .e2b-search-modal__footer {
        display: flex;
        justify-content: center;
        gap: 16px;
        padding: 12px 16px;
        border-top: 1px solid var(--md-default-fg-color--lightest);
        font-size: 11px;
        color: var(--md-default-fg-color--light);
      }
      .e2b-search-modal__footer kbd {
        background: var(--md-default-fg-color--lightest);
        padding: 2px 6px;
        border-radius: 4px;
        font: inherit;
      }
    `;
    document.head.appendChild(style);
    document.body.appendChild(modal);

    const input = modal.querySelector("#e2b-search-input");
    const results = modal.querySelector("#e2b-search-results");
    let selectedIndex = -1;
    let resultItems = [];

    function close() {
      modal.remove();
      style.remove();
    }

    modal.querySelector(".e2b-search-modal__overlay").addEventListener("click", close);
    modal.querySelector(".e2b-search-modal__close").addEventListener("click", close);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    });

    input.focus();

    input.addEventListener("input", debounce(() => {
      const query = input.value.trim().toLowerCase();
      if (!query) {
        results.innerHTML = "";
        return;
      }
      // Simple client-side search - in production you'd use Algolia or similar
      performSearch(query);
    }, 150));

    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        selectedIndex = Math.min(selectedIndex + 1, resultItems.length - 1);
        updateSelection();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        selectedIndex = Math.max(selectedIndex - 1, 0);
        updateSelection();
      } else if (e.key === "Enter" && resultItems[selectedIndex]) {
        e.preventDefault();
        resultItems[selectedIndex].click();
        close();
      }
    });

    function updateSelection() {
      resultItems.forEach((item, i) => {
        item.classList.toggle("e2b-search-result--selected", i === selectedIndex);
      });
      if (selectedIndex >= 0) {
        resultItems[selectedIndex].scrollIntoView({ block: "nearest" });
      }
    }

    function performSearch(query) {
      // This is a simple fallback - in production use Algolia/Meilisearch
      const allLinks = document.querySelectorAll(".md-content a[href]");
      const matches = [];
      allLinks.forEach(link => {
        const text = link.textContent.toLowerCase();
        if (text.includes(query)) {
          matches.push({
            title: link.textContent,
            href: link.href,
            excerpt: link.closest("p")?.textContent?.slice(0, 200) || ""
          });
        }
      });
      
      results.innerHTML = matches.slice(0, 10).map(m => `
        <a href="${m.href}" class="e2b-search-result">
          <div class="e2b-search-result__title">${m.title}</div>
          <div class="e2b-search-result__path">${new URL(m.href).pathname}</div>
          ${m.excerpt ? `<div class="e2b-search-result__excerpt">${m.excerpt}</div>` : ""}
        </a>
      `).join("");
      
      resultItems = Array.from(results.querySelectorAll(".e2b-search-result"));
      selectedIndex = -1;
    }
  }

  function debounce(fn, ms) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  }

  // ============================================
  // THEME TOGGLE (System/Light/Dark)
  // ============================================
  function setupTheme() {
    const existingToggle = document.querySelector("[data-md-toggle]");
    if (existingToggle) return; // Material handles this
  }

  // ============================================
  // CODE TABS WITH COPY BUTTON
  // ============================================
  function setupCodeTabs() {
    document.querySelectorAll(".highlight").forEach(block => {
      if (block.querySelector(".e2b-code-header")) return;

      const langs = Array.from(block.querySelectorAll("code[data-lang]"));
      if (langs.length <= 1) return;

      const header = document.createElement("div");
      header.className = "e2b-code-header";
      header.style.cssText = `
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 12px;
        background: var(--md-default-fg-color--lightest);
        border-bottom: 1px solid var(--md-default-fg-color--lighter);
        border-radius: 6px 6px 0 0;
      `;

      const tabContainer = document.createElement("div");
      tabContainer.className = "e2b-code-tabs";
      tabContainer.style.cssText = "display: flex; gap: 4px;";

      langs.forEach((code, i) => {
        const lang = code.dataset.lang || "text";
        const btn = document.createElement("button");
        btn.className = "e2b-code-tab" + (i === 0 ? " active" : "");
        btn.textContent = lang;
        btn.style.cssText = `
          background: none;
          border: none;
          color: var(--md-default-fg-color--light);
          font: inherit;
          font-size: 11px;
          font-weight: 600;
          padding: 4px 10px;
          border-radius: 4px;
          cursor: pointer;
          text-transform: capitalize;
        `;
        btn.addEventListener("click", () => {
          tabContainer.querySelectorAll(".e2b-code-tab").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          langs.forEach(c => c.hidden = true);
          code.hidden = false;
        });
        tabContainer.appendChild(btn);
      });

      const copyBtn = document.createElement("button");
      copyBtn.className = "e2b-code-copy";
      copyBtn.setAttribute("aria-label", "Copy code");
      copyBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
          <path fill="currentColor" d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>
        </svg>
      `;
      copyBtn.style.cssText = `
        background: none;
        border: none;
        color: var(--md-default-fg-color--light);
        padding: 6px;
        cursor: pointer;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
      `;
      copyBtn.addEventListener("click", async () => {
        const code = block.querySelector("code:not([hidden])") || block.querySelector("code");
        if (code) {
          await navigator.clipboard.writeText(code.textContent);
          copyBtn.innerHTML = `
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" style="color: var(--md-accent-fg-color);">
              <path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/>
            </svg>
          `;
          setTimeout(() => {
            copyBtn.innerHTML = `
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                <path fill="currentColor" d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>
              </svg>
            `;
          }, 1500);
        }
      });

      header.append(tabContainer, copyBtn);
      block.prepend(header);

      // Hide all but first
      langs.slice(1).forEach(c => c.hidden = true);
    });
  }

  // ============================================
  // COPY BUTTONS FOR INLINE CODE BLOCKS
  // ============================================
  function setupCopyButtons() {
    document.querySelectorAll("pre > code:not(.hljs)").forEach(code => {
      if (code.parentElement.querySelector(".e2b-copy-inline")) return;
      
      const btn = document.createElement("button");
      btn.className = "e2b-copy-inline";
      btn.setAttribute("aria-label", "Copy");
      btn.innerHTML = `
        <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
          <path fill="currentColor" d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>
        </svg>
      `;
      btn.style.cssText = `
        position: absolute;
        top: 8px;
        right: 8px;
        background: var(--md-default-fg-color--lightest);
        border: none;
        color: var(--md-default-fg-color--light);
        padding: 6px;
        border-radius: 4px;
        cursor: pointer;
        opacity: 0;
        transition: opacity 150ms ease, color 150ms ease;
      `;
      code.parentElement.style.position = "relative";
      code.parentElement.appendChild(btn);
      
      code.parentElement.addEventListener("mouseenter", () => btn.style.opacity = "1");
      code.parentElement.addEventListener("mouseleave", () => btn.style.opacity = "0");
      
      btn.addEventListener("click", async () => {
        await navigator.clipboard.writeText(code.textContent);
        btn.style.color = "var(--md-accent-fg-color)";
        setTimeout(() => btn.style.color = "", 1500);
      });
    });
  }

  // ============================================
  // SCROLL SPY (Highlight active sidebar item)
  // ============================================
  function setupScrollSpy() {
    const headers = document.querySelectorAll(".md-content h2, .md-content h3");
    const navLinks = document.querySelectorAll(".md-nav__link[href^='#']");
    
    if (!headers.length || !navLinks.length) return;

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const id = entry.target.id;
          navLinks.forEach(link => {
            link.classList.toggle("md-nav__link--active", link.getAttribute("href") === "#" + id);
          });
        }
      });
    }, { rootMargin: "-20% 0px -60% 0px", threshold: 0 });

    headers.forEach(h => observer.observe(h));
  }

  // ============================================
  // GITHUB STARS IN SIDEBAR
  // ============================================
  function setupGitHubStars() {
    const repo = "kam6l/agentdiff";
    const badgeContainer = document.querySelector(".md-nav__list:first-child");
    if (!badgeContainer) return;

    // Check if already exists
    if (badgeContainer.querySelector(".e2b-github-stars")) return;

    const badge = document.createElement("a");
    badge.className = "e2b-github-stars md-nav__link";
    badge.href = `https://github.com/${repo}`;
    badge.target = "_blank";
    badge.rel = "noopener";
    badge.innerHTML = `
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <path fill="currentColor" d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.123-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.228 2.85.105 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.605-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 21.797 24 17.297 24 12c0-6.627-5.373-12-12-12z"/>
      </svg>
      <span>${repo}</span>
      <span class="e2b-github-stars__count" id="e2b-stars-count">—</span>
    `;
    badge.style.cssText = `
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 8px;
      background: var(--md-default-fg-color--lightest);
      color: var(--md-default-fg-color);
      font-size: 12px;
      font-weight: 600;
      text-decoration: none;
      margin: 8px 0;
      transition: background 150ms ease;
    `;

    badgeContainer.parentElement.insertBefore(badge, badgeContainer);

    // Fetch stars
    fetch(`https://api.github.com/repos/${repo}`)
      .then(r => r.json())
      .then(data => {
        const count = data.stargazers_count;
        const el = document.getElementById("e2b-stars-count");
        if (el) el.textContent = count.toLocaleString();
      })
      .catch(() => {
        const el = document.getElementById("e2b-stars-count");
        if (el) el.textContent = "★";
      });
  }

  // Handle Material's instant navigation
  if (typeof window.document$ !== "undefined") {
    window.document$.subscribe(() => {
      setupSidebar();
      setupCodeTabs();
      setupCopyButtons();
      setupScrollSpy();
    });
  }
})();