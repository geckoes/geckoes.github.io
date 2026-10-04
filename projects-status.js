/* GitHub is queried by Actions; the browser reads only this site's static JSON. */
(() => {
  "use strict";

  const container = document.getElementById("portfolio-status-content");
  if (!container) return;

  function require(condition) {
    if (!condition) throw new Error("Invalid portfolio status");
  }

  function githubUrl(value) {
    require(typeof value === "string" && /^https:\/\/github\.com\/[\w./%-]+$/.test(value));
    return value;
  }

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function link(text, url) {
    const node = element("a", text);
    node.href = githubUrl(url);
    return node;
  }

  function render(data) {
    require(data && data.schema_version === 1 && Array.isArray(data.projects)
      && data.projects.length === 3 && data.source);
    githubUrl(data.source.url);
    require(typeof data.source.title === "string" && data.source.title.length > 0);
    require(typeof data.updated_at === "string" && Number.isFinite(Date.parse(data.updated_at)));
    const priorities = ["PRIMARY", "NEXT", "INCUBATING"];
    const fragment = document.createDocumentFragment();

    data.projects.forEach((project, index) => {
      require(project && typeof project.project === "string" && project.project.length > 0);
      require(project.priority === priorities[index]);
      require(["DISCOVERY", "DEVELOPMENT"].includes(project.phase));
      require(project.target === null || (typeof project.target === "string" && project.target.length > 0));
      require(project.repository_url === null || typeof project.repository_url === "string");
      const card = element("article", undefined, "status-project");
      card.append(element("p", `${project.priority} · ${project.phase}`, "status-badges"));
      const heading = element("h4");
      heading.append(project.repository_url ? link(project.project, project.repository_url)
        : element("span", project.project));
      card.append(heading);
      if (project.target) card.append(element("p", `Target: ${project.target}`, "status-target"));

      if (project.phase === "DISCOVERY") {
        require(project.progress === null && project.current_milestone === null);
      } else {
        const progress = project.progress;
        require(project.target && project.repository_url && progress);
        require(Number.isInteger(progress.total) && progress.total > 0
          && Number.isInteger(progress.closed) && progress.closed >= 0 && progress.closed <= progress.total);
        require(progress.percent === Math.round(progress.closed * 100 / progress.total));
        const summary = `${progress.percent}% (${progress.closed}/${progress.total})`;
        card.append(element("p", `${summary} · milestones closed`, "status-progress-label"));
        const bar = element("progress");
        bar.max = progress.total;
        bar.value = progress.closed;
        bar.setAttribute("aria-label", `${project.project}: ${summary} milestones closed`);
        card.append(bar);
        if (progress.closed < progress.total) {
          const current = project.current_milestone;
          require(current && typeof current.title === "string" && current.title.length > 0);
          const paragraph = element("p", undefined, "status-current");
          paragraph.append("Current milestone: ", link(current.title, current.url));
          card.append(paragraph);
        } else {
          require(project.current_milestone === null);
          card.append(element("p", "All target milestones closed.", "status-current"));
        }
      }
      fragment.append(card);
    });

    const note = element("p", undefined, "status-note");
    note.append("Source: ", link(data.source.title, data.source.url), " · Updated ");
    const time = element("time", new Intl.DateTimeFormat("en", {
      dateStyle: "medium", timeStyle: "short", timeZone: "UTC",
    }).format(new Date(data.updated_at)) + " UTC");
    time.dateTime = data.updated_at;
    note.append(time);
    fragment.append(note);
    container.replaceChildren(fragment);
  }

  fetch("./projects-status.json", { credentials: "omit" })
    .then(response => {
      require(response.ok);
      return response.json();
    })
    .then(render)
    .catch(() => container.replaceChildren(element("p",
      "Portfolio status is temporarily unavailable.", "status-note")));
})();
