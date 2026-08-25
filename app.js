let editor = null;
let currentPlan = [];
let sessionId = "";
let activeFile = null;
let isSending = false;
let selectedModelMode = "auto";

// --- Antigravity-Style Model Selector Handlers ---
function toggleModelDropdown(e) {
  e.stopPropagation();
  const menu = document.getElementById("model-dropdown-menu");
  if (!menu) return;
  menu.style.display = menu.style.display === "none" ? "flex" : "none";
}

function selectModelMode(mode, label) {
  selectedModelMode = mode;
  const labelEl = document.getElementById("current-model-label");
  if (labelEl) labelEl.innerText = label;
  document.querySelectorAll(".model-opt").forEach(el => el.classList.remove("active"));
  if (event && event.currentTarget) event.currentTarget.classList.add("active");
  const menu = document.getElementById("model-dropdown-menu");
  if (menu) menu.style.display = "none";
}

document.addEventListener("click", () => {
  const menu = document.getElementById("model-dropdown-menu");
  if (menu) menu.style.display = "none";
});

// --- Live Orchestration Pipeline Strip Handlers ---
const STAGES_ORDER = ["triage", "research", "planning", "coding", "critic", "done"];
function updateOrchStage(currentStage, label) {
  const idx = STAGES_ORDER.indexOf(currentStage);
  STAGES_ORDER.forEach((s, i) => {
    const el = document.getElementById(`stage-${s}`);
    if (!el) return;
    if (i < idx) {
      el.className = "orch-pipeline-step step-done";
    } else if (i === idx) {
      el.className = "orch-pipeline-step step-active";
    } else {
      el.className = "orch-pipeline-step";
    }
  });
  const statusEl = document.getElementById("statusbar-engine-status");
  if (statusEl && label) {
    statusEl.textContent = `Orchestra: ${label}`;
  }
}

function resetOrchStages() {
  STAGES_ORDER.forEach(s => {
    const el = document.getElementById(`stage-${s}`);
    if (el) el.className = "orch-pipeline-step";
  });
  updateOrchStage("triage", "Intent Triage & Routing");
}

// --- Live Orchestration Visualizer Modal ---
async function openOrchVisualizerModal() {
  const modal = document.getElementById("orch-modal");
  if (!modal) return;
  modal.style.display = "flex";
  const body = document.getElementById("orch-modal-body");
  body.innerHTML = '<div style="color:var(--vscode-text-muted);font-size:12px;">Fetching live orchestration trace...</div>';

  try {
    const res = await fetch(`/api/dag/${sessionId || 'default'}`);
    if (!res.ok) throw new Error("Failed to fetch DAG");
    const nodes = await res.json();

    let h = `
      <div class="telemetry-summary-row">
        <div class="telemetry-stat-card">
          <div class="stat-label">Model Mode</div>
          <div class="stat-value" style="font-size:13px;color:#89b4fa;">${esc(selectedModelMode.toUpperCase())}</div>
        </div>
        <div class="telemetry-stat-card">
          <div class="stat-label">Active Nodes</div>
          <div class="stat-value">${nodes.length || 0}</div>
        </div>
        <div class="telemetry-stat-card">
          <div class="stat-label">Session Tokens</div>
          <div class="stat-value" id="modal-tokens">${document.getElementById("metric-tokens")?.innerText || 0}</div>
        </div>
        <div class="telemetry-stat-card">
          <div class="stat-label">Est. Cost</div>
          <div class="stat-value" style="color:#a6e3a1;">${document.getElementById("metric-cost")?.innerText || "$0.0000"}</div>
        </div>
      </div>
      <div style="font-weight:600;font-size:12px;color:#fff;margin:16px 0 8px;">Execution Task Nodes & Audit Logs:</div>
    `;

    if (!nodes || !nodes.length) {
      h += '<div class="telemetry-empty-state"><div style="color:#858585;font-size:12px;">No active task graph yet. Submit a prompt to observe live node execution.</div></div>';
    } else {
      h += '<div style="display:flex;flex-direction:column;gap:8px;">';
      nodes.forEach(n => {
        const st = n.status || "pending";
        const cls = st === "done" || st === "completed" ? "completed" : st === "in_progress" ? "running" : "pending";
        h += `
          <div class="dag-node-card ${cls}">
            <div class="dag-node-header">
              <strong style="color:#fff;font-size:12px;">Node #${n.subtask_id}: ${esc(n.description)}</strong>
              <span class="dag-status-badge ${cls}">${st.toUpperCase()}</span>
            </div>
            <div class="dag-node-meta">
              <span>Role: <strong style="color:#89b4fa;">${esc(n.assigned_role || 'coder')}</strong></span>
              <span>Attempts: ${n.attempts_count || (n.attempts ? n.attempts.length : 1)}</span>
              <span>Target: ${esc((n.target_files && n.target_files[0]) || 'solution.py')}</span>
            </div>
        `;
        if (n.attempts && n.attempts.length) {
          n.attempts.forEach((att, idx) => {
            h += `
              <div class="attempt-card">
                <div style="font-size:11px;color:#a6e3a1;font-weight:600;">Attempt ${idx + 1}: ${esc(att.action || 'Subtask Execution')}</div>
                <div style="font-size:10px;color:#858585;margin-top:2px;">Result: ${esc(att.result || 'Executed successfully')}</div>
              </div>
            `;
          });
        }
        h += '</div>';
      });
      h += '</div>';
    }
    body.innerHTML = h;
  } catch (err) {
    body.innerHTML = `<div style="color:#da3633;font-size:12px;">Could not load DAG trace: ${esc(err.message)}</div>`;
  }
}

function closeOrchModal() {
  const modal = document.getElementById("orch-modal");
  if (modal) modal.style.display = "none";
}

async function init() {
  require.config({ paths: { vs: "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs" } });
  require(["vs/editor/editor.main"], function () {
    editor = monaco.editor.create(document.getElementById("monaco-container"), {
      value: "// Select a file from the workspace explorer or ask the agent to create one.\n",
      language: "plaintext",
      theme: "vs-dark",
      automaticLayout: true,
      fontSize: 13,
      fontFamily: "'JetBrains Mono', 'Fira Code', Menlo, monospace",
      minimap: { enabled: true },
      lineNumbers: "on",
      scrollBeyondLastLine: false,
      renderLineHighlight: "all",
      bracketPairColorization: { enabled: true },
    });
  });
  setupNavigation();
  setupChatKeyListeners();
  await loadSettings();
  await initSession();
  await loadFiles();
}

function setupNavigation() {
  document.querySelectorAll(".activity-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".activity-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const target = btn.getAttribute("data-target");
      document.querySelectorAll(".view-panel").forEach(p => p.classList.remove("active"));
      const panel = document.getElementById(target);
      if (panel) {
        panel.classList.add("active");
        if (target === "view-dag") loadDAGTelemetry();
        if (target === "view-diff") loadDiffReview();
        if (target === "view-settings") loadSettings();
      }
    });
  });
}

function setupChatKeyListeners() {
  const input = document.getElementById("chat-input");
  if (!input) return;
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
}

async function initSession() {
  try {
    const res = await fetch("/api/session/init", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
    if (res.ok) {
      const data = await res.json();
      const wsName = data.workspace_root.split("/").pop() || "home";
      const titleWs = document.getElementById("titlebar-ws-name");
      if (titleWs) titleWs.innerText = wsName;
      const sideWs = document.getElementById("sidebar-ws-title");
      if (sideWs) sideWs.innerText = "EXPLORER: " + wsName.toUpperCase();
      const breadWs = document.getElementById("breadcrumb-ws-name");
      if (breadWs) breadWs.innerText = wsName;
      termCwd = data.workspace_root || "";
      updateTermPrompt();
    }
  } catch (err) { console.error("Session init failed:", err); }
}

// --- File Explorer ---
async function loadFiles() {
  try {
    const res = await fetch("/api/files");
    if (!res.ok) return;
    const data = await res.json();
    const container = document.getElementById("file-list");
    container.innerHTML = "";
    if (data.files.length === 0) {
      container.innerHTML = '<div style="padding:10px 14px;color:var(--vscode-text-muted);font-size:11px;">Workspace is empty. Click + to create a file.</div>';
      return;
    }
    data.files.forEach(f => {
      const item = document.createElement("div");
      item.className = "file-item" + (activeFile === f ? " active" : "");
      const ext = f.split(".").pop().toLowerCase();
      item.innerHTML = `
        <div class="file-item-left" onclick="openFile('${esc(f)}')">
          <span class="file-icon-text">${ext}</span>
          <span>${esc(f)}</span>
        </div>
        <div class="file-actions">
          <span class="file-btn-action" title="Rename" onclick="renameFilePrompt(event, '${esc(f)}')">r</span>
          <span class="file-btn-delete" title="Delete" onclick="deleteFilePrompt(event, '${esc(f)}')">x</span>
        </div>`;
      container.appendChild(item);
    });
  } catch (err) { console.error("loadFiles error:", err); }
}

async function renameFilePrompt(event, oldPath) {
  event.stopPropagation();
  const newName = prompt(`Rename '${oldPath}' to:`, oldPath);
  if (!newName || newName.trim() === oldPath) return;
  try {
    const res = await fetch("/api/file/rename", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_path: oldPath, new_path: newName.trim() })
    });
    if (res.ok) {
      if (activeFile === oldPath) {
        activeFile = newName.trim();
        document.getElementById("active-tab-title").innerText = activeFile;
        document.getElementById("breadcrumb-file").innerText = activeFile;
      }
      await loadFiles();
    } else {
      const err = await res.json();
      alert("Rename failed: " + (err.detail || "Error"));
    }
  } catch (err) { alert("Rename failed: " + err.message); }
}

function detectLanguage(fp) {
  const m = { py:"python", ts:"typescript", tsx:"typescript", js:"javascript", jsx:"javascript",
    rs:"rust", go:"go", cpp:"cpp", cc:"cpp", c:"c", h:"c", java:"java", json:"json",
    html:"html", htm:"html", css:"css", sh:"shell", bash:"shell", md:"markdown",
    yaml:"yaml", yml:"yaml", sql:"sql", xml:"xml" };
  const ext = (fp || "").split(".").pop().toLowerCase();
  return m[ext] || "plaintext";
}

async function openFile(fp) {
  try {
    const res = await fetch(`/api/file/read?file_path=${encodeURIComponent(fp)}`);
    if (!res.ok) return;
    const data = await res.json();
    activeFile = fp;
    document.getElementById("active-tab-title").innerText = fp;
    document.getElementById("breadcrumb-file").innerText = fp;
    const lang = detectLanguage(fp);
    document.getElementById("statusbar-file-type").innerText = lang.toUpperCase();
    if (editor) { editor.setValue(data.content); monaco.editor.setModelLanguage(editor.getModel(), lang); }
    document.querySelectorAll(".file-item").forEach(el => el.classList.toggle("active", el.textContent.includes(fp)));
  } catch (err) { console.error("openFile error:", err); }
}

function createNewFilePrompt() {
  const container = document.getElementById("file-list");
  if (document.getElementById("new-file-inline-row")) return;
  const row = document.createElement("div");
  row.className = "new-file-row"; row.id = "new-file-inline-row";
  row.innerHTML = '<input type="text" class="new-file-input" placeholder="filename.ext (Enter to create, Esc to cancel)" />';
  container.prepend(row);
  const input = row.querySelector("input"); input.focus();
  const create = async () => {
    const v = input.value.trim();
    if (v) {
      const r = await fetch("/api/file/create", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ file_path: v, content: "" }) });
      if (r.ok) { await loadFiles(); await openFile(v); }
    }
    row.remove();
  };
  input.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); create(); } else if (e.key === "Escape") row.remove(); });
  input.addEventListener("blur", () => setTimeout(() => { if (row.parentNode) row.remove(); }, 200));
}

async function deleteFilePrompt(event, fp) {
  event.stopPropagation();
  if (!confirm(`Delete '${fp}'?`)) return;
  const r = await fetch("/api/file/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ file_path: fp }) });
  if (r.ok) {
    if (activeFile === fp) { activeFile = null; document.getElementById("active-tab-title").innerText = "No file open"; if (editor) editor.setValue(""); }
    await loadFiles();
  }
}

// --- Real Interactive Terminal Engine ---
let termCwd = "";  // tracks the current working directory
let termHistory = [];  // command history
let termHistoryIdx = -1;  // current position in history navigation
let termIsRunning = false;  // prevent double-submission

function toggleTerminal(e) {
  if (e) e.stopPropagation();
  const panel = document.getElementById("terminal-panel");
  panel.classList.toggle("collapsed");
  if (!panel.classList.contains("collapsed")) {
    setTimeout(focusTerminal, 50);
  }
}

function toggleMaximizeTerminal(e) {
  if (e) e.stopPropagation();
  const panel = document.getElementById("terminal-panel");
  if (panel) panel.classList.toggle("maximized");
  setTimeout(focusTerminal, 50);
}

function focusTerminal() {
  const input = document.getElementById("terminal-input");
  if (input && !termIsRunning) {
    input.focus();
  }
}

function clearTerminal(e) {
  if (e) e.stopPropagation();
  const hist = document.getElementById("term-history-lines");
  if (hist) hist.innerHTML = "";
  focusTerminal();
}

function switchTerminalTab(tab) {
  document.querySelectorAll(".terminal-tab").forEach(t => t.classList.remove("active"));
  const id = tab === "terminal" ? "tab-term" : tab === "output" ? "tab-out" : "tab-dbg";
  const el = document.getElementById(id); if (el) el.classList.add("active");
  focusTerminal();
}

function getShortCwd(cwd) {
  if (!cwd) return "~/home";
  const home = "/Users/" + (cwd.split("/")[2] || "");
  if (cwd === home) return "~";
  if (cwd.startsWith(home + "/")) return "~" + cwd.slice(home.length);
  return cwd;
}

function updateTermPrompt() {
  const promptEl = document.getElementById("terminal-prompt-path");
  if (promptEl) promptEl.textContent = getShortCwd(termCwd);
  const welcomeWs = document.getElementById("term-welcome-ws");
  if (welcomeWs) welcomeWs.textContent = getShortCwd(termCwd);
}

// ANSI Escape Code Parser -> Colored HTML
function ansiToHtml(str) {
  if (!str) return "";
  const escStr = str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const colors = {
    "30": "#282a36", "31": "#f38ba8", "32": "#a6e3a1", "33": "#f9e2af",
    "34": "#89b4fa", "35": "#cba6f7", "36": "#94e2d5", "37": "#cdd6f4",
    "90": "#6c7086", "91": "#f38ba8", "92": "#a6e3a1", "93": "#f9e2af",
    "94": "#89b4fa", "95": "#cba6f7", "96": "#94e2d5", "97": "#ffffff"
  };

  let openSpan = false;
  let formatted = escStr.replace(/\x1b\[([0-9;]+)m/g, (match, codes) => {
    let resClose = openSpan ? "</span>" : "";
    openSpan = false;

    if (codes === "0" || codes === "") {
      return resClose;
    }

    const codeArr = codes.split(";");
    let isBold = false;
    let color = "";

    codeArr.forEach(c => {
      if (c === "1") isBold = true;
      else if (colors[c]) color = colors[c];
    });

    if (color || isBold) {
      openSpan = true;
      let styleStr = "";
      if (color) styleStr += `color:${color};`;
      if (isBold) styleStr += `font-weight:700;`;
      return `${resClose}<span style="${styleStr}">`;
    }
    return resClose;
  });

  if (openSpan) formatted += "</span>";
  return formatted;
}

async function handleTerminalKey(e) {
  const inputEl = document.getElementById("terminal-input");

  if (e.key === "Enter") {
    e.preventDefault();
    executeTerminalCommand();
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    if (termHistory.length === 0) return;
    if (termHistoryIdx < termHistory.length - 1) termHistoryIdx++;
    inputEl.value = termHistory[termHistory.length - 1 - termHistoryIdx];
  } else if (e.key === "ArrowDown") {
    e.preventDefault();
    if (termHistoryIdx > 0) {
      termHistoryIdx--;
      inputEl.value = termHistory[termHistory.length - 1 - termHistoryIdx];
    } else {
      termHistoryIdx = -1;
      inputEl.value = "";
    }
  } else if (e.key === "Tab") {
    e.preventDefault();
    // Tab Auto-Completion for files
    const val = inputEl.value;
    const tokens = val.split(" ");
    const lastToken = tokens[tokens.length - 1];
    if (lastToken) {
      try {
        const res = await fetch("/api/files");
        if (res.ok) {
          const d = await res.json();
          const matches = (d.files || []).filter(f => f.toLowerCase().startsWith(lastToken.toLowerCase()));
          if (matches.length === 1) {
            tokens[tokens.length - 1] = matches[0];
            inputEl.value = tokens.join(" ");
          } else if (matches.length > 1) {
            appendTermLine(matches.join("  "), "stdout");
          }
        }
      } catch {}
    }
  } else if (e.key === "c" && e.ctrlKey) {
    e.preventDefault();
    appendTermLine(getShortCwd(termCwd) + " $ " + inputEl.value + "^C", "cmd");
    inputEl.value = "";
    termHistoryIdx = -1;
  } else if (e.key === "l" && e.ctrlKey) {
    e.preventDefault();
    clearTerminal();
  } else if (e.key === "u" && e.ctrlKey) {
    e.preventDefault();
    inputEl.value = "";
  } else if (e.key === "a" && e.ctrlKey) {
    e.preventDefault();
    inputEl.setSelectionRange(0, 0);
  } else if (e.key === "e" && e.ctrlKey) {
    e.preventDefault();
    inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length);
  }
}

async function executeTerminalCommand(customCmd) {
  if (termIsRunning) return;
  const inputEl = document.getElementById("terminal-input");
  const activeLine = document.getElementById("terminal-active-line");
  const cmd = (customCmd || inputEl.value).trim();
  if (!cmd) return;
  if (!customCmd) inputEl.value = "";

  // Add to history (avoid duplicates)
  if (termHistory.length === 0 || termHistory[termHistory.length - 1] !== cmd) {
    termHistory.push(cmd);
    if (termHistory.length > 200) termHistory.shift();
  }
  termHistoryIdx = -1;

  // Open panel if collapsed
  const panel = document.getElementById("terminal-panel");
  if (panel.classList.contains("collapsed")) panel.classList.remove("collapsed");

  // Handle local-only commands
  if (cmd === "clear" || cmd === "cls") {
    clearTerminal();
    return;
  }

  // Append user's command line to output history
  const promptHtml = `<span class="terminal-prompt">${esc(getShortCwd(termCwd))} <span class="term-prompt-arrow">$</span></span> <span>${esc(cmd)}</span>`;
  appendTermHtml(promptHtml, "cmd");

  termIsRunning = true;
  if (activeLine) activeLine.style.display = "none";

  try {
    const res = await fetch("/api/terminal/exec", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: cmd, approved: true, cwd: termCwd || undefined })
    });
    const data = await res.json();

    // Update cwd from server response
    if (data.cwd) {
      termCwd = data.cwd;
      updateTermPrompt();
    }

    // Display output with ANSI color parsing
    const output = (data.output || "").replace(/\n$/, "");
    if (output && output !== "(Command executed with no output)") {
      const formatted = ansiToHtml(output);
      appendTermHtml(formatted, data.is_error ? "error" : "stdout");
    }

    // Refresh file tree if command modified files
    const mutatingCmds = /\b(touch|mkdir|rm|mv|cp|git|pip|npm|yarn|make|cargo|go\s+build|gcc|g\+\+|rustc|python|node|chmod|chown|wget|curl\s+-o|tar|unzip|zip)\b/;
    if (mutatingCmds.test(cmd)) {
      await loadFiles();
    }
  } catch (err) {
    appendTermLine("Connection error: " + err.message, "error");
  } finally {
    termIsRunning = false;
    if (activeLine) activeLine.style.display = "flex";
    inputEl.value = "";
    focusTerminal();
    scrollTerminalToBottom();
  }
}

function appendTermLine(text, cls) {
  const container = document.getElementById("term-history-lines") || document.getElementById("terminal-output");
  const div = document.createElement("div");
  div.className = "terminal-line" + (cls ? " " + cls : "");
  div.textContent = text;
  container.appendChild(div);
  scrollTerminalToBottom();
}

function appendTermHtml(html, cls) {
  const container = document.getElementById("term-history-lines") || document.getElementById("terminal-output");
  const div = document.createElement("div");
  div.className = "terminal-line" + (cls ? " " + cls : "");
  div.innerHTML = html;
  container.appendChild(div);
  scrollTerminalToBottom();
}

function scrollTerminalToBottom() {
  const out = document.getElementById("terminal-output");
  if (out) out.scrollTop = out.scrollHeight;
}

function runActiveFileInTerminal(e) {
  if (e) e.stopPropagation();
  if (!activeFile) { appendTermLine("No file is open. Open a file in explorer first.", "error"); return; }
  const ext = activeFile.split(".").pop().toLowerCase();
  const runners = {
    py: "python3", js: "node", ts: "npx ts-node", sh: "bash",
    go: "go run", rs: "rustc %f -o /tmp/rs_out && /tmp/rs_out",
    c: "gcc %f -o /tmp/c_out && /tmp/c_out", cpp: "g++ %f -o /tmp/cpp_out && /tmp/cpp_out"
  };
  let cmd = runners[ext] ? runners[ext] + " " + activeFile : "cat " + activeFile;
  if (cmd.includes("%f")) cmd = cmd.replace(/%f/g, activeFile);
  executeTerminalCommand(cmd);
}

// --- Core: Real-Time Streaming with STRICT code/chat separation ---
async function sendMessage() {
  if (isSending) return;
  const input = document.getElementById("chat-input");
  const msg = input.value.trim();
  if (!msg) return;
  input.value = "";
  appendChatMsg("user", msg);
  isSending = true;
  resetOrchStages();
  const btn = document.querySelector(".chat-controls .btn-vscode");
  if (btn) { btn.innerText = "Working..."; btn.disabled = true; }

  // Build live streaming container
  const history = document.getElementById("chat-history");
  const msgDiv = document.createElement("div");
  msgDiv.className = "chat-msg assistant";
  msgDiv.innerHTML = `<div class="chat-msg-header">AGENT ZERO</div>
    <details class="thinking-box" open style="display:none">
      <summary class="thinking-toggle">Thinking</summary>
      <div class="thinking-content"></div>
    </details>
    <div class="stream-content" style="white-space:pre-wrap"></div>`;
  history.appendChild(msgDiv);
  history.scrollTop = history.scrollHeight;
  const thinkBox = msgDiv.querySelector(".thinking-box");
  const thinkEl = msgDiv.querySelector(".thinking-content");
  const chatEl = msgDiv.querySelector(".stream-content");

  let thinkBuf = "", contentBuf = "";
  let targetFile = activeFile || "solution.py";
  let editorStarted = false;
  const statusEl = document.getElementById("statusbar-engine-status");
  if (statusEl) statusEl.textContent = "Agent Working...";
  chatEl.textContent = "Connecting to agent...";

  if (!sessionId) {
    sessionId = "session-" + Math.random().toString(36).substring(2, 9);
  }

  try {
    const resp = await fetch("/api/chat/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: msg, active_file: activeFile, model_mode: selectedModelMode })
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;
        let ev;
        try { ev = JSON.parse(raw); } catch { continue; }

        if (ev.type === "orch_stage") {
          updateOrchStage(ev.stage, ev.label);
        } else if (ev.type === "init" && ev.target_file) {
          targetFile = ev.target_file;
        } else if (ev.type === "plan" && ev.plan) {
          currentPlan = ev.plan;
          renderPlanStepper(currentPlan);
          if (chatEl.textContent === "Connecting to agent...") {
            chatEl.textContent = "Planning dynamic subtasks...";
          }
        } else if (ev.type === "metrics" || (ev.type === "done" && ev.total_tokens !== undefined)) {
          document.getElementById("metric-tokens").innerText = ev.total_tokens;
          document.getElementById("metric-cost").innerText = "$" + (ev.total_cost_usd || 0).toFixed(4);
        } else if (ev.type === "thinking_chunk") {
          thinkBuf += ev.chunk;
          thinkBox.style.display = "block";
          thinkBox.open = true;
          if (chatEl.textContent === "Connecting to agent..." || chatEl.textContent === "Planning dynamic subtasks...") {
            chatEl.textContent = "";
          }
          // Strip meta preamble (e.g., "Here's a thinking process:") and code artifacts
          const cleanThink = thinkBuf
            .replace(/^(?:Here's\s+(?:a\s+)?thinking\s+process:?|Here\s+is\s+(?:the\s+)?thinking\s+process:?|Thinking\s+Process:?)\s*/i, "")
            .replace(/```[\s\S]*?```/g, "")
            .replace(/```/g, "")
            .trimStart();
          thinkEl.textContent = cleanThink;
          if (statusEl) statusEl.textContent = "Thinking...";
        } else if (ev.type === "target_file") {
          targetFile = ev.target_file;
          if (document.getElementById("active-tab-title")) {
            document.getElementById("active-tab-title").innerText = targetFile;
          }
        } else if (ev.type === "code_chunk") {
          // Direct real-time high-performance streaming into Monaco Editor
          const target = ev.file || targetFile;
          if (!editorStarted) {
            editorStarted = true;
            activeFile = target;
            document.getElementById("active-tab-title").innerText = target;
            document.getElementById("breadcrumb-file").innerHTML = esc(target) + ' <span class="live-coding-badge">LIVE</span>';
            const lang = detectLanguage(target);
            document.getElementById("statusbar-file-type").innerText = lang.toUpperCase();
            if (statusEl) statusEl.textContent = `Writing ${target}...`;
            if (editor) {
              editor.setValue("");
              monaco.editor.setModelLanguage(editor.getModel(), lang);
            }
          }
          if (editor) {
            const model = editor.getModel();
            if (model) {
              const lastLine = model.getLineCount();
              const maxCol = model.getLineMaxColumn(lastLine);
              const range = new monaco.Range(lastLine, maxCol, lastLine, maxCol);
              
              // Only auto-scroll if user hasn't deliberately scrolled up to read earlier code
              const layout = editor.getLayoutInfo();
              const isEditorNearBottom = layout ? (editor.getScrollTop() + layout.height >= editor.getScrollHeight() - 80) : true;
              
              model.applyEdits([{ range: range, text: ev.chunk, forceMoveMarkers: true }]);
              
              if (isEditorNearBottom) {
                const newLastLine = model.getLineCount();
                editor.revealLine(newLastLine, monaco.editor.ScrollType.Smooth);
              }
            }
          }
        } else if (ev.type === "chat_chunk") {
          // Clean explanation update to chat
          const cleanChunk = (ev.chunk || "")
            .replace(/```[\s\S]*?```/g, "")
            .replace(/###\s*File:[^\n]*/g, "")
            .replace(/<[a-zA-Z\/][^>]*>/g, "")
            .trim();
          if (cleanChunk && cleanChunk !== chatEl.textContent) {
            chatEl.textContent = cleanChunk;
          }
          const isChatNearBottom = history.scrollHeight - history.scrollTop - history.clientHeight < 80;
          if (isChatNearBottom) history.scrollTop = history.scrollHeight;
        } else if (ev.type === "content_chunk") {
          contentBuf += ev.chunk;

          // Robust separation of code vs explanation for fallback
          const parsed = parseStreamResponse(contentBuf, targetFile);

          // 1. Update Chat: Text explanation only (never raw code)
          if (parsed.explanation) {
            chatEl.textContent = parsed.explanation;
          }

          // 2. Update Monaco Editor: Code only (if not already handled by code_chunk)
          if (parsed.code !== null && !editorStarted) {
            editorStarted = true;
            activeFile = targetFile;
            document.getElementById("active-tab-title").innerText = targetFile;
            document.getElementById("breadcrumb-file").innerHTML = esc(targetFile) + ' <span class="live-coding-badge">LIVE</span>';
            const lang = detectLanguage(targetFile);
            document.getElementById("statusbar-file-type").innerText = lang.toUpperCase();
            if (statusEl) statusEl.textContent = "Writing Code...";
            if (editor) {
              editor.setValue(parsed.code);
              monaco.editor.setModelLanguage(editor.getModel(), lang);
              const m = editor.getModel();
              const lc = m.getLineCount();
              editor.setPosition({ lineNumber: lc, column: m.getLineMaxColumn(lc) });
              editor.revealLine(lc);
            }
          }
          const isChatNearBottom = history.scrollHeight - history.scrollTop - history.clientHeight < 80;
          if (isChatNearBottom) history.scrollTop = history.scrollHeight;
        } else if (ev.type === "done") {
          if (ev.saved_file) targetFile = ev.saved_file;
          document.getElementById("breadcrumb-file").textContent = targetFile;
          if (statusEl) statusEl.textContent = "Forge Engine: Active";
          await loadFiles();
          if (targetFile) await openFile(targetFile);
        } else if (ev.type === "error") {
          chatEl.textContent += "\n[Error]: " + ev.message;
        }
      }
    }
  } catch (err) {
    chatEl.textContent += "\n[Error]: " + err.message;
  } finally {
    isSending = false;
    if (btn) { btn.innerText = "Submit"; btn.disabled = false; }
    if (statusEl) statusEl.textContent = "Forge Engine: Active";
    document.getElementById("breadcrumb-file").textContent = activeFile || "select a file";
    await loadFiles();
  }
}

// --- Stream Parser Helper (Strict separation of code and explanation) ---
function parseStreamResponse(rawText, targetFile) {
  let code = null;
  let explanation = "";

  // 1. Check for markdown code fences
  const fenceMatch = rawText.match(/```(?:[a-zA-Z0-9_\-]+)?\n?([\s\S]*?)(?:```|$)/);
  if (fenceMatch) {
    code = fenceMatch[1];
    // Strip code blocks and file headers from explanation
    explanation = rawText
      .replace(/```[\s\S]*?```/g, "")
      .replace(/```[\s\S]*$/g, "")
      .replace(/###\s*File:[^\n]*/g, "")
      .trim();
  } else {
    // 2. Check if rawText contains source code (HTML, Python, JS, CSS, etc.)
    const trimmed = rawText.trim();
    const hasCodePattern = /^(?:<!DOCTYPE|<html|<head|<body|<style|<script|import\s+|from\s+|def\s+|class\s+|#include|const\s+|function\s+|let\s+|var\s+|public\s+class)/im.test(trimmed);
    const hasHtmlTags = /<\/?(?:div|section|p|h[1-6]|ul|ol|li|table|tr|td|span|footer|header|main|nav|a|img)[^>]*>/i.test(trimmed);

    if (hasCodePattern || (hasHtmlTags && (trimmed.includes("</") || trimmed.includes("<!")))) {
      code = rawText;
      const lines = rawText.split("\n");
      const textLines = [];
      for (const l of lines) {
        if (/^(?:<!|<[a-zA-Z]|import\s+|def\s+|class\s+|#include|const\s+|function\s+)/.test(l.trim())) break;
        textLines.push(l);
      }
      explanation = textLines.join("\n").trim();
    } else {
      explanation = trimmed;
    }
  }

  // Ensure explanation NEVER contains raw HTML tags, code fences, or file headers
  explanation = explanation
    .replace(/<[a-zA-Z\/][^>]*>/g, "")
    .replace(/###\s*File:[^\n]*/g, "")
    .replace(/```[^\n]*/g, "")
    .trim();

  if (!explanation && code !== null) {
    explanation = `Implementing ${targetFile} directly in Monaco Editor...`;
  }

  return { code, explanation };
}

// --- UI Helpers ---
function esc(s) {
  if (!s) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");
}

function appendChatMsg(role, text) {
  const history = document.getElementById("chat-history");
  const div = document.createElement("div");
  div.className = "chat-msg " + role;
  div.innerHTML = '<div class="chat-msg-header">' + (role === "user" ? "YOU" : "AGENT ZERO") + '</div><div style="white-space:pre-wrap">' + esc(text) + '</div>';
  history.appendChild(div);
  history.scrollTop = history.scrollHeight;
}

function renderPlanStepper(plan) {
  const container = document.getElementById("plan-stepper");
  if (!plan || !plan.length) { container.innerHTML = '<div style="color:var(--vscode-text-muted);font-size:11px">Agent graph idle.</div>'; return; }
  let h = "";
  plan.forEach(st => {
    const s = st.status || "pending";
    const isDone = s === "completed" || s === "done";
    const icon = isDone ? "[done]" : s === "in_progress" ? "[..]" : s === "failed" ? "[fail]" : "[--]";
    const cls = isDone ? "completed" : s === "in_progress" ? "running" : s === "failed" ? "failed" : "pending";
    h += `<div class="stepper-item ${cls}"><span class="stepper-icon">${icon}</span><div class="stepper-content"><div class="stepper-title">${st.subtask_id}. ${esc(st.description)}</div><div class="stepper-meta">Role: ${esc(st.assigned_role)} | Attempts: ${st.attempts_count || st.attempts?.length || 1}</div></div></div>`;
  });
  container.innerHTML = h;
}

async function loadSettings() {
  try {
    const r = await fetch("/api/settings");
    if (!r.ok) return;
    const d = await r.json();
    if (d.active_workspace) {
      const wsEl = document.getElementById("setting-workspace");
      if (wsEl) wsEl.value = d.active_workspace;
      const titleWs = document.getElementById("titlebar-ws-name");
      if (titleWs) titleWs.innerText = d.active_workspace.split("/").pop();
    }
    if (d.nvidia_base_url) {
      const buEl = document.getElementById("setting-base-url");
      if (buEl) buEl.value = d.nvidia_base_url;
    }
    if (d.roles) {
      if (d.roles.planner) {
        const pm = document.getElementById("setting-planner-model");
        const pk = document.getElementById("setting-planner-key");
        if (pm) pm.value = d.roles.planner.model || "";
        if (pk) pk.value = d.roles.planner.api_key || "";
      }
      if (d.roles.coder) {
        const cm = document.getElementById("setting-coder-model");
        const ck = document.getElementById("setting-coder-key");
        if (cm) cm.value = d.roles.coder.model || "";
        if (ck) ck.value = d.roles.coder.api_key || "";
      }
      if (d.roles.critic) {
        const rm = document.getElementById("setting-critic-model");
        const rk = document.getElementById("setting-critic-key");
        if (rm) rm.value = d.roles.critic.model || "";
        if (rk) rk.value = d.roles.critic.api_key || "";
      }
      if (d.roles.router) {
        const tm = document.getElementById("setting-router-model");
        const tk = document.getElementById("setting-router-key");
        if (tm) tm.value = d.roles.router.model || "";
        if (tk) tk.value = d.roles.router.api_key || "";
      }
    }
  } catch (err) {
    console.error("loadSettings error:", err);
  }
}

async function saveSettings() {
  const payload = {
    nvidia_base_url: document.getElementById("setting-base-url")?.value.trim(),
    active_workspace: document.getElementById("setting-workspace")?.value.trim(),
    planner: {
      model: document.getElementById("setting-planner-model")?.value.trim(),
      api_key: document.getElementById("setting-planner-key")?.value.trim(),
    },
    coder: {
      model: document.getElementById("setting-coder-model")?.value.trim(),
      api_key: document.getElementById("setting-coder-key")?.value.trim(),
    },
    critic: {
      model: document.getElementById("setting-critic-model")?.value.trim(),
      api_key: document.getElementById("setting-critic-key")?.value.trim(),
    },
    router: {
      model: document.getElementById("setting-router-model")?.value.trim(),
      api_key: document.getElementById("setting-router-key")?.value.trim(),
    },
  };

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      alert("Settings saved successfully!");
      await loadSettings();
      await loadFiles();
    } else {
      alert("Failed to save settings.");
    }
  } catch (err) {
    alert("Error saving settings: " + err.message);
  }
}

// --- Observability DAG & Telemetry View ---
async function loadDAGTelemetry() {
  const listEl = document.getElementById("dag-tree-list");
  const inspectorEl = document.getElementById("node-inspector-content");
  if (!listEl) return;

  try {
    const res = await fetch(`/api/dag/${encodeURIComponent(sessionId)}`);
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById("metric-tokens").innerText = data.total_tokens || 0;
    document.getElementById("metric-cost").innerText = "$" + (data.total_cost_usd || 0).toFixed(4);

    const nodes = data.nodes && data.nodes.length > 0 ? data.nodes : currentPlan || [];
    if (nodes.length === 0) {
      listEl.innerHTML = `
        <div class="telemetry-empty-state">
          <div style="font-weight:600;margin-bottom:6px;color:var(--vscode-text-bright);">No Active Orchestration DAG Trace</div>
          <div style="color:var(--vscode-text-muted);font-size:12px;">Submit a coding prompt in the IDE Chat to generate dynamic execution graphs, latency traces, and model audit records.</div>
        </div>`;
      inspectorEl.innerHTML = `<div style="color:var(--vscode-text-muted);font-size:12px;">Select a node above to inspect its thoughts and inputs/outputs.</div>`;
      return;
    }

    let html = `
      <div class="telemetry-summary-row">
        <div class="telemetry-stat-card">
          <div class="stat-label">Total Subtasks</div>
          <div class="stat-value">${nodes.length}</div>
        </div>
        <div class="telemetry-stat-card">
          <div class="stat-label">Total Tokens</div>
          <div class="stat-value">${data.total_tokens || 0}</div>
        </div>
        <div class="telemetry-stat-card">
          <div class="stat-label">Total Session Cost</div>
          <div class="stat-value">$${(data.total_cost_usd || 0).toFixed(4)}</div>
        </div>
        <div class="telemetry-stat-card">
          <div class="stat-label">Budget Safety Limit</div>
          <div class="stat-value">$0.5000</div>
        </div>
      </div>
      <div style="margin-top:14px;margin-bottom:8px;font-size:12px;font-weight:600;color:var(--vscode-text-bright);">Subtask Execution DAG:</div>
    `;

    nodes.forEach((node, idx) => {
      const isDone = node.status === "completed" || node.status === "done";
      const statusClass = isDone ? "completed" : node.status === "in_progress" ? "running" : "pending";
      const badgeText = isDone ? "[DONE]" : node.status === "in_progress" ? "[RUNNING]" : "[PENDING]";
      const roleColor = node.assigned_role === "coder" ? "#4ec9b0" : node.assigned_role === "critic" ? "#f38ba8" : "#9cdcfe";

      html += `
        <div class="dag-node-card ${statusClass}" onclick="inspectDAGNode(${idx})">
          <div class="dag-node-header">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="dag-status-badge ${statusClass}">${badgeText}</span>
              <span style="font-weight:600;color:var(--vscode-text-bright);">#${node.subtask_id}. ${esc(node.description)}</span>
            </div>
            <span style="font-size:11px;color:${roleColor};font-weight:700;text-transform:uppercase;">${esc(node.assigned_role)}</span>
          </div>
          <div class="dag-node-meta">
            <span>Target: ${esc((node.target_files || []).join(", ") || activeFile || "solution.py")}</span>
            <span>Attempts: ${node.attempts_count || (node.attempts || []).length || 1}</span>
            <span>Dependencies: ${esc((node.dependencies || []).join(", ") || "None")}</span>
          </div>
        </div>
      `;
    });

    listEl.innerHTML = html;
    window._currentDAGNodes = nodes;
    if (nodes.length > 0) inspectDAGNode(0);
  } catch (err) {
    console.error("loadDAGTelemetry error:", err);
  }
}

function inspectDAGNode(idx) {
  const nodes = window._currentDAGNodes || currentPlan || [];
  const node = nodes[idx];
  if (!node) return;

  const inspectorEl = document.getElementById("node-inspector-content");
  if (!inspectorEl) return;

  const attempts = node.attempts || [];
  let attemptsHtml = "";
  if (attempts.length > 0) {
    attempts.forEach((att, aIdx) => {
      const verdict = att.critic_verdict || {};
      attemptsHtml += `
        <div class="attempt-card">
          <div style="font-weight:600;font-size:12px;color:var(--vscode-text-bright);margin-bottom:4px;">
            Attempt ${aIdx + 1}: ${verdict.passed ? '<span style="color:#a6e3a1;">Passed</span>' : '<span style="color:#f38ba8;">Failed</span>'}
            <span style="float:right;font-size:11px;color:var(--vscode-text-muted);">Latency: ${(att.latency || 0).toFixed(2)}s | Cost: $${(att.cost || 0).toFixed(5)}</span>
          </div>
          <div style="font-size:11px;color:var(--vscode-text);margin-bottom:6px;"><strong>Action:</strong> ${esc(att.action || "")}</div>
          <div style="font-size:11px;color:var(--vscode-text-muted);"><strong>Critic Audit:</strong> ${esc(verdict.reason || "Verified clean syntax and behavior.")}</div>
        </div>
      `;
    });
  } else {
    attemptsHtml = `<div style="font-size:11px;color:var(--vscode-text-muted);padding:4px 0;">No attempt logs recorded for this node yet.</div>`;
  }

  inspectorEl.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;border-bottom:1px solid #3c3c3c;padding-bottom:8px;">
      <div>
        <strong style="font-size:13px;color:var(--vscode-text-bright);">Subtask #${node.subtask_id}: ${esc(node.description)}</strong>
        <div style="font-size:11px;color:var(--vscode-text-muted);margin-top:2px;">Role: <span style="color:#4ec9b0;font-weight:600;">${esc(node.assigned_role)}</span> | Status: <strong>${esc(node.status)}</strong></div>
      </div>
      <span class="dag-status-badge ${node.status === "completed" || node.status === "done" ? "completed" : "running"}">${esc(node.status).toUpperCase()}</span>
    </div>
    <div style="margin-bottom:12px;">
      <div style="font-size:11px;font-weight:600;color:var(--vscode-text-bright);margin-bottom:4px;">Target Files & Scope:</div>
      <div style="font-size:11px;font-family:var(--font-mono);background:#1e1e1e;padding:6px 8px;border-radius:4px;border:1px solid #333;color:#89b4fa;">
        ${esc((node.target_files || []).join(", ") || activeFile || "solution.py")}
      </div>
    </div>
    <div>
      <div style="font-size:11px;font-weight:600;color:var(--vscode-text-bright);margin-bottom:6px;">Multi-Agent Verification & Attempt Trace:</div>
      ${attemptsHtml}
    </div>
  `;
}

// --- Source Control & Diff Review View ---
async function loadDiffReview() {
  const container = document.getElementById("diff-hunk-container");
  if (!container) return;
  try {
    const res = await fetch("/api/git/status");
    if (!res.ok) return;
    const data = await res.json();
    if (!data.diff && (!data.untracked || data.untracked.length === 0)) {
      container.innerHTML = `<div style="color:var(--vscode-text-muted);font-size:12px;">Working directory clean. No uncommitted diffs or pending modifications.</div>`;
      return;
    }
    let html = "";
    if (data.untracked && data.untracked.length > 0) {
      html += `<div style="font-size:12px;font-weight:600;color:#89b4fa;margin-bottom:8px;">Untracked Files (${data.untracked.length}):</div>`;
      data.untracked.forEach(uf => {
        html += `<div style="font-family:var(--font-mono);font-size:11px;padding:4px 8px;background:#1e1e1e;margin-bottom:4px;border-radius:3px;color:#a6e3a1;">+ ${esc(uf)}</div>`;
      });
    }
    if (data.diff) {
      html += `<div style="font-size:12px;font-weight:600;color:#4ec9b0;margin-top:12px;margin-bottom:8px;">Active Git Diff:</div>`;
      html += `<pre style="font-family:var(--font-mono);font-size:11px;background:#1e1e1e;padding:10px;border-radius:4px;border:1px solid #3c3c3c;overflow-x:auto;max-height:350px;color:#cccccc;">${esc(data.diff)}</pre>`;
    }
    container.innerHTML = html;
  } catch (err) {
    console.error("loadDiffReview error:", err);
  }
}

window.onload = init;
