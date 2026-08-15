/* Project detail: project summary plus its incidents, and incident reporting. */

document.addEventListener("DOMContentLoaded", () => {
  const { project_id: projectId } = UI.pageData();

  const summary = document.getElementById("project-summary");
  const list = document.getElementById("incident-list");
  const form = document.getElementById("incident-form");
  const errorNode = document.getElementById("incident-form-error");

  function renderProject(project) {
    document.getElementById("project-name").textContent = project.name;
    document.getElementById("crumb-project").textContent = project.key;
    document.getElementById("project-meta").textContent = project.description || "";

    const repository = project.repository_url
      ? `<a href="${UI.escapeHtml(project.repository_url)}" rel="noreferrer noopener" target="_blank">
           ${UI.escapeHtml(project.repository_url)}</a>`
      : "Not connected";

    summary.innerHTML = `
      <dl class="detail-list">
        <dt>Key</dt><dd class="mono">${UI.escapeHtml(project.key)}</dd>
        <dt>Primary service</dt><dd>${UI.escapeHtml(project.primary_service || "—")}</dd>
        <dt>Repository</dt><dd>${repository}</dd>
        <dt>Created</dt><dd>${UI.escapeHtml(UI.formatDateTime(project.created_at))}</dd>
      </dl>`;
  }

  async function loadProject() {
    try {
      renderProject(await Api.get(`/api/projects/${projectId}`));
    } catch (error) {
      document.getElementById("project-name").textContent = "Project unavailable";
      UI.reportError(error);
    }
  }

  async function loadIncidents() {
    try {
      const data = await Api.get(`/api/projects/${projectId}/incidents?limit=50`);
      IncidentTable.render(list, data.items, {
        showProject: false,
        emptyMessage: "Report an incident to track a production problem here.",
      });
    } catch (error) {
      list.className = "empty";
      list.textContent = "Could not load incidents.";
      UI.reportError(error);
    }
  }

  function toggleForm(show) {
    form.hidden = !show;
    errorNode.hidden = true;
    if (show) document.getElementById("incident-title").focus();
  }

  document.getElementById("new-incident-button").addEventListener("click", () => toggleForm(true));
  document.getElementById("incident-cancel").addEventListener("click", () => {
    form.reset();
    toggleForm(false);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorNode.hidden = true;

    const body = {
      title: form.title.value.trim(),
      severity: form.severity.value,
    };
    const description = form.description.value.trim();
    if (description) body.description = description;
    const service = form.affected_service.value.trim();
    if (service) body.affected_service = service;
    if (form.started_at.value) {
      // datetime-local has no timezone; convert the local wall clock to UTC so the
      // server stores the instant the reporter meant.
      body.started_at = new Date(form.started_at.value).toISOString();
    }

    try {
      const incident = await Api.post(`/api/projects/${projectId}/incidents`, body);
      UI.toast(`${incident.reference} created.`);
      form.reset();
      toggleForm(false);
      loadIncidents();
    } catch (error) {
      const detail = error instanceof Api.ApiError ? error.firstDetail : null;
      errorNode.textContent = detail || error.message;
      errorNode.hidden = false;
    }
  });

  loadProject();
  loadIncidents();
});
