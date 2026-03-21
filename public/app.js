(function () {
  "use strict";

  const form = document.getElementById("generate-form");
  const urlInput = document.getElementById("url");
  const maxPagesInput = document.getElementById("max-pages");
  const advancedToggle = document.getElementById("advanced-toggle");
  const advancedFields = document.getElementById("advanced-fields");
  const submitBtn = document.getElementById("submit-btn");
  const loading = document.getElementById("loading");
  const errorBanner = document.getElementById("error-banner");
  const outputSection = document.getElementById("output-section");
  const outputText = document.getElementById("output-text");
  const copyBtn = document.getElementById("copy-btn");
  const downloadBtn = document.getElementById("download-btn");

  function showError(message) {
    errorBanner.textContent = message;
    errorBanner.hidden = false;
  }

  function hideError() {
    errorBanner.hidden = true;
    errorBanner.textContent = "";
  }

  function setLoading(isLoading) {
    loading.hidden = !isLoading;
    submitBtn.disabled = isLoading;
  }

  function validateClientUrl(value) {
    const trimmed = value.trim();
    if (!trimmed) {
      return "Enter a website URL.";
    }
    try {
      const u = new URL(trimmed);
      if (u.protocol !== "http:" && u.protocol !== "https:") {
        return "URL must start with http:// or https://.";
      }
    } catch {
      return "Enter a valid URL (e.g. https://example.com).";
    }
    return null;
  }

  advancedToggle.addEventListener("click", () => {
    const open = advancedFields.hidden;
    advancedFields.hidden = !open;
    advancedToggle.setAttribute("aria-expanded", open ? "true" : "false");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideError();
    outputSection.hidden = true;

    const url = urlInput.value.trim();
    const clientErr = validateClientUrl(url);
    if (clientErr) {
      showError(clientErr);
      return;
    }

    let maxPages = parseInt(maxPagesInput.value, 10);
    if (Number.isNaN(maxPages) || maxPages < 1) {
      maxPages = 30;
    }
    maxPages = Math.min(maxPages, 100);

    setLoading(true);

    try {
      const resp = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, maxPages }),
      });

      let data = null;
      try {
        data = await resp.json();
      } catch {
        data = null;
      }

      if (!resp.ok) {
        const msg =
          data && typeof data.error === "string"
            ? data.error
            : `Request failed (${resp.status}).`;
        showError(msg);
        return;
      }

      if (!data || typeof data.llmstxt !== "string") {
        showError("Unexpected response from the server.");
        return;
      }

      outputText.value = data.llmstxt;
      outputSection.hidden = false;
    } catch {
      showError("Network error. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  });

  copyBtn.addEventListener("click", async () => {
    const text = outputText.value;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      copyBtn.textContent = "Copied!";
      setTimeout(() => {
        copyBtn.textContent = "Copy to clipboard";
      }, 2000);
    } catch {
      showError("Could not copy to the clipboard.");
    }
  });

  downloadBtn.addEventListener("click", () => {
    const text = outputText.value;
    if (!text) return;
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "llms.txt";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });
})();
