import {api, byId, element} from "./common.js";

const en = document.documentElement.lang.startsWith("en");
const focus = byId("graph-focus");
const links = byId("graph-links");
let graph;

function draw() {
  links.replaceChildren();
  const anchor = Number(focus.value);
  for (const edge of graph.edges.filter(e => e.source === anchor || e.target === anchor)) {
    const other = edge.source === anchor ? edge.target : edge.source;
    const node = graph.nodes.find(n => n.id === other);
    const branch = element("article", "graph-branch");
    const button = element("button", "secondary-button", node.filename);
    button.type = "button";
    button.onclick = () => { focus.value = String(other); draw(); };
    const reason = {
      identifier: en ? "Shared identifier" : "شناسهٔ مشترک",
      terms: en ? "Shared terms" : "واژه‌های مشترک",
      semantic: en ? "Possible similarity in meaning" : "شباهت احتمالی در معنی"
    }[edge.kind];
    const details = element("details");
    details.append(element("summary", "", [reason, ...edge.terms].join(" · ")));
    for (const source of edge.evidence) {
      const quote = element("blockquote", "", source.quote);
      quote.dir = "auto";
      details.append(element("strong", "", source.title + " · " + source.location), quote);
    }
    branch.append(button, details);
    links.append(branch);
  }
  if (!links.children.length) links.textContent = en ? "No supported connection found." : "ارتباطی با شاهد کافی پیدا نشد.";
}

focus.onchange = draw;
byId("graph-open").onclick = async () => {
  byId("graph-dialog").showModal();
  focus.replaceChildren();
  links.textContent = en ? "Loading…" : "در حال بررسی…";
  try {
    graph = await api("/api/documents/graph/");
    for (const node of graph.nodes) focus.add(new Option(node.filename, node.id));
    draw();
  } catch (error) {
    links.textContent = error.message;
  }
};
