const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const vm = require("node:vm");

// Minimal DOM harness: runs the production script, without a frontend dependency.
class Element {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.attributes = {};
    this.textContent = "";
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
}

function fixture() {
  return {
    schema_version: 1, updated_at: "2026-10-04T19:00:00+00:00",
    source: { title: "Engineering Portfolio", url: "https://github.com/users/geckoes/projects/999" },
    projects: [
      { project: "Temperature Monitor", priority: "PRIMARY", phase: "DEVELOPMENT",
        target: "v1.0 Portfolio Release", repository_url: "https://github.com/geckoes/temperature-monitor",
        progress: { closed: 2, total: 8, percent: 25 },
        current_milestone: { title: "M02 — API Robustness", url: "https://github.com/geckoes/temperature-monitor/milestone/3" } },
      { project: "Expected Run", priority: "NEXT", phase: "DISCOVERY", target: "MVP",
        repository_url: null, progress: null, current_milestone: null },
      { project: "Air Quality Intelligence", priority: "INCUBATING", phase: "DISCOVERY", target: null,
        repository_url: "https://github.com/geckoes/air-quality-intelligence", progress: null, current_milestone: null },
    ],
  };
}

async function run(data, options = {}) {
  const container = new Element("div");
  const requests = [];
  vm.runInNewContext(fs.readFileSync("projects-status.js", "utf8"), {
    document: {
      getElementById: () => container,
      createElement: tag => new Element(tag),
      createDocumentFragment: () => new Element("fragment"),
    },
    fetch: async (url, settings) => {
      requests.push({ url, credentials: settings.credentials });
      if (options.error) throw new Error("Network error");
      return { ok: !options.httpError, json: async () => data };
    },
    Intl, Date,
  });
  await new Promise(resolve => setImmediate(resolve));
  return { container, requests };
}

function all(node) {
  if (typeof node === "string") return [];
  return [node, ...node.children.flatMap(all)];
}

test("renders acceptance cards, one accessible progress bar and source timestamp", async () => {
  const { container, requests } = await run(fixture());
  const nodes = all(container);
  assert.equal(nodes.filter(n => n.tag === "article").length, 3);
  const bars = nodes.filter(n => n.tag === "progress");
  assert.equal(bars.length, 1);
  assert.equal(bars[0].value, 2);
  assert.equal(bars[0].max, 8);
  assert.match(bars[0].attributes["aria-label"], /25% \(2\/8\)/);
  assert(nodes.some(n => n.textContent === "PRIMARY · DEVELOPMENT"));
  assert(nodes.some(n => n.textContent === "NEXT · DISCOVERY"));
  assert(nodes.some(n => n.textContent === "INCUBATING · DISCOVERY"));
  assert(nodes.some(n => n.textContent === "M02 — API Robustness"));
  assert(nodes.some(n => n.textContent === "Target: MVP"));
  assert(nodes.some(n => n.tag === "time" && n.dateTime === fixture().updated_at));
  assert.deepEqual(requests, [{ url: "./projects-status.json", credentials: "omit" }]);
});

test("metadata is rendered as text, not injected HTML", async () => {
  const data = fixture();
  data.projects[1].project = '<img src=x onerror="alert(1)">';
  const { container } = await run(data);
  assert(all(container).some(n => n.textContent === data.projects[1].project));
  assert.equal(all(container).filter(n => n.tag === "img").length, 0);
});

test("invalid snapshots never render partial cards", async () => {
  const mutations = [
    d => { d.projects[0].progress.percent = 99; },
    d => { d.projects[1].progress = { closed: 0, total: 1, percent: 0 }; },
    d => { d.projects[2].repository_url = "javascript:alert(1)"; },
    d => { d.projects[0].current_milestone = null; },
    d => { d.projects[1].priority = "PRIMARY"; },
    d => { d.updated_at = "invalid"; },
    d => { d.projects.pop(); },
    d => { d.schema_version = 2; },
  ];
  for (const mutate of mutations) {
    const data = fixture();
    mutate(data);
    const { container } = await run(data);
    assert.equal(all(container).filter(n => n.tag === "article").length, 0);
    assert.match(container.children[0].textContent, /temporarily unavailable/);
  }
});

test("HTTP and network failure produce a readable fallback", async () => {
  for (const options of [{ error: true }, { httpError: true }]) {
    const { container } = await run(fixture(), options);
    assert.match(container.children[0].textContent, /temporarily unavailable/);
  }
});

test("completed target renders 100% without a current milestone", async () => {
  const data = fixture();
  data.projects[0].progress = { closed: 8, total: 8, percent: 100 };
  data.projects[0].current_milestone = null;
  const { container } = await run(data);
  assert(all(container).some(n => n.textContent === "All target milestones closed."));
});
