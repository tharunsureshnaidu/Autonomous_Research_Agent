// Vanilla JS, no build step, no framework: talks directly to the FastAPI
// endpoints already used by curl/docs. The only non-trivial piece is a small
// hand-rolled renderer for the exact Markdown shape app/agents/report_generator.py
// emits, and a fetch-based Server-Sent Events reader (the streaming endpoint
// is POST, so the native EventSource API - which only supports GET - can't be used).

const form = document.getElementById("query-form");
const input = document.getElementById("query-input");
const runBtn = document.getElementById("run-btn");
const statusLine = document.getElementById("status-line");

const traceSection = document.getElementById("trace-section");
const traceLog = document.getElementById("trace-log");
const traceToggle = document.getElementById("trace-toggle");

const reportSection = document.getElementById("report-section");
const reportCard = document.getElementById("report-card");
const downloadMd = document.getElementById("download-md");
const downloadPdf = document.getElementById("download-pdf");

const historySection = document.getElementById("history-section");
const historyList = document.getElementById("history-list");

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function inline(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(https?:\/\/[^\s)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  return html;
}

// Renders the fixed report template from report_generator.py:
//   # Research Summary
//   **Query:** ...
//   **Generated:** ...
//   ## <section>
//   - bullet
//   paragraph
function renderReportMarkdown(markdown) {
  const lines = markdown.split("\n");
  let html = "";
  let i = 0;

  if (lines[i] && lines[i].startsWith("# ")) {
    html += `<h1>${inline(lines[i].slice(2))}</h1>`;
    i++;
  }
  while (i < lines.length && lines[i].trim() === "") i++;

  const metaLines = [];
  while (i < lines.length && /^\*\*.+:\*\*/.test(lines[i])) {
    metaLines.push(inline(lines[i]));
    i++;
  }
  if (metaLines.length) html += `<p class="paper-meta">${metaLines.join("<br>")}</p>`;

  let listBuffer = [];
  let paraBuffer = [];
  const flushList = () => {
    if (listBuffer.length) {
      html += "<ul>" + listBuffer.map((item) => `<li>${inline(item)}</li>`).join("") + "</ul>";
      listBuffer = [];
    }
  };
  const flushPara = () => {
    if (paraBuffer.length) {
      html += `<p>${inline(paraBuffer.join(" "))}</p>`;
      paraBuffer = [];
    }
  };

  for (; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (trimmed === "") {
      flushList();
      flushPara();
    } else if (trimmed.startsWith("## ")) {
      flushList();
      flushPara();
      html += `<h2>${inline(trimmed.slice(3))}</h2>`;
    } else if (trimmed.startsWith("# ")) {
      flushList();
      flushPara();
      html += `<h1>${inline(trimmed.slice(2))}</h1>`;
    } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      flushPara();
      listBuffer.push(trimmed.slice(2));
    } else {
      flushList();
      paraBuffer.push(trimmed);
    }
  }
  flushList();
  flushPara();
  return html;
}

function appendTraceLine(node, message) {
  const line = document.createElement("span");
  line.className = "trace-line";
  line.innerHTML = `<span class="trace-node">[${escapeHtml(node)}]</span> ${escapeHtml(message)}`;
  traceLog.appendChild(line);
  traceLog.scrollTop = traceLog.scrollHeight;
}

function showReport(sessionId, markdown) {
  reportCard.innerHTML = renderReportMarkdown(markdown);
  downloadMd.href = `/api/history/${sessionId}/report.md`;
  downloadPdf.href = `/api/history/${sessionId}/report.pdf`;
  reportSection.classList.remove("is-hidden");
  reportSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function formatTimestamp(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

async function loadHistory() {
  const resp = await fetch("/api/history");
  if (!resp.ok) return;
  const sessions = await resp.json();
  historyList.innerHTML = "";
  if (sessions.length === 0) {
    historySection.classList.add("is-hidden");
    return;
  }
  for (const session of sessions) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "history-card";
    card.innerHTML = `
      <p class="history-query">${escapeHtml(session.query)}</p>
      <p class="history-meta">${escapeHtml(session.sources.join(", "))} &middot; ${escapeHtml(formatTimestamp(session.timestamp))}</p>
    `;
    card.addEventListener("click", () => loadSession(session.session_id));
    historyList.appendChild(card);
  }
  historySection.classList.remove("is-hidden");
}

async function loadSession(sessionId) {
  const resp = await fetch(`/api/history/${sessionId}`);
  if (!resp.ok) return;
  const { markdown } = await resp.json();
  showReport(sessionId, markdown);
}

function parseSSEEvent(rawEvent) {
  let eventType = "message";
  let dataText = "";
  for (const line of rawEvent.split("\n")) {
    if (line.startsWith("event:")) eventType = line.slice(6).trim();
    else if (line.startsWith("data:")) dataText += line.slice(5).trim();
  }
  return dataText ? { eventType, payload: JSON.parse(dataText) } : null;
}

async function streamResearch(query) {
  const resp = await fetch("/api/research/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${resp.status})`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseSSEEvent(rawEvent);
      if (!parsed) continue;

      if (parsed.eventType === "log") {
        appendTraceLine(parsed.payload.node, parsed.payload.message);
      } else if (parsed.eventType === "done") {
        traceLog.classList.remove("trace-cursor");
        if (parsed.payload.session_id) {
          showReport(parsed.payload.session_id, parsed.payload.markdown);
        }
      }
    }
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = input.value.trim();
  if (query.length < 3) return;

  runBtn.disabled = true;
  statusLine.textContent = "researching…";
  statusLine.classList.remove("is-error");
  reportSection.classList.add("is-hidden");
  traceLog.innerHTML = "";
  traceLog.classList.add("trace-cursor");
  traceSection.classList.remove("is-hidden", "is-collapsed");
  traceToggle.textContent = "collapse";

  try {
    await streamResearch(query);
    statusLine.textContent = "done.";
    loadHistory();
  } catch (err) {
    statusLine.textContent = err.message || "Something went wrong.";
    statusLine.classList.add("is-error");
  } finally {
    traceLog.classList.remove("trace-cursor");
    runBtn.disabled = false;
  }
});

traceToggle.addEventListener("click", () => {
  const collapsed = traceSection.classList.toggle("is-collapsed");
  traceToggle.textContent = collapsed ? "expand" : "collapse";
});

loadHistory();
