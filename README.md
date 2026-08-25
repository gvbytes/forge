# Forge IDE (Agent Zero) — Autonomous Agentic Coding Studio

[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-Live%20Demo-brightgreen?logo=github)](https://gvbytes.github.io/forge/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA%20NIM-4--Role%20Architecture-76B900?logo=nvidia)](https://build.nvidia.com)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

> Built for the **Takneek Problem Statement (High Prep)** — Programming Club, IIT Kanpur.
> **GitHub**: [github.com/gvbytes](https://github.com/gvbytes) | **Live Site**: [gvbytes.github.io/forge](https://gvbytes.github.io/forge/)

---

## 1. Overview

**Forge IDE (Agent Zero)** is an autonomous multi-agent software engineering studio built from the ground up for open-weight models ($\le$ 80B parameters) running on NVIDIA NIM endpoints or local hardware.

Small and medium open-weight models frequently suffer orchestration collapse when tasked with planning, coding, and debugging all at once. Forge solves this by decomposing complex requests into a **Dynamic Execution DAG** orchestrated by four specialized roles:

1. **Conductor / Architect (`Role 1: Planner`)**: `nvidia/nemotron-3.5-lightning-30b-a3b`
2. **Primary Code Engineer (`Role 2: Coder`)**: `google/gemma-4-31b-it`
3. **Adversarial Critic (`Role 3: Critic`)**: `meta/muse-glimmer-30b`
4. **Router & Fast Scout (`Role 4: Router`)**: `openai/gpt-oss-20b`

---

## 2. Key Features

- **Dual-Mode Orchestration**:
  - **GitHub Pages Web Studio Mode**: Runs statically in the browser, calling NVIDIA NIM APIs directly with in-browser virtual files and shell.
  - **Full-Stack Self-Hosted Mode**: Runs with FastAPI, SQLite WAL persistence, local AST code indexing, and system subshell execution.
- **Real-Time Monaco Code Streaming**: Differential O(1) `applyEdits` streaming code directly into Monaco Editor without locking the UI or glitching scroll positions.
- **Antigravity-Style Model Selector**: Switch between 4-Role Orchestra, Nemotron 30B, Gemma 31B, GPT-OSS 20B, or Muse 30B directly from the chat interface.
- **Live Orchestration Pipeline Visualizer**: 5-stage real-time execution indicator (`Triage` $\to$ `Research` $\to$ `Planner` $\to$ `Coder` $\to$ `Critic`) with interactive DAG telemetry modals.
- **Interactive Web Terminal**: Full zsh console with dynamic CWD tracking, ANSI color rendering, Tab autocomplete, and Ctrl+C/L/U shortcuts.
- **Autonomous Multi-Engine Web Researcher**: Built-in Wikipedia REST APIs, PyPI docs, and DuckDuckGo search integration.
- **Block-by-Block Git Diff Review (HITL)**: Human-in-the-loop hunk approval with partial acceptance handling.
- **Isolated `/bytheway` Spot Queries**: Zero-context queries answered in sub-seconds without polluting task context.
- **AST Symbol Code Retrieval**: Hierarchical AST parser + BM25 ranking across Python, JavaScript/TypeScript, Go, Rust, and C/C++.
- **Automatic Context Compaction**: Token-aware context compression preserving `AGENTS.md` rules and plan status.

---

## 3. Quickstart & Installation

### Option A: Open Live on GitHub Pages (Zero Install)
Visit the live deployment at: **[https://gvbytes.github.io/forge/](https://gvbytes.github.io/forge/)**

1. Click **Settings (Gear Icon)** in the left activity bar.
2. Enter your **NVIDIA NIM API Key(s)** (or use default).
3. Start coding!

---

### Option B: Run Full-Stack Locally (Linux / macOS / Windows)

#### 1. Clone the repository
```bash
git clone https://github.com/gvbytes/forge.git
cd agent-zero
```

#### 2. Setup Virtual Environment
```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

#### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 4. Launch Forge IDE
```bash
python run.py
```
Open **`http://127.0.0.1:8000`** in your browser.

---

## 4. System Architecture & Flow

```
User Prompt
    │
    ▼
[Router: GPT-OSS 20B] ──── (Greeting/Chit-Chat) ───► Fast Reply (~0.5s)
    │
    ▼ (Coding Task / Complex Goal)
[Autonomous Web Researcher] (Wikipedia / PyPI / Web Scraper)
    │
    ▼
[Planner: Nemotron 30B] ────► Decomposes into Dynamic Task Graph (DAG)
    │
    ▼
[Coder: Gemma 31B] ─────────► Live Token Stream into Monaco Editor
    │
    ▼
[Critic: Muse 30B] ─────────► Adversarial Red-Team Audit & Bug Patching
    │
    ▼
[SQLite State / Disk] ──────► Final Verified Result & Live Telemetry
```

---

## 5. Architectural Trade-Off Analysis

| Decision | Chosen Approach | Alternative Considered | Rationale |
|---|---|---|---|
| **Orchestrator Topology** | 4-Role Heterogeneous NIM Pipeline | Single Unified LLM (e.g. 70B alone) | Single $\le \text{80B}$ models fail at simultaneous long-horizon planning and bug fixing. Specialized roles prevent orchestration collapse. |
| **Monaco Streaming** | Differential `model.applyEdits()` | Repeated `editor.setValue()` | `setValue()` recreates AST and layout 50x/sec, causing main-thread stutter. `applyEdits` provides O(1) silky 60 FPS streaming. |
| **Code Retrieval** | Hierarchical AST + BM25 | Raw Vector Embeddings / Full Files | AST indexing extracts exact function/class bounds (20-50 lines), cutting prompt token costs by up to $78\%$. |
| **State Persistence** | SQLite with WAL Mode | In-Memory / File Dumps | SQLite WAL ensures zero corruption, atomic checkpointing, and instant recovery across process crashes. |
| **Terminal Integration** | Interactive ANSI-enabled Subshell | Read-only Form Submission Box | Embedded interactive terminal supports persistent `cd`, real-time stderr/stdout colors, and keyboard shortcuts. |

---

## 6. Mathematical Scoring Formula

$$\text{Task Score } S_{\text{task}} = \frac{10 \cdot A}{\left(1 + 0.65 \left(\frac{C}{\$0.15}\right) + 0.35 \left(\frac{T}{1320}\right)\right)^{2.5}}$$

- **Accuracy Ceiling**: $A \in [0, 1]$.
- **Hard Cost Budget**: $\$0.50$ maximum.
- **Hard Time Limit**: $2700\text{ seconds}$ maximum.

---

## 7. Project Structure

```
agent-zero/
├── .github/workflows/deploy.yml   # GitHub Pages deployment CI/CD
├── backend/
│   ├── indexer/ast_retriever.py   # Multi-language AST + BM25 retrieval
│   ├── models/nim_client.py       # NVIDIA NIM API client & failover
│   ├── orchestrator/              # State machine, DAG, compaction, SQLite
│   ├── tools/                     # Web scraper, sandbox executor, HITL
│   ├── config.py                  # 4-Role configuration & workspace resolution
│   └── server.py                  # FastAPI REST & SSE streaming server
├── frontend/                      # Web UI source assets
├── home/                          # Dedicated workspace directory
├── index.html                     # Root entry point for GitHub Pages
├── styles.css                     # Root styling bundle
├── app.js                         # Root Dual-Mode Orchestrator engine
├── AGENTS.md                      # System instructions & coding standards
├── ARCHITECTURE.md                # Comprehensive technical specification
├── README.md                      # Project documentation
├── requirements.txt               # Dependencies
└── run.py                         # Application runner
```

---

## 8. License

MIT License. Developed for IIT Kanpur Takneek by [Gaurav (gvbytes)](https://github.com/gvbytes).
