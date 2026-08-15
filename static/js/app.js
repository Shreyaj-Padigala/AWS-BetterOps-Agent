/* Shared UI helpers for authenticated pages: navigation, session, formatting, toasts. */

const UI = (() => {
  /** Escape text before it goes into innerHTML. Every dynamic value passes through here. */
  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatDateTime(isoString) {
    if (!isoString) return "—";
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function formatRelative(isoString) {
    if (!isoString) return "—";
    const then = new Date(isoString).getTime();
    if (Number.isNaN(then)) return "—";
    const seconds = Math.round((Date.now() - then) / 1000);
    if (seconds < 60) return "just now";
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.round(hours / 24)}d ago`;
  }

  function severityBadge(severity) {
    const cls = `badge badge-${escapeHtml(severity).toLowerCase()}`;
    return `<span class="${cls}">${escapeHtml(severity)}</span>`;
  }

  function statusLabel(status) {
    return `<span class="status status-${escapeHtml(status)}">${escapeHtml(status)}</span>`;
  }

  let toastTimer = null;
  function toast(message, isError = false) {
    const node = document.getElementById("toast");
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("error", Boolean(isError));
    node.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      node.hidden = true;
    }, 4000);
  }

  /** Report an error to the user, sending them to login if the session has gone. */
  function reportError(error) {
    if (error instanceof Api.ApiError && error.status === 401) {
      window.location.href = "/login";
      return;
    }
    const detail = error instanceof Api.ApiError ? error.firstDetail : null;
    toast(detail || error.message || "Something went wrong.", true);
  }

  /** Data the server embedded in the page, e.g. the id from the URL. */
  function pageData() {
    const node = document.getElementById("page-data");
    return node ? JSON.parse(node.textContent) : {};
  }

  function markActiveNav() {
    const path = window.location.pathname;
    let key = "dashboard";
    if (path.startsWith("/projects")) key = "projects";
    else if (path.startsWith("/incidents")) key = "incidents";
    const link = document.querySelector(`[data-nav="${key}"]`);
    if (link) link.classList.add("active");
  }

  async function loadSession() {
    try {
      const session = await Api.get("/api/auth/me");
      const badge = document.getElementById("org-badge");
      if (badge) badge.textContent = session.organization.name;
    } catch (error) {
      reportError(error);
    }
  }

  function wireLogout() {
    const button = document.getElementById("logout-button");
    if (!button) return;
    button.addEventListener("click", async () => {
      try {
        await Api.post("/api/auth/logout", {});
      } finally {
        window.location.href = "/login";
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    markActiveNav();
    wireLogout();
    loadSession();
  });

  return {
    escapeHtml,
    formatDateTime,
    formatRelative,
    severityBadge,
    statusLabel,
    toast,
    reportError,
    pageData,
  };
})();
