import { marked } from "/assets/vendor/marked.js";
import DOMPurify from "/assets/vendor/purify.js";

const content = document.querySelector("#content");
const status = document.querySelector("#status");
const rawButton = document.querySelector("#raw");
const copyButton = document.querySelector("#copy");
const tabs = [["issue", "Issue"], ["pr", "Pull request"], ["patch", "Files changed"], ["files", "Evidence and source"], ["metrics", "Measurements"]];
let review;
let active;
let currentText = "";
let raw = false;
let request = 0;
const escape = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const fileURL = (path, download = false) => "/file?" + new URLSearchParams({ item: active.id, path, ...(download ? { download: "1" } : {}) });

async function fetchText(path) {
  const response = await fetch(fileURL(path));
  if (!response.ok) throw new Error(await response.text());
  return response.text();
}

function markdown(text) {
  const renderer = new marked.Renderer();
  renderer.image = ({ href, text: label }) => {
    const file = active.files.find((entry) => entry.role === "screenshot" && (entry.path === href || entry.url === href));
    return file ? `<a href="${escape(fileURL(file.path))}" target="_blank" rel="noreferrer"><img src="${escape(fileURL(file.path))}" alt="${escape(label)}"></a>` : escape(label);
  };
  content.innerHTML = DOMPurify.sanitize(marked.parse(text, { renderer }));
  for (const link of content.querySelectorAll("a[href]")) {
    const href = link.getAttribute("href");
    const file = active.files.find((entry) => entry.path === href || entry.url === href);
    if (file) link.href = fileURL(file.path, file.role !== "screenshot");
    else if (!/^(?:https?:\/\/|mailto:|#|\/file\?)/i.test(href)) {
      link.removeAttribute("href");
      link.title = "File is not included in this review manifest";
    }
    link.target = "_blank";
    link.rel = "noreferrer";
  }
  for (const table of content.querySelectorAll("table")) {
    const wrapper = document.createElement("div");
    wrapper.className = "table-scroll";
    table.before(wrapper);
    wrapper.append(table);
  }
}

async function route() {
  const token = ++request;
  const [id, chosen] = location.hash.replace(/^#\/?/, "").split("/");
  active = review.items.find((item) => item.id === id) || review.items[0];
  const tab = tabs.some(([key]) => key === chosen) ? chosen : "issue";
  raw = false;
  currentText = "";
  status.textContent = "";
  content.classList.remove("error");
  document.querySelector("#title").textContent = ["issue", "pr"].includes(tab) ? active[tab].title : active.title;
  document.querySelector("#context").textContent = [active.baseline && "Baseline: " + active.baseline, active.candidate && "Candidate: " + active.candidate, active.types.join(", "), "PR mode: " + (active.pr.draft ? "draft" : "ready")].filter(Boolean).join(" · ");
  document.querySelector("#items").innerHTML = review.items.map((item) => `<button data-item="${item.id}" ${item.id === active.id ? 'aria-current="page"' : ""}>${escape(item.title)}</button>`).join("");
  document.querySelectorAll("[data-item]").forEach((button) => button.onclick = () => { location.hash = "/" + button.dataset.item + "/issue"; });
  document.querySelector("#tabs").innerHTML = tabs.map(([key, label]) => `<button data-tab="${key}" role="tab" aria-selected="${key === tab}">${label}</button>`).join("");
  document.querySelectorAll("[data-tab]").forEach((button) => button.onclick = () => { location.hash = "/" + active.id + "/" + button.dataset.tab; });
  document.querySelector("#archive").href = "/archive?" + new URLSearchParams({ item: active.id });
  rawButton.hidden = copyButton.hidden = !["issue", "pr"].includes(tab);
  rawButton.textContent = "Raw Markdown";
  content.textContent = "Loading…";
  try {
    if (tab === "issue" || tab === "pr") {
      const text = await fetchText(active[tab].body);
      if (token !== request) return;
      currentText = text;
      markdown(text);
      if (active[tab].url) {
        const link = document.createElement("a");
        link.href = active[tab].url;
        link.textContent = "Open published " + (tab === "pr" ? "PR" : "issue");
        link.target = "_blank";
        link.rel = "noreferrer";
        content.prepend(link);
      }
    } else if (tab === "patch") {
      const text = await fetchText(active.patch);
      if (token !== request) return;
      const pre = document.createElement("pre");
      pre.innerHTML = text.split("\n").map((line) => `<span class="diff-line ${line.startsWith("+") ? "added" : line.startsWith("-") ? "removed" : ""}">${escape(line)}</span>`).join("");
      content.replaceChildren(pre);
    } else if (tab === "files") {
      let selection = 0;
      content.innerHTML = active.files.map((file) => `<div class="file-row"><button data-source="${escape(file.path)}">${escape(file.path)}</button><span>${file.bytes} bytes · ${escape(file.role)}</span><a href="${escape(fileURL(file.path, true))}">Download</a></div>`).join("") + '<pre id="source">Select a file to inspect its complete text.</pre>';
      for (const button of content.querySelectorAll("[data-source]")) {
        button.onclick = async () => {
          const selected = ++selection;
          const file = active.files.find((entry) => entry.path === button.dataset.source);
          const target = document.querySelector("#source");
          if (file.bytes > 2 * 1024 * 1024 || !/\.(?:md|txt|json|jsonl|csv|log|py|sh|js|mjs|cjs|ts|tsx|patch|yml|yaml)$/i.test(file.path)) {
            target.textContent = "Use Download for the complete original file (" + file.bytes + " bytes).";
            return;
          }
          try {
            const text = await fetchText(file.path);
            if (token === request && selected === selection) target.textContent = text;
          } catch (error) {
            if (token === request && selected === selection) target.textContent = error.message;
          }
        };
      }
    } else {
      content.innerHTML = active.metrics.length ? '<div class="table-scroll"><table><thead><tr><th>Metric</th><th>Before</th><th>After</th><th>Scope / source</th></tr></thead><tbody>' + active.metrics.map((metric) => `<tr><td>${escape(metric.label)} (${escape(metric.unit)})</td><td>${escape(metric.before)}</td><td>${escape(metric.after)}</td><td>${escape(metric.scope)}<br><a href="${escape(fileURL(metric.source, true))}">${escape(metric.source)}</a></td></tr>`).join("") + "</tbody></table></div>" : "No comparison metrics supplied.";
    }
  } catch (error) {
    if (token === request) {
      content.textContent = error.message;
      content.classList.add("error");
    }
  }
}

rawButton.onclick = () => {
  raw = !raw;
  rawButton.textContent = raw ? "Rendered Markdown" : "Raw Markdown";
  if (raw) {
    const textarea = document.createElement("textarea");
    textarea.readOnly = true;
    textarea.value = currentText;
    textarea.setAttribute("aria-label", "Complete Markdown source");
    content.replaceChildren(textarea);
  } else markdown(currentText);
};
copyButton.onclick = async () => {
  try {
    if (window.isSecureContext && navigator.clipboard) await navigator.clipboard.writeText(currentText);
    else {
      const textarea = document.createElement("textarea");
      textarea.value = currentText;
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      document.body.append(textarea);
      textarea.select();
      const copied = document.execCommand("copy");
      textarea.remove();
      if (!copied) throw new Error("Copy unavailable; use Raw Markdown.");
    }
    status.textContent = "Full text copied";
  } catch (error) { status.textContent = error.message; }
};
window.addEventListener("hashchange", () => { void route(); });
try {
  const response = await fetch("/api/review");
  if (!response.ok) throw new Error(await response.text());
  review = await response.json();
  document.querySelector("#project").textContent = review.project;
  await route();
} catch (error) { content.textContent = error.message; }
