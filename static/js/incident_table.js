/* Shared incident table rendering.
 *
 * The dashboard, the project page and the incident list all show the same rows, so the
 * markup is defined once here.
 */

const IncidentTable = (() => {
  function row(incident, { showProject }) {
    const projectCell = showProject
      ? `<td class="nowrap"><a href="/projects/${incident.project.id}">${UI.escapeHtml(
          incident.project.key
        )}</a></td>`
      : "";

    return `
      <tr>
        <td class="mono nowrap">${UI.escapeHtml(incident.reference)}</td>
        <td><a href="/incidents/${incident.id}">${UI.escapeHtml(incident.title)}</a></td>
        ${projectCell}
        <td class="nowrap">${UI.severityBadge(incident.severity)}</td>
        <td class="nowrap">${UI.statusLabel(incident.status)}</td>
        <td class="nowrap">${UI.escapeHtml(incident.affected_service || "—")}</td>
        <td class="nowrap" title="${UI.escapeHtml(UI.formatDateTime(incident.started_at))}">
          ${UI.escapeHtml(UI.formatRelative(incident.started_at))}
        </td>
      </tr>`;
  }

  /**
   * Replace `container`'s contents with a table of incidents, or an empty state.
   * `emptyMessage` is plain text describing what the user can do next.
   */
  function render(container, incidents, { showProject = true, emptyMessage } = {}) {
    if (!incidents.length) {
      container.className = "empty";
      container.innerHTML = `<strong>No incidents</strong>${UI.escapeHtml(emptyMessage || "")}`;
      return;
    }

    container.className = "";
    container.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Ref</th>
            <th>Title</th>
            ${showProject ? "<th>Project</th>" : ""}
            <th>Severity</th>
            <th>Status</th>
            <th>Service</th>
            <th>Started</th>
          </tr>
        </thead>
        <tbody>${incidents.map((incident) => row(incident, { showProject })).join("")}</tbody>
      </table>`;
  }

  return { render };
})();
