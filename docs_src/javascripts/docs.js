(() => {
  "use strict";

  function labelThemeProgress() {
    document.querySelectorAll('[role="progressbar"]:not([aria-label])').forEach((progress) => {
      progress.setAttribute("aria-label", "Page loading progress");
    });
  }

  function fallbackCopy(value) {
    const input = document.createElement("textarea");
    input.value = value;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.opacity = "0";
    input.style.pointerEvents = "none";
    document.body.appendChild(input);
    input.select();
    try {
      document.execCommand("copy");
    } catch (_) {}
    input.remove();
  }

  function copyText(value) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      return navigator.clipboard.writeText(value).catch(() => {
        fallbackCopy(value);
      });
    }
    fallbackCopy(value);
    return Promise.resolve();
  }

  function openSearch() {
    const searchToggle = document.getElementById("__search");
    if (!searchToggle) return;
    searchToggle.checked = true;
    searchToggle.dispatchEvent(new Event("change", { bubbles: true }));
    window.setTimeout(() => document.querySelector(".md-search__input")?.focus(), 40);
  }

  function enhanceSearch() {
    const search = document.querySelector(".md-search");
    const searchToggle = document.getElementById("__search");
    const trigger = document.querySelector("[data-ad-search-open]");
    const input = search?.querySelector(".md-search__input");
    if (!search || !searchToggle || !trigger || !input) return;

    search.id = "ad-doc-search";
    search.setAttribute("aria-label", "Search AgentDiff documentation");
    input.setAttribute("aria-label", "Search AgentDiff documentation");
    input.placeholder = "Search AgentDiff documentation...";

    if (trigger.dataset.searchEnhanced !== "true") {
      trigger.dataset.searchEnhanced = "true";
      let retriedValue = "";
      trigger.addEventListener("click", openSearch);
      input.addEventListener("input", () => {
        window.setTimeout(() => {
          const meta = search.querySelector(".md-search-result__meta");
          const value = input.value.trim();
          if (value && value !== retriedValue && meta?.textContent?.trim() === "Type to start searching") {
            retriedValue = value;
            input.dispatchEvent(new KeyboardEvent("keyup", { key: "Process", bubbles: true }));
          }
        }, 350);
      });
      searchToggle.addEventListener("change", () => {
        const expanded = searchToggle.checked;
        trigger.setAttribute("aria-expanded", String(expanded));
        document.body.classList.toggle("ad-search-open", expanded);
        search.setAttribute("aria-modal", String(expanded));
        if (!expanded) trigger.focus();
      });
    }
  }

  function enhanceRepoBadge() {
    const badge = document.querySelector("[data-github-repo]");
    if (!badge || badge.dataset.starsEnhanced === "true") return;
    badge.dataset.starsEnhanced = "true";

    const repo = badge.dataset.githubRepo;
    const count = badge.querySelector("[data-github-stars]");
    if (!repo || !count) return;

    fetch(`https://api.github.com/repos/${repo}`, {
      headers: { Accept: "application/vnd.github+json" },
    })
      .then((response) => {
        if (!response.ok) throw new Error("GitHub repository metadata unavailable");
        return response.json();
      })
      .then((data) => {
        if (!Number.isFinite(data.stargazers_count)) return;
        const stars = new Intl.NumberFormat("en-US").format(data.stargazers_count);
        count.textContent = stars;
        badge.setAttribute("aria-label", `${repo} on GitHub, ${stars} stars`);
      })
      .catch(() => {
        // Keep the server-rendered count when GitHub is unavailable or rate limited.
      });
  }

  function setupBackToTop() {
    let topBtn = document.getElementById("ad-back-to-top");
    if (!topBtn) {
      topBtn = document.createElement("button");
      topBtn.id = "ad-back-to-top";
      topBtn.className = "ad-back-to-top";
      topBtn.type = "button";
      topBtn.setAttribute("aria-label", "Back to top");
      topBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="18 15 12 9 6 15"></polyline>
        </svg>
      `;
      topBtn.addEventListener("click", () => {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
      document.body.appendChild(topBtn);
    }

    const onScroll = () => {
      if (window.scrollY > 280) {
        topBtn.classList.add("is-visible");
      } else {
        topBtn.classList.remove("is-visible");
      }
    };

    window.removeEventListener("scroll", onScroll);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  function clearSearchHighlights() {
    // Strip any lingering ?h= query parameter from URL
    if (window.location.search.includes("h=")) {
      const url = new URL(window.location.href);
      url.searchParams.delete("h");
      window.history.replaceState({}, "", url.pathname + (url.search ? url.search : "") + url.hash);
    }
    // Unwrap any mark elements created by search highlight in page content
    document.querySelectorAll(".md-content mark, .md-content__inner mark").forEach((mark) => {
      const parent = mark.parentNode;
      if (!parent) return;
      while (mark.firstChild) {
        parent.insertBefore(mark.firstChild, mark);
      }
      mark.remove();
    });
  }

  function enhanceDocs() {
    labelThemeProgress();
    clearSearchHighlights();
    if (document.querySelector("[data-agentdiff-home]")) return;
    document.body.classList.add("ad-doc-page");
    enhanceSearch();
    enhanceRepoBadge();

    const article = document.querySelector(".md-content__inner");
    if (!article || article.dataset.docsEnhanced === "true") return;
    article.dataset.docsEnhanced = "true";

    // Remove any default Material edit buttons or stray top anchors in content
    article.querySelectorAll(".md-content__button, .md-top").forEach((el) => el.remove());

    const h1 = article.querySelector("h1");
    if (h1) {
      const actions = document.createElement("div");
      actions.className = "ad-doc-page-actions";

      const copy = document.createElement("button");
      copy.type = "button";
      copy.innerHTML = '<span class="md-icon" aria-hidden="true">⧉</span><span>Copy link</span>';
      copy.addEventListener("click", async () => {
        await copyText(window.location.href);
        const label = copy.querySelector("span:last-child");
        if (label) {
          label.textContent = "Copied";
          window.setTimeout(() => { label.textContent = "Copy link"; }, 1500);
        }
      });
      actions.appendChild(copy);

      h1.before(actions);
    }

    article.querySelectorAll("pre > code[class*='language-']").forEach((code) => {
      const pre = code.parentElement;
      if (!pre || pre.dataset.languageLabel) return;
      const languageClass = Array.from(code.classList).find((name) => name.startsWith("language-"));
      if (!languageClass) return;
      const language = languageClass.replace("language-", "");
      if (["text", "console"].includes(language)) return;
      pre.dataset.languageLabel = language;
    });

    const feedback = document.createElement("aside");
    feedback.className = "ad-doc-feedback";
    feedback.setAttribute("aria-label", "Documentation feedback");
    feedback.innerHTML = `
      <div><span>DOCUMENTATION FEEDBACK</span><strong>Was this page useful?</strong></div>
      <div>
        <a href="https://github.com/kam6l/agentdiff/issues/new" target="_blank" rel="noopener noreferrer">Give feedback / Report a gap ↗</a>
      </div>`;
    article.appendChild(feedback);

    setupBackToTop();
  }

  function setupSearchShortcut(event) {
    const target = event.target;
    if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target?.isContentEditable) return;
    if (event.key === "/" || ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k")) {
      event.preventDefault();
      openSearch();
    }
  }

  document.addEventListener("DOMContentLoaded", enhanceDocs);
  document.addEventListener("keydown", setupSearchShortcut);
  if (typeof window.document$ !== "undefined") {
    window.document$.subscribe(enhanceDocs);
  }
})();
