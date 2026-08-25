# Forge IDE (Agent Zero) — System Architecture & Mathematical Specification

## 1. Executive Summary

**Forge IDE (Agent Zero)** is a multi-agent autonomous software engineering studio engineered specifically for open-weight models ($\le$ 80B parameters) hosted on NVIDIA NIM endpoints or local hardware.

The system addresses the fundamental limitation of small and medium language models: **single models cannot reliably perform multi-step planning, long-horizon code synthesis, and self-debugging simultaneously without suffering orchestration collapse or catastrophic forgetting.**

---

## 2. Multi-Agent 4-Role NIM Architecture

```
                                      +---------------------------------------------+
                                      |                 User Prompt                 |
                                      +----------------------+----------------------+
                                                             |
                                                             v
                                      +---------------------------------------------+
                                      |      Intent Triage & Router (Role 4)        |
                                      |            openai/gpt-oss-20b               |
                                      +----------------------+----------------------+
                                                             |
                           +---------------------------------+---------------------------------+
                           |                                                                   |
            [Conversational / Greeting]                                              [Coding Task / DAG Goal]
                           |                                                                   |
                           v                                                                   v
              +-------------------------+                                     +---------------------------------+
              | Fast Single-Turn Reply  |                                     |    Autonomous Web Researcher    |
              |     (~0.5s Latency)     |                                     | (Wikipedia / PyPI / Web Scraper)|
              +-------------------------+                                     +----------------+----------------+
                                                                                               |
                                                                                               v
                                                                              +---------------------------------+
                                                                              |   Conductor / Planner (Role 1)  |
                                                                              |  nvidia/nemotron-3.5-30b-a3b    |
                                                                              +----------------+----------------+
                                                                                               |
                                                                                               v
                                                                              +---------------------------------+
                                                                              |      Dynamic Task Graph (DAG)   |
                                                                              |    (Decomposed Atomic Nodes)    |
                                                                              +----------------+----------------+
                                                                                               |
                                                              +--------------------------------+--------------------------------+
                                                              |                                                                 |
                                                              v                                                                 v
                                             +---------------------------------+                               +---------------------------------+
                                             |   Primary Coder (Role 2)        |                               |  Adversarial Critic (Role 3)    |
                                             |    google/gemma-4-31b-it        |                               |     meta/muse-glimmer-30b       |
                                             +----------------+----------------+                               +----------------+----------------+
                                                              |                                                                 |
                                                              v                                                                 v
                                             +---------------------------------+                               +---------------------------------+
                                             |   Real-Time Monaco Live Stream  |                               |   Red-Team Audit & Bug Patch    |
                                             |   (Differential applyEdits)     |                               |   (Regression & Edge Check)     |
                                             +----------------+----------------+                               +----------------+----------------+
                                                              |                                                                 |
                                                              +--------------------------------+--------------------------------+
                                                                                               |
                                                                                               v
                                                                              +---------------------------------+
                                                                              |    Workspace Disk Persistence   |
                                                                              |    & Live Observability Trace   |
                                                                              +---------------------------------+
```

### Role Specifications

1. **Conductor / Architect (`Role 1` - Planner)**:
   - **Model**: `nvidia/nemotron-3.5-lightning-30b-a3b`
   - **Responsibility**: Dynamic task decomposition, topological dependency graph construction, and access list allocation.
2. **Primary Code Engineer (`Role 2` - Coder)**:
   - **Model**: `google/gemma-4-31b-it` (auto-failover: `nemotron-30b`)
   - **Responsibility**: Multi-file implementation, differential Git patch generation, and live Monaco Editor token streaming.
3. **Adversarial Critic & Verifier (`Role 3` - Critic)**:
   - **Model**: `meta/muse-glimmer-30b` (auto-failover: `gpt-oss-20b`)
   - **Responsibility**: Red-team verification, logic soundness audits, edge-case analysis, and automatic patch generation.
4. **Router & Fast Scout (`Role 4` - Router)**:
   - **Model**: `openai/gpt-oss-20b`
   - **Responsibility**: Sub-second intent classification, `/bytheway` zero-context spot consulting, and AST symbol query triage.

---

## 3. Mathematical Evaluation & Cost Penalty Formulations

The system is evaluated against the official Takneek PS task score formula:

$$S_{\text{task}} = \frac{10 \cdot A}{\left(1 + w_C \left(\frac{C}{C_{\text{base}}}\right) + w_T \left(\frac{T}{T_{\text{base}}}\right)\right)^\epsilon}$$

Where:
- $A \in [0, 1]$: Accuracy (ratio of passed test cases).
- $C$: Cumulative session cost in USD.
- $T$: Wall-clock execution time in seconds.
- $C_{\text{base}} = \$0.15$, $T_{\text{base}} = 1320\text{ s}$.
- $w_C = 0.65$ (Cost weight), $w_T = 0.35$ (Time weight).
- $\epsilon = 2.5$ (Penalty exponent penalizing cost overruns).
- **Hard Ceilings**: Maximum budget $\$0.50$ and maximum time $2700\text{ s}$.

---

## 4. AST Symbol Code Retrieval Pipeline

Rather than dumping entire source files into LLM context windows, Forge utilizes hierarchical AST parsing:
1. **Tree Extraction**: Recursively parses `.py`, `.js`, `.ts`, `.go`, `.rs`, `.c`, `.cpp` into symbol trees (classes, methods, functions, docstrings).
2. **Hybrid BM25 Scoring**: Evaluates query relevance across symbol signatures:

$$\text{Score}(D, Q) = \sum_{i=1}^N \text{IDF}(q_i) \cdot \frac{f(q_i, D) \cdot (k_1 + 1)}{f(q_i, D) + k_1 \cdot \left(1 - b + b \cdot \frac{|D|}{\text{avgdl}}\right)}$$

3. **Surgical Context Window**: Injects only 20–50 relevant line slices into the Coder's prompt context, reducing prompt token costs by up to $78\%$.

---

## 5. Automatic Context Compaction Engine

When accumulated conversation turns exceed the compaction threshold ($\approx 24,000$ tokens), the compactor:
- Preserves active system directives, `AGENTS.md` guidelines, and task graph status.
- Summarizes historical conversational exchanges.
- Prunes redundant bash/tool outputs while retaining essential diff hunks.

---

## 6. Real Interactive Terminal Console

- Embedded native prompt line with dynamic CWD tracking (`~/home $`).
- Real-time ANSI escape color decoding (green, cyan, yellow, blue, red, bold, dim).
- Tab completion for workspace files.
- Full keyboard shortcuts: `Ctrl+C` (abort), `Ctrl+L` (clear), `Ctrl+U` (erase line), `Ctrl+A` / `Ctrl+E` (jump start/end), `Arrow Up/Down` (history).
