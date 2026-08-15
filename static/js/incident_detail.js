/* Incident detail: full record plus status changes. */

document.addEventListener("DOMContentLoaded", () => {
  const { incident_id: incidentId } = UI.pageData();

  const details = document.getElementById("incident-details");
  const statusSelect = document.getElementById("status-select");

  function render(incident) {
    document.title = `${incident.reference} · AWS BetterOps Agent`;
    document.getElementById("crumb-incident").textContent = incident.reference;
    document.getElementById("incident-title").textContent = incident.title;
    document.getElementById("incident-subtitle").innerHTML = `
      ${UI.escapeHtml(incident.reference)} ·
      ${UI.severityBadge(incident.severity)} ·
      <a href="/projects/${incident.project.id}">${UI.escapeHtml(incident.project.name)}</a>`;

    details.innerHTML = `
      <dt>Status</dt><dd>${UI.statusLabel(incident.status)}</dd>
      <dt>Severity</dt><dd>${UI.severityBadge(incident.severity)}</dd>
      <dt>Affected service</dt><dd>${UI.escapeHtml(incident.affected_service || "—")}</dd>
      <dt>Started</dt><dd>${UI.escapeHtml(UI.formatDateTime(incident.started_at))}</dd>
      <dt>Resolved</dt><dd>${UI.escapeHtml(UI.formatDateTime(incident.resolved_at))}</dd>
      <dt>Reported</dt><dd>${UI.escapeHtml(UI.formatDateTime(incident.created_at))}</dd>
      <dt>Source</dt><dd>${UI.escapeHtml(incident.source)}</dd>`;

    document.getElementById("incident-description").textContent =
      incident.description || "No description provided.";

    statusSelect.value = incident.status;
    statusSelect.disabled = false;
  }

  async function load() {
    try {
      render(await Api.get(`/api/incidents/${incidentId}`));
    } catch (error) {
      document.getElementById("incident-title").textContent = "Incident unavailable";
      UI.reportError(error);
    }
  }

  statusSelect.addEventListener("change", async () => {
    const status = statusSelect.value;
    statusSelect.disabled = true;
    try {
      render(await Api.put(`/api/incidents/${incidentId}`, { status }));
      UI.toast(`Status set to ${status}.`);
    } catch (error) {
      UI.reportError(error);
      // Put the control back in sync with what the server actually holds.
      load();
    }
  });

  load();
});
