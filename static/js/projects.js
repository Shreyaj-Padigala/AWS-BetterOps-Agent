/* Projects list and creation. */

document.addEventListener("DOMContentLoaded", () => {
  const list = document.getElementById("project-list");
  const form = document.getElementById("project-form");
  const errorNode = document.getElementById("project-form-error");
  const openButton = document.getElementById("new-project-button");
  const cancelButton = document.getElementById("project-cancel");

  function renderProjects(projects) {
    if (!projects.length) {
      list.className = "empty";
      list.innerHTML =
        "<strong>No projects yet</strong>A project is a deployed system BetterOps can investigate.";
      return;
    }

    list.className = "";
    list.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Key</th><th>Name</th><th>Primary service</th>
            <th>Open incidents</th><th>Created</th>
          </tr>
        </thead>
        <tbody>
          ${projects
            .map(
              (project) => `
            <tr>
              <td class="mono nowrap">${UI.escapeHtml(project.key)}</td>
              <td><a href="/projects/${project.id}">${UI.escapeHtml(project.name)}</a></td>
              <td>${UI.escapeHtml(project.primary_service || "—")}</td>
              <td>${project.open_incident_count ?? 0}</td>
              <td class="nowrap">${UI.escapeHtml(UI.formatDateTime(project.created_at))}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  async function load() {
    try {
      const data = await Api.get("/api/projects");
      renderProjects(data.items);
    } catch (error) {
      list.className = "empty";
      list.textContent = "Could not load projects.";
      UI.reportError(error);
    }
  }

  function toggleForm(show) {
    form.hidden = !show;
    errorNode.hidden = true;
    if (show) document.getElementById("project-name").focus();
  }

  openButton.addEventListener("click", () => toggleForm(true));
  cancelButton.addEventListener("click", () => {
    form.reset();
    toggleForm(false);
  });

  // Suggest a key from the name, but stop as soon as the user edits the key themselves.
  const keyInput = document.getElementById("project-key");
  let keyEdited = false;
  keyInput.addEventListener("input", () => {
    keyEdited = true;
  });
  document.getElementById("project-name").addEventListener("input", (event) => {
    if (keyEdited) return;
    keyInput.value = event.target.value
      .toUpperCase()
      .replace(/[^A-Z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 32);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorNode.hidden = true;

    const body = { name: form.name.value.trim(), key: form.key.value.trim() };
    ["primary_service", "repository_url", "description"].forEach((field) => {
      const value = form[field].value.trim();
      if (value) body[field] = value;
    });

    try {
      const project = await Api.post("/api/projects", body);
      UI.toast(`Project ${project.key} created.`);
      form.reset();
      keyEdited = false;
      toggleForm(false);
      load();
    } catch (error) {
      const detail = error instanceof Api.ApiError ? error.firstDetail : null;
      errorNode.textContent = detail || error.message;
      errorNode.hidden = false;
    }
  });

  load();
});
