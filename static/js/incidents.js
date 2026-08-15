/* Organization-wide incident list with status filtering and paging. */

document.addEventListener("DOMContentLoaded", () => {
  const list = document.getElementById("incident-list");
  const pager = document.getElementById("pager");
  const pageInfo = document.getElementById("page-info");
  const prevButton = document.getElementById("prev-page");
  const nextButton = document.getElementById("next-page");
  const statusFilter = document.getElementById("status-filter");

  const PAGE_SIZE = 25;
  let offset = 0;

  async function load() {
    list.className = "loading";
    list.textContent = "Loading…";

    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (statusFilter.value) params.set("status", statusFilter.value);

    try {
      const data = await Api.get(`/api/incidents?${params.toString()}`);
      IncidentTable.render(list, data.items, {
        showProject: true,
        emptyMessage: "Nothing matches this filter.",
      });
      updatePager(data.pagination);
    } catch (error) {
      list.className = "empty";
      list.textContent = "Could not load incidents.";
      UI.reportError(error);
    }
  }

  function updatePager({ total, limit, offset: currentOffset }) {
    pager.hidden = total <= limit;
    const first = total === 0 ? 0 : currentOffset + 1;
    const last = Math.min(currentOffset + limit, total);
    pageInfo.textContent = `${first}–${last} of ${total}`;
    prevButton.disabled = currentOffset === 0;
    nextButton.disabled = currentOffset + limit >= total;
  }

  prevButton.addEventListener("click", () => {
    offset = Math.max(0, offset - PAGE_SIZE);
    load();
  });
  nextButton.addEventListener("click", () => {
    offset += PAGE_SIZE;
    load();
  });
  statusFilter.addEventListener("change", () => {
    offset = 0;
    load();
  });

  load();
});
