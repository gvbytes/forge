# Forge IDE (Agent Zero) — Comprehensive Test Suite & Benchmark Plan

This document outlines standard, edge-case, and performance benchmark test cases to validate the end-to-end capabilities of **Forge IDE**.

---

## Matrix Overview

| Category | Suite ID | Test Focus | Target Component |
| :--- | :--- | :--- | :--- |
| **Intent & Research** | `TC-01` to `TC-05` | Chit-chat vs. Web Research vs. Code Generation | `Router`, `ScraperTool`, `classify_intent` |
| **Code Generation** | `TC-06` to `TC-10` | Single-turn, multi-file, Monaco token streaming | `Coder`, `StreamingParser`, Monaco Editor |
| **Parallel DAG** | `TC-11` to `TC-15` | Multi-agent concurrency, topological layers | `TaskGraph`, `AsyncioWorkerPool`, `app.js` |
| **HITL Diff Review** | `TC-16` to `TC-20` | Patch inspection, approve/reject hunks | `DiffEngine`, Git VFS, Source Control Tab |
| **Persistent Memory** | `TC-21` to `TC-25` | Episodic memory, context window compaction | `PersistenceEngine`, SQLite WAL, Memory Tab |
| **Self-Healing Loop** | `TC-26` to `TC-30` | AST validation, runtime error auto-repair | `Critic`, `ASTIndexer`, `DeterministicOrchestrator` |
| **Terminal & VFS** | `TC-31` to `TC-35` | Subprocess isolation, output windowing | `ToolExecutor`, `window_output`, Terminal UI |
| **Takneek Metric** | `TC-36` to `TC-40` | Cost ($C < \$0.002$), Latency ($T < 5\text{s}$), Accuracy | NIM Client, Token Meter, Formula Score |

---

## 1. Intent Classification & Web Intelligence (`TC-01` – `TC-05`)

### `TC-01`: Conversational Greeting Triage
- **Prompt**: `"Hello, who are you and what can you do?"`
- **Expected Intent**: `greeting`
- **Expected Behavior**:
  - Response delivered in 1–2 sentences in Chat panel.
  - Editor remains untouched (0 files modified, 0 `.ino`/`.py` files created).
  - Latency: $< 800\text{ms}$, Tokens: $< 80$.

### `TC-02`: Conceptual Research Query (No Code Intrusion)
- **Prompt**: `"Give me info about Bionic Butterfly"`
- **Expected Intent**: `research_info`
- **Expected Behavior**:
  - Automatically triggers DuckDuckGo search (`ddgs`) & Bing fallback.
  - Generates comprehensive markdown explanation with aerodynamics, actuation, and citations.
  - `saved_file` is `None` (no spurious code files created in the workspace).

### `TC-03`: Academic / Paper Lookup
- **Prompt**: `"Explain Raft consensus algorithm and leader election steps."`
- **Expected Intent**: `research_info`
- **Expected Behavior**:
  - Delivers state transitions, terms, and log replication steps in chat.
  - Zero code written to Monaco editor buffer.

### `TC-04`: Direct Python Package Documentation Scrape
- **Prompt**: `"Search for fastapi-limiter library documentation and explain how Redis is used."`
- **Expected Intent**: `research_info`
- **Expected Behavior**:
  - PyPI / Web Scraper retrieves package metadata.
  - Summarizes API usage and Redis dependencies in markdown.

### `TC-05`: Boundary Disambiguation
- **Prompt**: `"What is a Snake Game?"` vs `"Build a Snake game in HTML/JS"`
- **Expected Behavior**:
  - `"What is a Snake Game?"` $\to$ Returns gameplay history & mechanics in Chat (`research_info`).
  - `"Build a Snake game in HTML/JS"` $\to$ Decomposes into DAG tasks, creates `snake.html`, and streams playable game code to Monaco Editor (`coding_task`).

---

## 2. Code Generation & Monaco Token Streaming (`TC-06` – `TC-10`)

### `TC-06`: Single File Generation (Clean Header & Code Parsing)
- **Prompt**: `"Write a Python script solution.py that implements binary search with type hints and doctests."`
- **Expected Behavior**:
  - Emits `code_chunk` events streaming real-time into Monaco Editor.
  - Creates `solution.py` in workspace with passing doctests.

### `TC-07`: Multi-File Web Application
- **Prompt**: `"Build a full-stack Stopwatch app with index.html, styles.css, and app.js with lap timing."`
- **Expected Behavior**:
  - Planner breaks down into 3 subtasks.
  - Creates `index.html`, `styles.css`, and `app.js` with proper cross-linking.

### `TC-08`: Refactoring & In-Place Code Replacement
- **Prompt**: `"Refactor solution.py to use an iterative approach instead of recursion."`
- **Expected Behavior**:
  - Reads existing `solution.py` via AST/VFS.
  - Streams updated implementation and saves cleaned code.

### `TC-09`: Syntax Error Resilience
- **Prompt**: `"Write a complex matrix multiplication script in Python with rigorous type hints."`
- **Expected Behavior**:
  - Code passes `ast.parse()` validation.
  - No unbalanced parenthesis or unclosed string literals.

### `TC-10`: Large-File Windowing
- **Prompt**: `"Generate a mock database schema with 50 table models in models.py."`
- **Expected Behavior**:
  - Handles token windowing without hitting context truncation limits.

---

## 3. Parallel Multi-Agent DAG Execution (`TC-11` – `TC-15`)

### `TC-11`: Independent Layer Concurrency (Kahn's Topological Sort)
- **Prompt**: `"Create a microservices backend: auth_service.py, payment_service.py, and notification_service.py simultaneously."`
- **Expected Behavior**:
  - Planner generates 3 subtasks with `dependencies: []`.
  - Server executes Layer 0 concurrently using `asyncio.gather()`.
  - DAG viewer in `view-dag` displays `RUNNING (Worker #1)`, `RUNNING (Worker #2)`, `RUNNING (Worker #3)`.

### `TC-12`: Sequential Dependency Gating
- **Prompt**: `"Create database_schema.py first, then write db_crud.py that imports the schema, then write test_crud.py."`
- **Expected Behavior**:
  - Subtask #2 depends on #1; Subtask #3 depends on #2.
  - DAG viewer transitions through Layer 0 $\to$ Layer 1 $\to$ Layer 2 sequentially.

### `TC-13`: Diamond DAG Graph Resolution
- **Prompt**: `"Build common_utils.py, then simultaneously build worker_a.py and worker_b.py using utils, then build main.py merging both."`
- **Expected Behavior**:
  - Layer 0: `[common_utils.py]`
  - Layer 1 (Parallel): `[worker_a.py, worker_b.py]`
  - Layer 2: `[main.py]`

### `TC-14`: DAG Node Inspector Interaction
- **Action**: Click individual node cards in `view-dag`.
- **Expected Behavior**:
  - Displays subtask ID, assigned role (Planner/Coder/Critic), target file, status, and dependency list.

### `TC-15`: Dynamic DAG Failure Recovery
- **Scenario**: Subtask #1 encounters a syntax error during parallel execution.
- **Expected Behavior**:
  - Dependent subtasks wait in `PENDING` state while Critic triggers self-healing on Subtask #1.

---

## 4. Human-In-The-Loop (HITL) Diff Review (`TC-16` – `TC-20`)

### `TC-16`: Pending Diff Generation
- **Action**: Have Forge modify an existing file `calculator.py`.
- **Expected Behavior**:
  - Generates unified diff hunks with line-level additions/deletions.
  - Activity Bar badge or Diff Review panel (`view-diff`) displays pending hunks.

### `TC-17`: Selective Hunk Approval
- **Action**: Select 1 out of 3 hunks and click *"Approve Selected"*.
- **Expected Behavior**:
  - Applies approved hunk to disk; keeps unapproved hunks pending.

### `TC-18`: Approve All Diffs
- **Action**: Click *"Approve All"*.
- **Expected Behavior**:
  - Writes all modified buffers to workspace.
  - Monaco editor refreshes with new contents.

### `TC-19`: Reject All Diffs
- **Action**: Click *"Reject All"*.
- **Expected Behavior**:
  - Discards pending hunks; restores workspace files to their original state.

### `TC-20`: In-Editor Monaco Diff Viewer
- **Action**: Open diff review on a modified file.
- **Expected Behavior**:
  - Renders side-by-side or inline colorized diffs (`#a6e3a1` for additions, `#f38ba8` for deletions).

---

## 5. Persistent Memory & Context Window Compaction (`TC-21` – `TC-25`)

### `TC-21`: Custom Directive Injection
- **Action**: In `view-memory`, add:
  - Type: `convention`
  - Key: `framework_rules`
  - Content: `Always use FastAPI with Pydantic v2 and SQLite WAL mode.`
- **Expected Behavior**:
  - Saved to SQLite `memories` table.
  - Injected into subsequent coding prompts under `=== [Persistent Memory & Session Context] ===`.

### `TC-22`: Automatic Sliding Context Compaction
- **Action**: Conduct 6 consecutive prompt turns.
- **Expected Behavior**:
  - Earlier turns are compacted into concise summary bullet points (`get_compacted_context_window()`).
  - Total prompt token footprint remains $< 1,500$ tokens.

### `TC-23`: Cross-Session Memory Persistence
- **Action**: Restart backend server process and query `GET /api/memory/list`.
- **Expected Behavior**:
  - Previously stored memories remain intact from `forge.db`.

### `TC-24`: Memory Deletion & Clear
- **Action**: Click *"Delete"* on a specific memory entry and *"Clear All"*.
- **Expected Behavior**:
  - Entry removed from SQLite table and UI updates immediately.

### `TC-25`: Context Window Overflow Protection (TrueForge Pattern)
- **Scenario**: Execute a tool generating $10,000$ lines of output.
- **Expected Behavior**:
  - Truncated with head/tail omission markers, preventing LLM context blowup.

---

## 6. Self-Healing Error Repair Loop (`TC-26` – `TC-30`)

### `TC-26`: Python AST Syntax Validation
- **Scenario**: Coder generates invalid Python (missing colon or unclosed bracket).
- **Expected Behavior**:
  - `_check_syntax_fast()` detects error.
  - State machine re-prompts Critic with error trace for automatic repair.

### `TC-27`: Runtime Exception Auto-Fix
- **Prompt**: `"Write a division utility divide(a, b) and test divide(10, 0)."`
- **Expected Behavior**:
  - Terminal runs script, captures `ZeroDivisionError`, and Critic rewrites `divide()` with exception handling.

### `TC-28`: Infinite Self-Healing Loop Protection
- **Scenario**: A task repeatedly fails due to an unsolvable environment dependency.
- **Expected Behavior**:
  - Action hash tracker stops execution after 3 repeated identical hashes (`halt_reason: "Cycle detected"`).

### `TC-29`: Critic Quality Rating ($\ge 8.5/10$)
- **Scenario**: Task completes generation.
- **Expected Behavior**:
  - Critic role evaluates correctness, edge cases, and code quality before approving.

### `TC-30`: Pytest Suite Integration
- **Prompt**: `"Write a string reverser with pytest test_reverser.py and verify all tests pass."`
- **Expected Behavior**:
  - Executes `pytest` in terminal; self-heals if any test assertion fails.

---

## 7. Integrated Terminal & Workspace Isolation (`TC-31` – `TC-35`)

### `TC-31`: Interactive Command Execution
- **Action**: Run `ls -la`, `python3 --version`, `pwd` in the Terminal panel.
- **Expected Behavior**:
  - Output streams directly into the terminal window with exit code `0`.

### `TC-32`: Run File Action Button
- **Action**: Open `solution.py` in Monaco Editor and click the **Run** button.
- **Expected Behavior**:
  - Executes `python3 solution.py` in workspace directory and streams stdout/stderr.

### `TC-33`: Long-Running Process Guard
- **Action**: Run `python3 -c "import time; time.sleep(100)"`.
- **Expected Behavior**:
  - Command executes with timeout or allows background management without freezing the UI.

### `TC-34`: Terminal Clear & ANSI Escape Code Stripping
- **Action**: Run colorful output (`pytest` or `git status`).
- **Expected Behavior**:
  - ANSI colors render cleanly or clean text displays in the terminal body.

### `TC-35`: Path Traversal Security
- **Action**: Attempt writing to `../../etc/passwd`.
- **Expected Behavior**:
  - Rejected by `ToolExecutor` path sanitizer with path confinement error.

---

## 8. Takneek Benchmark Formula & Efficiency (`TC-36` – `TC-40`)

### Benchmark Scoring Metric
$$S_{\text{task}} = \frac{10 \cdot A}{\left( 1 + 0.65 \left(\frac{C}{0.15}\right) + 0.35 \left(\frac{T}{1320}\right) \right)^{2.5}}$$

Where:
- $A \in [0, 1]$: Accuracy / Test pass rate
- $C$: Total LLM cost in USD
- $T$: Wall-clock execution time in seconds

### `TC-36`: Sub-Second Chit-Chat Cost ($C < \$0.00005, T < 1.0\text{s}$)
- **Target**: Score $S_{\text{task}} \ge 9.85$

### `TC-37`: Single-File Code Task ($C < \$0.0015, T < 4.0\text{s}$)
- **Target**: Score $S_{\text{task}} \ge 9.20$

### `TC-38`: 3-Node Parallel Execution ($C < \$0.0035, T < 6.5\text{s}$)
- **Target**: Score $S_{\text{task}} \ge 8.80$

### `TC-39`: Live Web Intelligence Query ($C < \$0.0008, T < 3.0\text{s}$)
- **Target**: Score $S_{\text{task}} \ge 9.40$

### `TC-40`: Multi-Turn Session with Compaction ($C < \$0.005, T < 15.0\text{s}$)
- **Target**: Score $S_{\text{task}} \ge 8.50$

---

## Automated Test Runner Command

To run the automated Python test suite across these test cases, execute:

```bash
# Run unit & integration test suite
python3 -m pytest tests/ -v
```
