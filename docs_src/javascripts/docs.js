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

  function enhanceDocs() {
    labelThemeProgress();
    if (document.querySelector("[data-agentdiff-home]")) return;
    document.body.classList.add("ad-doc-page");

    const article = document.querySelector(".md-content__inner");
    if (!article || article.dataset.docsEnhanced === "true") return;
    article.dataset.docsEnhanced = "true";

    const editAction = article.querySelector("a.md-content__button[href]");
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

      if (editAction) {
        const source = document.createElement("a");
        source.href = editAction.href;
        source.target = "_blank";
        source.rel = "noopener noreferrer";
        source.innerHTML = '<span aria-hidden="true">↗</span><span>Edit page</span>';
        actions.appendChild(source);
        editAction.hidden = true;
      }

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
    const editLink = editAction?.href || "https://github.com/kam6l/agentdiff/tree/main/docs_src";
    feedback.innerHTML = `
      <div><span>DOCUMENTATION FEEDBACK</span><strong>Was this page useful?</strong></div>
      <div>
        <a href="${encodeURI(editLink)}" target="_blank" rel="noopener noreferrer">Improve this page ↗</a>
        <a href="https://github.com/kam6l/agentdiff/issues/new" target="_blank" rel="noopener noreferrer">Report a gap ↗</a>
      </div>`;
    article.appendChild(feedback);
  }

  function setupSearchShortcut(event) {
    const target = event.target;
    if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target?.isContentEditable) return;
    if (event.key === "/" || ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k")) {
      event.preventDefault();
      const searchToggle = document.getElementById("__search");
      if (!searchToggle) return;
      searchToggle.checked = true;
      window.setTimeout(() => document.querySelector(".md-search__input")?.focus(), 30);
    }
  }

  document.addEventListener("DOMContentLoaded", enhanceDocs);
  document.addEventListener("keydown", setupSearchShortcut);
  if (typeof window.document$ !== "undefined") {
    window.document$.subscribe(enhanceDocs);
  }
})();
