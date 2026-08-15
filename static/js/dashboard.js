/* Dashboard: organization-level counters and the most recent incidents. */

document.addEventListener("DOMContentLoaded", async () => {
  const container = document.getElementById("recent-incidents");

  try {
    const data = await Api.get("/api/dashboard");

    document.getElementById("stat-open").textContent = data.open_incidents;
    document.getElementById("stat-total").textContent = data.total_incidents;
    document.getElementById("stat-projects").textContent = data.project_count;
    document.getElementById("stat-investigations").textContent = data.active_investigations;

    IncidentTable.render(container, data.recent_incidents, {
      showProject: true,
      emptyMessage: "Create a project, then report an incident to get started.",
    });
  } catch (error) {
    container.className = "empty";
    container.textContent = "Could not load the dashboard.";
    UI.reportError(error);
  }
});
