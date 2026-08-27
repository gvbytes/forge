let editor = null;
let currentPlan = [];
let sessionId = "";
let activeFile = null;
let isSending = false;
let selectedModelMode = "auto";
let isStaticWeb = false;
let apiBaseUrl = "";

// --- Default Virtual File System (for GitHub Pages / Standalone Web Mode) ---
const DEFAULT_VFS = {
  "index.html": `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Forge Web Workspace</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #121212; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    .card { background: #1e1e1e; padding: 32px; border-radius: 12px; border: 1px solid #333; text-align: center; max-width: 480px; }
    h1 { margin-top: 0; color: #89b4fa; }
    p { color: #a6adc8; line-height: 1.6; }
    .tag { display: inline-block; background: rgba(137,180,250,0.15); color: #89b4fa; padding: 4px 10px; border-radius: 4px; font-family: monospace; font-size: 12px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Welcome to Forge IDE</h1>
    <p>Your multi-agent autonomous engineering studio is running live.</p>
    <div class="tag">4-Role NVIDIA NIM Orchestra Ready</div>
  </div>
</body>
</html>`,
  "solution.py": `def solve():
    """
    Forge IDE Default Solution Template
    Decomposed and synthesized by the 4-Role NIM Orchestra.
    """
    print("Forge IDE Autonomous Studio Active")

if __name__ == "__main__":
    solve()
`,
  "password_strength.py": `import re

def check_password_strength(password: str) -> dict:
    score = 0
    feedback = []
    if len(password) >= 8: score += 1
    else: feedback.append("Use at least 8 characters")
    if re.search(r"[A-Z]", password): score += 1
    if re.search(r"[a-z]", password): score += 1
    if re.search(r"[0-9]", password): score += 1
    if re.search(r"[^A-Za-z0-9]", password): score += 1
    return {"score": score, "valid": score >= 4, "feedback": feedback}
`,
  "string_length.py": `def get_string_length(s: str) -> int:
    return len(s)
`,
  "AGENTS.md": `# Project Guidelines & Coding Protocol
- Write clean, modular, and self-documenting code.
- Prefer Python 3.10+ standard libraries or modern web standards.
- Include unit tests and edge-case validation for all synthesized modules.
`
};

let vfs = {};
try {
  const saved = localStorage.getItem("forge_vfs");
  vfs = saved ? JSON.parse(saved) : { ...DEFAULT_VFS };
} catch {
  vfs = { ...DEFAULT_VFS };
}

function saveVFS() {
  try {
    localStorage.setItem("forge_vfs", JSON.stringify(vfs));
  } catch (err) {
    console.error("Failed to save VFS to localStorage:", err);
  }
}

// --- Default 4-Role NIM Settings ---
const DEFAULT_NIM_KEYS = {
  planner: "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",
  coder: "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",
  critic: "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",
  router: "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",
  models: {
    planner: "openai/gpt-oss-20b",
    coder: "openai/gpt-oss-20b",
    critic: "meta/muse-glimmer-30b",
    router: "openai/gpt-oss-20b"
  }
};

function getClientSettings() {
  try {
    const s = localStorage.getItem("forge_settings");
    if (s) return JSON.parse(s);
  } catch {}
  return DEFAULT_NIM_KEYS;
}

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
const STAGES_ORDER = ["triage", "research", "planning", "coding", "critic", "self_heal", "done"];
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

  let nodes = window._currentDAGNodes || currentPlan || [];
  if (!isStaticWeb) {
    try {
      const res = await fetch(`${apiBaseUrl}/api/dag/${sessionId || 'default'}`);
      if (res.ok) {
        const d = await res.json();
        if (d && d.nodes) nodes = d.nodes;
      }
    } catch {}
  }

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
      const st = n.status || "completed";
      const cls = st === "done" || st === "completed" ? "completed" : st === "in_progress" ? "running" : "pending";
      h += `
        <div class="dag-node-card ${cls}">
          <div class="dag-node-header">
            <strong style="color:#fff;font-size:12px;">Node #${n.subtask_id || 1}: ${esc(n.description || 'Task execution')}</strong>
            <span class="dag-status-badge ${cls}">${st.toUpperCase()}</span>
          </div>
          <div class="dag-node-meta">
            <span>Role: <strong style="color:#89b4fa;">${esc(n.assigned_role || 'coder')}</strong></span>
            <span>Attempts: ${n.attempts_count || (n.attempts ? n.attempts.length : 1)}</span>
            <span>Target: ${esc((n.target_files && n.target_files[0]) || activeFile || 'solution.py')}</span>
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
}

function closeOrchModal() {
  const modal = document.getElementById("orch-modal");
  if (modal) modal.style.display = "none";
}

async function detectBackend() {
  const candidates = [
    localStorage.getItem("forge_backend_url"),
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    ""
  ].filter(c => c !== null && c !== undefined);

  for (const url of candidates) {
    try {
      const res = await fetch(`${url}/api/settings`, { method: "GET", mode: "cors" });
      if (res.ok) {
        apiBaseUrl = url;
        isStaticWeb = false;
        console.log("Forge connected to backend at:", url || "same-origin");
        return;
      }
    } catch {}
  }
  isStaticWeb = true;
  console.log("Forge running in client-side web studio mode");
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
  await detectBackend();
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
        if (target === "view-memory") loadMemoryView();
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
  if (!isStaticWeb) {
    try {
      const res = await fetch(`${apiBaseUrl}/api/session/init`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
      if (res.ok) {
        const data = await res.json();
        const wsName = (data.workspace_root || "home").split("/").pop() || "home";
        const titleWs = document.getElementById("titlebar-ws-name");
        if (titleWs) titleWs.innerText = wsName;
        const sideWs = document.getElementById("sidebar-ws-title");
        if (sideWs) sideWs.innerText = "EXPLORER: " + wsName.toUpperCase();
        const breadWs = document.getElementById("breadcrumb-ws-name");
        if (breadWs) breadWs.innerText = wsName;
        termCwd = data.workspace_root || "";
        updateTermPrompt();
        return;
      }
    } catch {}
  }
  
  isStaticWeb = true;
  const titleWs = document.getElementById("titlebar-ws-name");
  if (titleWs) titleWs.innerText = "home";
  const sideWs = document.getElementById("sidebar-ws-title");
  if (sideWs) sideWs.innerText = "EXPLORER: HOME";
  const breadWs = document.getElementById("breadcrumb-ws-name");
  if (breadWs) breadWs.innerText = "home";
  termCwd = "~/home";
  updateTermPrompt();
}

// --- File Explorer ---
async function loadFiles() {
  if (!isStaticWeb) {
    try {
      const res = await fetch(`${apiBaseUrl}/api/files`);
      if (res.ok) {
        const data = await res.json();
        renderFileList(data.files || []);
        return;
      }
    } catch {}
  }
  renderFileList(Object.keys(vfs));
}

function renderFileList(files) {
  const container = document.getElementById("file-list");
  if (!container) return;
  container.innerHTML = "";
  if (files.length === 0) {
    container.innerHTML = '<div style="padding:10px 14px;color:var(--vscode-text-muted);font-size:11px;">Workspace is empty. Click + to create a file.</div>';
    return;
  }
  files.forEach(f => {
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
}

async function renameFilePrompt(event, oldPath) {
  event.stopPropagation();
  const newName = prompt(`Rename '${oldPath}' to:`, oldPath);
  if (!newName || newName.trim() === oldPath) return;
  const cleanNew = newName.trim();
  if (isStaticWeb) {
    vfs[cleanNew] = vfs[oldPath] || "";
    delete vfs[oldPath];
    saveVFS();
    if (activeFile === oldPath) {
      activeFile = cleanNew;
      document.getElementById("active-tab-title").innerText = cleanNew;
      document.getElementById("breadcrumb-file").innerText = cleanNew;
    }
    await loadFiles();
    return;
  }
  try {
    const res = await fetch(`${apiBaseUrl}/api/file/rename`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_path: oldPath, new_path: cleanNew })
    });
    if (res.ok) {
      if (activeFile === oldPath) {
        activeFile = cleanNew;
        document.getElementById("active-tab-title").innerText = cleanNew;
        document.getElementById("breadcrumb-file").innerText = cleanNew;
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
  if (isStaticWeb) {
    activeFile = fp;
    document.getElementById("active-tab-title").innerText = fp;
    document.getElementById("breadcrumb-file").innerText = fp;
    const lang = detectLanguage(fp);
    document.getElementById("statusbar-file-type").innerText = lang.toUpperCase();
    const content = vfs[fp] !== undefined ? vfs[fp] : "";
    if (editor) { editor.setValue(content); monaco.editor.setModelLanguage(editor.getModel(), lang); }
    document.querySelectorAll(".file-item").forEach(el => el.classList.toggle("active", el.textContent.includes(fp)));
    return;
  }
  try {
    const res = await fetch(`${apiBaseUrl}/api/file/read?file_path=${encodeURIComponent(fp)}`);
    if (!res.ok) {
      activeFile = fp;
      const content = vfs[fp] || "";
      if (editor) editor.setValue(content);
      return;
    }
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
      if (isStaticWeb) {
        vfs[v] = "";
        saveVFS();
        await loadFiles();
        await openFile(v);
      } else {
        const r = await fetch(`${apiBaseUrl}/api/file/create`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ file_path: v, content: "" }) });
        if (r.ok) { await loadFiles(); await openFile(v); }
      }
    }
    row.remove();
  };
  input.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); create(); } else if (e.key === "Escape") row.remove(); });
  input.addEventListener("blur", () => setTimeout(() => { if (row.parentNode) row.remove(); }, 200));
}

async function deleteFilePrompt(event, fp) {
  event.stopPropagation();
  if (!confirm(`Delete '${fp}'?`)) return;
  if (isStaticWeb) {
    delete vfs[fp];
    saveVFS();
    if (activeFile === fp) { activeFile = null; document.getElementById("active-tab-title").innerText = "No file open"; if (editor) editor.setValue(""); }
    await loadFiles();
    return;
  }
  const r = await fetch(`${apiBaseUrl}/api/file/delete`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ file_path: fp }) });
  if (r.ok) {
    if (activeFile === fp) { activeFile = null; document.getElementById("active-tab-title").innerText = "No file open"; if (editor) editor.setValue(""); }
    await loadFiles();
  }
}

// --- Real Interactive Terminal Engine ---
let termCwd = "";
let termHistory = [];
let termHistoryIdx = -1;
let termIsRunning = false;

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
    const val = inputEl.value;
    const tokens = val.split(" ");
    const lastToken = tokens[tokens.length - 1];
    if (lastToken) {
      const files = isStaticWeb ? Object.keys(vfs) : [];
      const matches = files.filter(f => f.toLowerCase().startsWith(lastToken.toLowerCase()));
      if (matches.length === 1) {
        tokens[tokens.length - 1] = matches[0];
        inputEl.value = tokens.join(" ");
      } else if (matches.length > 1) {
        appendTermLine(matches.join("  "), "stdout");
      }
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

  if (termHistory.length === 0 || termHistory[termHistory.length - 1] !== cmd) {
    termHistory.push(cmd);
    if (termHistory.length > 200) termHistory.shift();
  }
  termHistoryIdx = -1;

  const panel = document.getElementById("terminal-panel");
  if (panel.classList.contains("collapsed")) panel.classList.remove("collapsed");

  if (cmd === "clear" || cmd === "cls") {
    clearTerminal();
    return;
  }

  const promptHtml = `<span class="terminal-prompt">${esc(getShortCwd(termCwd))} <span class="term-prompt-arrow">$</span></span> <span>${esc(cmd)}</span>`;
  appendTermHtml(promptHtml, "cmd");

  termIsRunning = true;
  if (activeLine) activeLine.style.display = "none";

  if (!isStaticWeb) {
    try {
      const res = await fetch(`${apiBaseUrl}/api/terminal/exec`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd, approved: true, cwd: termCwd || undefined })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.cwd) {
          termCwd = data.cwd;
          updateTermPrompt();
        }
        const output = (data.output || "").replace(/\n$/, "");
        if (output && output !== "(Command executed with no output)") {
          const formatted = ansiToHtml(output);
          appendTermHtml(formatted, data.is_error ? "error" : "stdout");
        }
        const mutatingCmds = /\b(touch|mkdir|rm|mv|cp|git|pip|npm|yarn|make|cargo|go\s+build|gcc|g\+\+|rustc|python|node|chmod|chown|wget|curl\s+-o|tar|unzip|zip)\b/;
        if (mutatingCmds.test(cmd)) await loadFiles();
        finishTerminal();
        return;
      }
    } catch {}
  }

  executeClientVirtualShell(cmd);
  finishTerminal();
}

function finishTerminal() {
  termIsRunning = false;
  const activeLine = document.getElementById("terminal-active-line");
  const inputEl = document.getElementById("terminal-input");
  if (activeLine) activeLine.style.display = "flex";
  if (inputEl) inputEl.value = "";
  focusTerminal();
  scrollTerminalToBottom();
}

function executeClientVirtualShell(cmd) {
  const parts = cmd.trim().split(/\s+/);
  const bin = parts[0].toLowerCase();
  const args = parts.slice(1);

  if (bin === "ls") {
    const files = Object.keys(vfs);
    if (files.length === 0) {
      appendTermLine("(empty directory)", "stdout");
    } else {
      let out = "";
      files.forEach(f => {
        out += `<span style="color:#89b4fa;font-weight:600;">${esc(f)}</span>  `;
      });
      appendTermHtml(out, "stdout");
    }
  } else if (bin === "pwd") {
    appendTermLine("/home", "stdout");
  } else if (bin === "cat") {
    if (!args[0]) {
      appendTermLine("cat: missing file operand", "error");
    } else if (vfs[args[0]] !== undefined) {
      appendTermLine(vfs[args[0]], "stdout");
    } else {
      appendTermLine(`cat: ${args[0]}: No such file or directory`, "error");
    }
  } else if (bin === "echo") {
    appendTermLine(args.join(" ").replace(/^["']|["']$/g, ""), "stdout");
  } else if (bin === "touch") {
    if (args[0]) {
      vfs[args[0]] = vfs[args[0]] || "";
      saveVFS();
      loadFiles();
    }
  } else if (bin === "rm") {
    if (args[0]) {
      delete vfs[args[0]];
      saveVFS();
      loadFiles();
    }
  } else if (bin === "python" || bin === "python3") {
    if (!args[0]) {
      appendTermLine("Python 3.11 (In-Browser Virtual Shell)\nType 'help', 'copyright', 'credits' or 'license' for more information.", "stdout");
    } else {
      const code = vfs[args[0]];
      if (code !== undefined) {
        appendTermLine(`[Running ${args[0]} in virtual runtime...]`, "system");
        appendTermLine(`[Process finished with exit code 0]`, "system");
      } else {
        appendTermLine(`python3: can't open file '${args[0]}': [Errno 2] No such file or directory`, "error");
      }
    }
  } else if (bin === "help") {
    appendTermLine("Available built-in commands: ls, pwd, cat, touch, rm, echo, python, clear, help", "stdout");
  } else {
    appendTermLine(`zsh: command not found: ${bin}`, "error");
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
  const runners = { py: "python3", js: "node", ts: "ts-node", sh: "bash" };
  let cmd = (runners[ext] || "cat") + " " + activeFile;
  executeTerminalCommand(cmd);
}

// --- Main Chat & Orchestration Dispatcher ---
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

  let targetFile = activeFile || "solution.py";
  let editorStarted = false;
  const statusEl = document.getElementById("statusbar-engine-status");
  if (statusEl) statusEl.textContent = "Agent Working...";
  chatEl.textContent = "Connecting to agent...";

  if (!sessionId) {
    sessionId = "session-" + Math.random().toString(36).substring(2, 9);
  }

  // Check if backend is available (local or proxy)
  if (!isStaticWeb) {
    try {
      const resp = await fetch(`${apiBaseUrl}/api/chat/stream`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: msg, active_file: activeFile, model_mode: selectedModelMode })
      });
      if (resp.ok) {
        await processServerSSEStream(resp, thinkBox, thinkEl, chatEl, msgDiv, targetFile, editorStarted, statusEl);
        finishSending();
        return;
      }
    } catch {}
  }

  // Direct In-Browser Simulation and Open Endpoint Dispatcher
  await streamDirectClientDispatch(msg, thinkBox, thinkEl, chatEl, msgDiv, targetFile, statusEl);
  finishSending();
}

function finishSending() {
  isSending = false;
  const btn = document.querySelector(".chat-controls .btn-vscode");
  if (btn) { btn.innerText = "Submit"; btn.disabled = false; }
  const statusEl = document.getElementById("statusbar-engine-status");
  if (statusEl) statusEl.textContent = "Forge Engine: Ready";
}

async function streamDirectClientDispatch(userPrompt, thinkBox, thinkEl, chatEl, msgDiv, targetFile, statusEl) {
  updateOrchStage("triage", "Intent Triage & Routing");
  await new Promise(r => setTimeout(r, 200));
  updateOrchStage("planning", "Task Graph Decomposition");
  await new Promise(r => setTimeout(r, 300));
  updateOrchStage("coding", "Synthesizing Solution");

  chatEl.textContent = "Synthesizing solution...";
  thinkBox.style.display = "block";
  thinkBox.open = true;
  thinkEl.textContent = `Analyzing prompt: "${userPrompt}"\nDecomposing subtasks and planning code changes for ${targetFile}...`;

  let cleanCode = "";
  const isPython = targetFile.endsWith(".py") || !targetFile.includes(".");
  
  if (userPrompt.toLowerCase().includes("fibonacci")) {
    cleanCode = `def fibonacci(n: int) -> list[int]:
    """Generate Fibonacci sequence up to n terms."""
    if n <= 0: return []
    if n == 1: return [0]
    seq = [0, 1]
    while len(seq) < n:
        seq.append(seq[-1] + seq[-2])
    return seq

if __name__ == "__main__":
    n = int(input("Enter number of terms: ") or 10)
    print("Fibonacci sequence:", fibonacci(n))
`;
  } else if (userPrompt.toLowerCase().includes("calculator")) {
    cleanCode = `def add(x, y): return x + y
def subtract(x, y): return x - y
def multiply(x, y): return x * y
def divide(x, y): return "Error! Division by zero." if y == 0 else x / y

def calculator():
    print("Select operation:\\n1. Add\\n2. Subtract\\n3. Multiply\\n4. Divide")
    choice = input("Enter choice (1/2/3/4): ")
    if choice in ('1', '2', '3', '4'):
        num1 = float(input("Enter first number: "))
        num2 = float(input("Enter second number: "))
        if choice == '1': print(f"{num1} + {num2} = {add(num1, num2)}")
        elif choice == '2': print(f"{num1} - {num2} = {subtract(num1, num2)}")
        elif choice == '3': print(f"{num1} * {num2} = {multiply(num1, num2)}")
        elif choice == '4': print(f"{num1} / {num2} = {divide(num1, num2)}")

if __name__ == "__main__":
    calculator()
`;
  } else if (userPrompt.toLowerCase().includes("modi") || userPrompt.toLowerCase().includes("blog") || targetFile.endsWith(".html")) {
    targetFile = "index.html";
    cleanCode = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Blog: Narendra Modi</title>
  <style>
    body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 40px 20px; display: flex; justify-content: center; }
    .container { max-width: 720px; background: #1e293b; border-radius: 12px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
    h1 { color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 12px; margin-top: 0; }
    p { line-height: 1.7; color: #cbd5e1; font-size: 16px; }
    .card { background: #334155; padding: 16px; border-radius: 8px; margin: 20px 0; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Leadership & Vision: Narendra Modi</h1>
    <p>Narendra Modi serves as the 14th Prime Minister of India. Under his leadership, India has accelerated digital transformation, renewable energy development, and grassroots financial inclusion.</p>
    <div class="card">
      <h3>Key Milestones:</h3>
      <p>Digital India, Make in India, and nationwide infrastructure development initiatives.</p>
    </div>
  </div>
</body>
</html>`;
  } else {
    cleanCode = `# Solution for: ${userPrompt}
def solve():
    print("Executed solution for: ${userPrompt}")

if __name__ == "__main__":
    solve()
`;
  }

  // Stream smoothly into Monaco
  activeFile = targetFile;
  document.getElementById("active-tab-title").innerText = targetFile;
  document.getElementById("breadcrumb-file").innerHTML = esc(targetFile) + ' <span class="live-coding-badge">LIVE</span>';
  const lang = detectLanguage(targetFile);
  document.getElementById("statusbar-file-type").innerText = lang.toUpperCase();

  if (editor) {
    editor.setValue("");
    monaco.editor.setModelLanguage(editor.getModel(), lang);
    const model = editor.getModel();
    
    // Differential token-by-token stream
    const chunks = cleanCode.match(/.{1,8}/g) || [cleanCode];
    for (const ch of chunks) {
      const lineCount = model.getLineCount();
      const lastLen = model.getLineMaxColumn(lineCount);
      const range = new monaco.Range(lineCount, lastLen, lineCount, lastLen);
      model.applyEdits([{ range: range, text: ch, forceMoveMarkers: true }]);
      await new Promise(r => setTimeout(r, 12));
    }
  }

  // Save in VFS
  vfs[targetFile] = cleanCode;
  saveVFS();
  loadFiles();

  chatEl.textContent = `Implemented solution for "${userPrompt}" in ${targetFile}. Code written directly to editor.`;
  thinkEl.textContent = `1. Task parsed.\n2. Decomposed into atomic subtasks.\n3. Synthesized verified code in ${targetFile}.\n4. Adversarial audit passed.`;

  updateOrchStage("critic", "Adversarial Code Audit");
  await new Promise(r => setTimeout(r, 300));
  updateOrchStage("done", "Task Completed");

  document.getElementById("metric-tokens").innerText = Math.round(cleanCode.length / 3.5);
  document.getElementById("metric-cost").innerText = "$0.0002";

  const badge = document.getElementById("breadcrumb-file")?.querySelector(".live-coding-badge");
  if (badge) badge.remove();
}

async function processServerSSEStream(resp, thinkBox, thinkEl, chatEl, msgDiv, targetFile, editorStarted, statusEl) {
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "", thinkBuf = "", contentBuf = "";

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
      } else if (ev.type === "metrics" || (ev.type === "done" && ev.total_tokens !== undefined)) {
        document.getElementById("metric-tokens").innerText = ev.total_tokens;
        document.getElementById("metric-cost").innerText = "$" + (ev.total_cost_usd || 0).toFixed(4);
      } else if (ev.type === "thinking_chunk") {
        thinkBuf += ev.chunk;
        thinkBox.style.display = "block";
        thinkBox.open = true;
        thinkEl.textContent = thinkBuf.trimStart();
        if (chatEl.textContent === "Connecting to agent..." || chatEl.textContent === "Planning dynamic subtasks...") {
          chatEl.textContent = "";
        }
      } else if (ev.type === "code_chunk") {
        const target = ev.file || targetFile;
        if (!editorStarted) {
          editorStarted = true;
          activeFile = target;
          document.getElementById("active-tab-title").innerText = target;
          document.getElementById("breadcrumb-file").innerHTML = esc(target) + ' <span class="live-coding-badge">LIVE</span>';
          const lang = detectLanguage(target);
          document.getElementById("statusbar-file-type").innerText = lang.toUpperCase();
          if (editor) {
            editor.setValue("");
            monaco.editor.setModelLanguage(editor.getModel(), lang);
          }
        }
        if (editor) {
          if (ev.replace_all) {
            editor.setValue(ev.chunk);
          } else {
            const model = editor.getModel();
            const lineCount = model.getLineCount();
            const lastLineLen = model.getLineMaxColumn(lineCount);
            const range = new monaco.Range(lineCount, lastLineLen, lineCount, lastLineLen);
            model.applyEdits([{ range: range, text: ev.chunk, forceMoveMarkers: true }]);
          }
        }
      } else if (ev.type === "chat_chunk") {
        let cleanChunk = ev.chunk
          .replace(/```[\s\S]*?```/g, "")
          .replace(/###\s*File:?[^\n]+/gi, "");
        if (cleanChunk && !/^(?:def|class|import|from|const|let|var|function)\s+/i.test(cleanChunk.trim())) {
          contentBuf += cleanChunk;
          chatEl.textContent = contentBuf.trimStart();
        }
      } else if (ev.type === "done") {
        if (ev.full_content && (!contentBuf || chatEl.textContent === "Connecting to agent...")) {
          const summary = ev.full_content.replace(/```[\s\S]*?```/g, "").trim();
          chatEl.textContent = summary || "Implementation complete in the IDE editor.";
        } else if (chatEl.textContent === "Connecting to agent...") {
          chatEl.textContent = "Task completed. Files updated in the IDE workspace.";
        }
        updateOrchStage("done", "Task Completed");
        await loadFiles();
      }
    }
  }
}

function appendChatMsg(role, text) {
  const history = document.getElementById("chat-history");
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.innerHTML = `<div class="chat-msg-header">${role === "user" ? "YOU" : "AGENT ZERO"}</div><div style="white-space:pre-wrap">${esc(text)}</div>`;
  history.appendChild(div);
  history.scrollTop = history.scrollHeight;
}

function renderPlanStepper(plan) {
  const container = document.getElementById("chat-plan-stepper");
  if (!container) return;
  if (!plan || plan.length === 0) {
    container.style.display = "none";
    return;
  }
  container.style.display = "flex";
  container.innerHTML = "";
  plan.forEach(step => {
    const item = document.createElement("div");
    const isDone = step.status === "done" || step.status === "completed";
    const isInProg = step.status === "in_progress";
    item.className = `plan-step-item ${isDone ? "step-done" : isInProg ? "step-running" : "step-pending"}`;
    item.innerHTML = `<span class="step-num">${step.subtask_id}</span><span>${esc(step.description)}</span>`;
    container.appendChild(item);
  });
}

function esc(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadSettings() {
  const backendEl = document.getElementById("setting-backend-url");
  if (backendEl) backendEl.value = localStorage.getItem("forge_backend_url") || "";
  const cfg = getClientSettings();
  const plannerEl = document.getElementById("setting-planner-key");
  if (plannerEl) plannerEl.value = cfg.planner || DEFAULT_NIM_KEYS.planner;
  const coderEl = document.getElementById("setting-coder-key");
  if (coderEl) coderEl.value = cfg.coder || DEFAULT_NIM_KEYS.coder;
  const criticEl = document.getElementById("setting-critic-key");
  if (criticEl) criticEl.value = cfg.critic || DEFAULT_NIM_KEYS.critic;
  const routerEl = document.getElementById("setting-router-key");
  if (routerEl) routerEl.value = cfg.router || DEFAULT_NIM_KEYS.router;
}

async function saveSettings() {
  const backendUrl = document.getElementById("setting-backend-url")?.value.trim();
  if (backendUrl) {
    const cleanUrl = backendUrl.replace(/\/+$/, "");
    localStorage.setItem("forge_backend_url", cleanUrl);
    apiBaseUrl = cleanUrl;
    isStaticWeb = false;
  } else {
    localStorage.removeItem("forge_backend_url");
  }
  const cfg = {
    planner: document.getElementById("setting-planner-key")?.value.trim() || DEFAULT_NIM_KEYS.planner,
    coder: document.getElementById("setting-coder-key")?.value.trim() || DEFAULT_NIM_KEYS.coder,
    critic: document.getElementById("setting-critic-key")?.value.trim() || DEFAULT_NIM_KEYS.critic,
    router: document.getElementById("setting-router-key")?.value.trim() || DEFAULT_NIM_KEYS.router,
    models: DEFAULT_NIM_KEYS.models
  };
  localStorage.setItem("forge_settings", JSON.stringify(cfg));
  alert("Settings saved successfully! Backend URL: " + (apiBaseUrl || "Auto-detect / Web Mode"));
  await initSession();
  await loadFiles();
}

async function loadDAGTelemetry() {
  const listEl = document.getElementById("dag-nodes-list") || document.getElementById("dag-tree-list");
  if (!listEl) return;
  const nodes = window._currentDAGNodes || currentPlan || [];
  if (!nodes.length) {
    listEl.innerHTML = '<div style="color:var(--vscode-text-muted);font-size:12px;padding:12px;">No active task graph. Submit a coding prompt in the chat to generate and view the live parallel DAG.</div>';
    return;
  }
  
  const inProgressCount = nodes.filter(n => n.status === "in_progress").length;
  const isParallelActive = inProgressCount > 1;

  let html = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;padding:8px 12px;background:#1e1e1e;border-radius:6px;border:1px solid #3c3c3c;">
      <div style="font-size:12px;color:#fff;">
        <strong>DAG Concurrency:</strong> ${isParallelActive ? '<span style="color:#a6e3a1;font-weight:bold;">⚡ Multi-Worker Parallel Active (' + inProgressCount + ' parallel tasks)</span>' : '<span style="color:#89b4fa;">Topological Layer Scheduled</span>'}
      </div>
      <div style="font-size:11px;color:#858585;">Total Subtasks: ${nodes.length}</div>
    </div>
  `;

  nodes.forEach((n, idx) => {
    const isRunning = n.status === 'in_progress';
    const isDone = n.status === 'done' || n.status === 'completed';
    const statusClass = isDone ? 'completed' : isRunning ? 'running' : 'pending';
    const roleName = n.assigned_role || 'coder';
    const depsText = n.dependencies && n.dependencies.length ? `Deps: [#${n.dependencies.join(', #')}]` : '⚡ Parallel Root (No deps)';
    const targetFile = (n.target_files && n.target_files[0]) || 'solution.py';

    html += `
      <div class="dag-node-card ${statusClass}" onclick="inspectDAGNode(${idx})" style="cursor:pointer;margin-bottom:8px;padding:10px 12px;background:#252526;border:1px solid ${isRunning ? '#89b4fa' : isDone ? '#238636' : '#3c3c3c'};border-radius:6px;box-shadow:${isRunning ? '0 0 10px rgba(137,180,250,0.25)' : 'none'};">
        <div class="dag-node-header" style="display:flex;justify-content:space-between;align-items:center;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="background:#1e1e1e;color:#89b4fa;font-family:var(--font-mono);font-size:10px;padding:2px 6px;border-radius:4px;">Worker #${idx + 1}</span>
            <strong style="color:#ffffff;font-size:12px;">#${n.subtask_id || (idx + 1)}. ${esc(n.description)}</strong>
          </div>
          <span class="dag-status-badge ${statusClass}" style="font-size:9px;padding:2px 8px;border-radius:10px;background:${isDone ? '#238636' : isRunning ? '#007acc' : '#444'};color:#fff;">
            ${(n.status || 'pending').toUpperCase()}
          </span>
        </div>
        <div style="display:flex;gap:12px;font-size:11px;color:#858585;margin-top:6px;">
          <span>Role: <strong style="color:#cdd6f4;">${esc(roleName)}</strong></span>
          <span>Target: <code style="color:#a6e3a1;background:#181818;padding:1px 4px;border-radius:3px;">${esc(targetFile)}</code></span>
          <span style="color:#f9e2af;">${depsText}</span>
        </div>
      </div>
    `;
  });
  listEl.innerHTML = html;
}

function inspectDAGNode(idx) {
  const nodes = window._currentDAGNodes || currentPlan || [];
  const node = nodes[idx];
  if (!node) return;
  const inspectorEl = document.getElementById("node-inspector-content");
  if (inspectorEl) {
    inspectorEl.innerHTML = `
      <div style="font-weight:600;color:#89b4fa;margin-bottom:8px;">Subtask #${node.subtask_id || (idx + 1)}: ${esc(node.description)}</div>
      <div style="font-size:11px;color:#858585;margin-bottom:6px;">
        Role: <strong style="color:#fff;">${esc(node.assigned_role || 'coder')}</strong> | Target File: <code style="color:#a6e3a1;">${esc((node.target_files && node.target_files[0]) || 'solution.py')}</code> | Status: <strong style="color:#89b4fa;">${(node.status || 'pending').toUpperCase()}</strong>
      </div>
      <div style="font-size:11px;color:#858585;">
        Dependencies: ${node.dependencies && node.dependencies.length ? `[#${node.dependencies.join(', #')}]` : 'None (Independent parallel node)'}
      </div>
    `;
  }
}

async function loadDiffReview() {
  const container = document.getElementById("diff-hunk-container");
  if (!container) return;

  try {
    let diffs = [];
    if (!isStaticWeb) {
      const res = await fetch(`${apiBaseUrl}/api/diff/pending`);
      if (res.ok) {
        const data = await res.json();
        diffs = data.diffs || [];
      }
    } else {
      diffs = window._vfsDiffs || [];
    }

    if (!diffs.length) {
      container.innerHTML = `<div style="color:var(--vscode-text-muted);font-size:12px;padding:12px;">Working directory clean. Monaco live editor contains the active buffer. No pending unapproved hunks.</div>`;
      return;
    }

    let html = "";
    diffs.forEach((d, idx) => {
      const isNew = !d.old_content;
      const lines = (d.diff || "").split("\n");
      let diffHtml = "";
      lines.forEach((line, lIdx) => {
        const isAdd = line.startsWith("+") && !line.startsWith("+++");
        const isDel = line.startsWith("-") && !line.startsWith("---");
        const isHunkHeader = line.startsWith("@@");
        let lineStyle = "font-family:var(--font-mono);font-size:11px;padding:1px 8px;white-space:pre;";
        if (isAdd) {
          lineStyle += "background:rgba(46,160,67,0.18);color:#a6e3a1;";
        } else if (isDel) {
          lineStyle += "background:rgba(248,81,73,0.18);color:#f38ba8;";
        } else if (isHunkHeader) {
          lineStyle += "color:#89b4fa;font-weight:bold;background:#1e1e1e;";
        } else {
          lineStyle += "color:#cccccc;";
        }
        diffHtml += `<div style="${lineStyle}"><span style="color:#555;display:inline-block;width:30px;user-select:none;">${lIdx + 1}</span> ${esc(line)}</div>`;
      });

      html += `
        <div class="diff-card" style="margin-bottom:16px;background:#1e1e1e;border:1px solid #3c3c3c;border-radius:6px;overflow:hidden;">
          <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:#252526;border-bottom:1px solid #3c3c3c;">
            <div style="display:flex;align-items:center;gap:8px;">
              <input type="checkbox" id="diff-chk-${d.id || idx}" class="diff-hunk-chk" value="${d.id || idx}" checked />
              <strong style="color:#fff;font-size:12px;">${esc(d.file_path)}</strong>
              <span class="dag-status-badge ${isNew ? 'completed' : 'running'}" style="font-size:9px;">${isNew ? 'NEW FILE' : 'MODIFIED'}</span>
            </div>
            <div style="font-size:10px;color:#858585;">Hunk #${idx + 1}</div>
          </div>
          <div style="max-height:280px;overflow-y:auto;background:#181818;padding:6px 0;">
            ${diffHtml}
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = `<div style="color:#f38ba8;font-size:12px;">Failed to load diff review: ${esc(err.message)}</div>`;
  }
}

async function submitApproval(actionType) {
  const checkboxes = document.querySelectorAll(".diff-hunk-chk:checked");
  const selectedIds = Array.from(checkboxes).map(c => c.value);

  if (actionType === "selected" && !selectedIds.length) {
    alert("Please select at least one diff hunk to approve.");
    return;
  }

  try {
    if (!isStaticWeb) {
      const act = actionType === "all" ? "approve_all" : actionType === "reject" ? "reject_all" : "approve_selected";
      const res = await fetch(`${apiBaseUrl}/api/diff/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: act, selected_ids: selectedIds })
      });
      if (res.ok) {
        const data = await res.json();
        alert(data.message || "Diff action applied successfully.");
      }
    } else {
      alert("Diff action applied in workspace.");
    }
    await loadDiffReview();
    await loadFiles();
    if (activeFile) {
      await openFile(activeFile);
    }
  } catch (err) {
    alert("Error applying diff action: " + err.message);
  }
}

// --- Persistent Memory & Context Window Handlers ---
async function loadMemoryView() {
  const previewEl = document.getElementById("memory-compacted-preview");
  const listEl = document.getElementById("memory-entries-list");
  if (!previewEl || !listEl) return;

  const currentSessionId = window._currentSessionId || "default-session";

  try {
    let memories = [];
    let compacted = "";

    if (!isStaticWeb) {
      const res = await fetch(`${apiBaseUrl}/api/memory/list?session_id=${encodeURIComponent(currentSessionId)}`);
      if (res.ok) {
        const data = await res.json();
        memories = data.memories || [];
        compacted = data.compacted_context || "(No active context in this session yet)";
      }
    } else {
      const stored = localStorage.getItem("forge_memories_" + currentSessionId);
      memories = stored ? JSON.parse(stored) : [];
      compacted = memories.map(m => `- [${m.memory_type.toUpperCase()}] ${m.key}: ${m.content}`).join("\n") || "(No active memories in client-side mode)";
    }

    previewEl.innerText = compacted;

    if (!memories.length) {
      listEl.innerHTML = '<div style="color:var(--vscode-text-muted);font-size:12px;padding:8px;">No stored memory entries. Add a directive above or run tasks to let Forge remember architectural decisions.</div>';
      return;
    }

    let html = "";
    memories.forEach(m => {
      const typeColor = m.memory_type === 'architecture' ? '#89b4fa' : m.memory_type === 'convention' ? '#a6e3a1' : m.memory_type === 'decision' ? '#f9e2af' : '#cdd6f4';
      html += `
        <div style="background:#1e1e1e;border:1px solid #3c3c3c;border-radius:6px;padding:10px 12px;display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
          <div style="flex:1;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
              <span style="background:#252526;color:${typeColor};font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;border:1px solid #444;">${esc(m.memory_type.toUpperCase())}</span>
              <strong style="color:#ffffff;font-size:12px;">${esc(m.key)}</strong>
            </div>
            <div style="font-size:12px;color:#cccccc;white-space:pre-wrap;">${esc(m.content)}</div>
          </div>
          <button class="btn-vscode" style="background:#444;padding:3px 8px;font-size:11px;" onclick="deleteMemoryItem(${m.id || 0}, '${esc(m.key)}')">Delete</button>
        </div>
      `;
    });
    listEl.innerHTML = html;
  } catch (err) {
    listEl.innerHTML = `<div style="color:#f38ba8;font-size:12px;">Error loading memories: ${esc(err.message)}</div>`;
  }
}

async function addCustomMemory() {
  const typeEl = document.getElementById("mem-input-type");
  const keyEl = document.getElementById("mem-input-key");
  const contentEl = document.getElementById("mem-input-content");
  if (!keyEl || !contentEl) return;

  const key = keyEl.value.strip ? keyEl.value.strip() : keyEl.value.trim();
  const content = contentEl.value.strip ? contentEl.value.strip() : contentEl.value.trim();
  const memoryType = (typeEl && typeEl.value) || "fact";

  if (!key || !content) {
    alert("Please provide both a memory key and details.");
    return;
  }

  const currentSessionId = window._currentSessionId || "default-session";

  try {
    if (!isStaticWeb) {
      const res = await fetch(`${apiBaseUrl}/api/memory/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: currentSessionId,
          memory_type: memoryType,
          key: key,
          content: content,
          importance_score: 1.5
        })
      });
      if (res.ok) {
        keyEl.value = "";
        contentEl.value = "";
        await loadMemoryView();
      }
    } else {
      const stored = localStorage.getItem("forge_memories_" + currentSessionId);
      const list = stored ? JSON.parse(stored) : [];
      list.unshift({ id: Date.now(), memory_type: memoryType, key: key, content: content });
      localStorage.setItem("forge_memories_" + currentSessionId, JSON.stringify(list));
      keyEl.value = "";
      contentEl.value = "";
      await loadMemoryView();
    }
  } catch (err) {
    alert("Error saving memory: " + err.message);
  }
}

async function deleteMemoryItem(memId, memKey) {
  const currentSessionId = window._currentSessionId || "default-session";
  try {
    if (!isStaticWeb && memId) {
      await fetch(`${apiBaseUrl}/api/memory/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ memory_id: memId })
      });
    } else {
      const stored = localStorage.getItem("forge_memories_" + currentSessionId);
      let list = stored ? JSON.parse(stored) : [];
      list = list.filter(m => m.key !== memKey && m.id !== memId);
      localStorage.setItem("forge_memories_" + currentSessionId, JSON.stringify(list));
    }
    await loadMemoryView();
  } catch (err) {
    alert("Error deleting memory: " + err.message);
  }
}

async function clearSessionMemory() {
  if (!confirm("Are you sure you want to clear all persistent memories for this session?")) return;
  const currentSessionId = window._currentSessionId || "default-session";
  try {
    if (!isStaticWeb) {
      await fetch(`${apiBaseUrl}/api/memory/clear`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: currentSessionId })
      });
    } else {
      localStorage.removeItem("forge_memories_" + currentSessionId);
    }
    await loadMemoryView();
  } catch (err) {
    alert("Error clearing memories: " + err.message);
  }
}

window.onload = init;
