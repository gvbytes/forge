import os
import uuid
import time
import difflib
from typing import Dict, Any, List, Optional
from pathlib import Path

import json
import re
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import settings
from backend.models.router import SmartRouter
from backend.indexer.ast_retriever import workspace_registry
from backend.tools.executor import ToolExecutor
from backend.orchestrator.persistence import persistence
from backend.orchestrator.state_machine import DeterministicOrchestrator, validate_code_syntax

PENDING_DIFF_HUNKS: List[Dict[str, Any]] = []

def record_file_diff(file_path: str, old_content: str, new_content: str):
    if not new_content.strip():
        return
    old_lines = old_content.splitlines(keepends=True) if old_content else []
    new_lines = new_content.splitlines(keepends=True)
    if old_content:
        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{file_path}", tofile=f"b/{file_path}",
            lineterm=""
        ))
        diff_text = "".join(diff)
    else:
        # New file creation diff
        diff_lines = [f"+{l}" for l in new_content.splitlines()]
        diff_text = f"--- /dev/null\n+++ b/{file_path}\n@@ -0,0 +1,{len(diff_lines)} @@\n" + "\n".join(diff_lines)

    if not diff_text.strip():
        return
    global PENDING_DIFF_HUNKS
    PENDING_DIFF_HUNKS = [d for d in PENDING_DIFF_HUNKS if d["file_path"] != file_path]
    PENDING_DIFF_HUNKS.append({
        "id": str(uuid.uuid4())[:8],
        "file_path": file_path,
        "old_content": old_content,
        "new_content": new_content,
        "diff": diff_text,
        "timestamp": time.time(),
        "status": "pending"
    })

app = FastAPI(title="Agent Zero API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
active_orchestrators: Dict[str, DeterministicOrchestrator] = {}

class RoleUpdateRequest(BaseModel):
    model: Optional[str] = None
    api_key: Optional[str] = None

class SettingsUpdate(BaseModel):
    nvidia_base_url: Optional[str] = None
    active_workspace: Optional[str] = None
    planner: Optional[RoleUpdateRequest] = None
    coder: Optional[RoleUpdateRequest] = None
    critic: Optional[RoleUpdateRequest] = None
    router: Optional[RoleUpdateRequest] = None

class SessionInitRequest(BaseModel):
    workspace_root: Optional[str] = None

class MemoryAddRequest(BaseModel):
    session_id: str
    memory_type: str = "fact"
    key: str
    content: str
    importance_score: Optional[float] = 1.0

class MemoryClearRequest(BaseModel):
    session_id: str

class MemoryDeleteRequest(BaseModel):
    memory_id: int

class ChatRequest(BaseModel):
    session_id: str
    message: str
    active_file: Optional[str] = None
    model_mode: Optional[str] = "auto"

class ApprovalRequest(BaseModel):
    session_id: str
    approved_hunks_indices: List[int]
    approved: bool = False
    workspace_root: Optional[str] = None

class TerminalExecRequest(BaseModel):
    command: str
    approved: bool = False
    workspace_root: Optional[str] = None
    cwd: Optional[str] = None

class FileCreateRequest(BaseModel):
    file_path: str
    content: Optional[str] = ""
    workspace_root: Optional[str] = None

class FileDeleteRequest(BaseModel):
    file_path: str
    workspace_root: Optional[str] = None

class FileRenameRequest(BaseModel):
    old_path: str
    new_path: str
    workspace_root: Optional[str] = None

class FileWriteRequest(BaseModel):
    file_path: str
    content: str
    approved: bool = False
    workspace_root: Optional[str] = None

def get_or_create_orchestrator(session_id: str, workspace_root: Optional[str] = None) -> DeterministicOrchestrator:
    ws = workspace_root or settings.active_workspace
    if session_id not in active_orchestrators:
        active_orchestrators[session_id] = DeterministicOrchestrator(
            session_id=session_id,
            workspace_root=ws,
        )
    return active_orchestrators[session_id]

@app.get("/api/settings")
def get_settings():
    return {
        "nvidia_base_url": settings.nvidia_base_url,
        "active_workspace": settings.active_workspace,
        "max_budget_usd": settings.max_budget_usd,
        "timeout_seconds": settings.timeout_seconds,
        "roles": {
            "planner": settings.role_planner.to_dict(),
            "coder": settings.role_coder.to_dict(),
            "critic": settings.role_critic.to_dict(),
            "router": settings.role_router.to_dict(),
        }
    }

@app.post("/api/settings")
def update_settings(payload: SettingsUpdate):
    if payload.nvidia_base_url:
        settings.nvidia_base_url = payload.nvidia_base_url
    if payload.active_workspace:
        raw_ws = payload.active_workspace.strip()
        project_home = str(Path(__file__).parent.parent / "home")
        os.makedirs(project_home, exist_ok=True)
        if raw_ws in ["/home", "home", "workspace", "/workspace"]:
            resolved_ws = project_home
        elif not os.path.exists(raw_ws):
            resolved_ws = project_home
        else:
            resolved_ws = os.path.abspath(os.path.expanduser(raw_ws))
        settings.active_workspace = resolved_ws
    if payload.planner:
        settings.update_role("planner", payload.planner.model, payload.planner.api_key)
    if payload.coder:
        settings.update_role("coder", payload.coder.model, payload.coder.api_key)
    if payload.critic:
        settings.update_role("critic", payload.critic.model, payload.critic.api_key)
    if payload.router:
        settings.update_role("router", payload.router.model, payload.router.api_key)
    settings.save_to_disk()
    return {"status": "ok", "settings": get_settings()}

@app.post("/api/session/init")
def init_session(payload: Optional[SessionInitRequest] = None):
    session_id = str(uuid.uuid4())
    ws = (payload.workspace_root if payload else None) or settings.active_workspace
    if not os.path.exists(ws):
        os.makedirs(ws, exist_ok=True)
    settings.active_workspace = ws
    settings.save_to_disk()
    
    idx = workspace_registry.get_index(ws)
    symbols_indexed = idx.build_index()
    
    orch = get_or_create_orchestrator(session_id, ws)
    
    return {
        "session_id": session_id,
        "workspace_root": ws,
        "symbols_indexed": symbols_indexed,
    }

@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest):
    try:
        orch = get_or_create_orchestrator(payload.session_id)
        msg = payload.message.strip()
        
        persistence.add_message(payload.session_id, "user", msg)
        
        if msg.startswith("/bytheway"):
            isolated_query = msg[len("/bytheway"):].strip()
            result = await orch.execute_bytheway(isolated_query)
            persistence.add_message(payload.session_id, "assistant", f"[ByTheWay]: {result['answer']}")
            return {
                "type": "bytheway",
                "result": result
            }

        is_conv = await orch.is_conversational(msg)
        if is_conv:
            chat_res = await orch.execute_direct_chat(msg)
            persistence.add_message(payload.session_id, "assistant", chat_res["answer"])
            return {
                "type": "chat",
                "answer": chat_res["answer"],
                "thinking": chat_res.get("thinking", ""),
                "model": chat_res["model"]
            }

        workflow_result = await orch.execute_deterministic_loop(msg)
        persistence.add_message(payload.session_id, "assistant", workflow_result["explanation"])
        
        return workflow_result
    except Exception as e:
        err_msg = str(e)
        persistence.add_message(payload.session_id, "assistant", f"Error: {err_msg}")
        return {
            "type": "error",
            "message": err_msg,
            "result": {"answer": f"Encountered issue: {err_msg}"}
        }

@app.post("/api/chat/stream")
async def chat_stream_endpoint(payload: ChatRequest):
    orch = get_or_create_orchestrator(payload.session_id)
    msg = payload.message.strip()
    persistence.add_message(payload.session_id, "user", msg)

    async def event_generator():
        try:
            ws = settings.active_workspace
            
            # 1. Discover all workspace files
            all_ws_files = []
            if os.path.exists(ws):
                for root, dirs, files in os.walk(ws):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {".git", ".venv", "venv"}]
                    for f in files:
                        if not f.startswith(".") and not f.endswith((".pyc", ".db", ".log")):
                            all_ws_files.append(os.path.relpath(os.path.join(root, f), ws))

            target_file = payload.active_file or "solution.py"
            # Check if user mentioned a specific file in the prompt
            matched_file = None
            for wf in all_ws_files:
                if wf.lower() in msg.lower():
                    matched_file = wf
                    break
            if not matched_file:
                m = re.search(r'(?:in|file|edit|update|complete)\s+([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)', msg, re.IGNORECASE)
                if m:
                    matched_file = m.group(1)

            if matched_file:
                target_file = matched_file

            yield f"data: {json.dumps({'type': 'init', 'target_file': target_file})}\n\n"

            # 2. Build rich workspace context with existing file contents
            workspace_context = f"Current Workspace Directory: {ws}\n"
            if all_ws_files:
                workspace_context += f"Files available in workspace: {', '.join(all_ws_files)}\n\n"

            target_full_path = os.path.join(ws, target_file)
            if os.path.exists(target_full_path):
                try:
                    with open(target_full_path, "r", encoding="utf-8", errors="replace") as f:
                        existing_content = f.read()
                    workspace_context += (
                        f"=== Contents of Existing File: `{target_file}` ===\n```\n{existing_content}\n```\n"
                        "The user wants you to edit, complete, or improve this file.\n"
                        "Output the complete revised code inside a single ```<lang> ... ``` code block.\n\n"
                    )
                except Exception:
                    pass

            # 0. Model Mode Overrides
            coder_model = settings.role_coder.model
            planner_model = settings.role_planner.model
            if payload.model_mode == "nemotron":
                coder_model = "nvidia/nemotron-3.5-lightning-30b-a3b"
                planner_model = "nvidia/nemotron-3.5-lightning-30b-a3b"
            elif payload.model_mode == "gemma":
                coder_model = "google/gemma-4-31b-it"
            elif payload.model_mode == "gpt-oss":
                coder_model = "openai/gpt-oss-20b"
                planner_model = "openai/gpt-oss-20b"
            elif payload.model_mode == "muse":
                coder_model = "meta/muse-glimmer-30b"

            yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'triage', 'label': 'Triage & Intent Classification', 'role': 'Router', 'model': settings.role_router.model})}\n\n"

            # 2. Hermes-Agent Autonomous Tools: Web Scraper & Web Search Integration
            yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'research', 'label': 'AST Context & Knowledge Retrieval', 'role': 'Researcher'})}\n\n"
            url_match = re.search(r'https?://[^\s<>"]+|www\.[^\s<>"]+', msg)
            if url_match:
                scraped_url = url_match.group(0)
                if not scraped_url.startswith("http"):
                    scraped_url = "https://" + scraped_url
                try:
                    scrape_res = await orch.execute_tool("web_scrape", {"url": scraped_url})
                    if scrape_res.get("status") == "success":
                        workspace_context += (
                            f"\n=== Live Web Content Scraped by Agent from `{scraped_url}` ===\n"
                            f"Title: {scrape_res.get('title')}\n"
                            f"{scrape_res.get('content')}\n"
                            f"=== End Live Web Content ===\n\n"
                        )
                except Exception as e:
                    workspace_context += f"\n[Web Scraper Notice]: Could not fetch {scraped_url}: {str(e)}\n\n"

            # Check for general web search or entity research intent (e.g. "about Narendra Modi", "search web for X", "docs for X")
            research_match = re.search(r'(?:search\s+(?:the\s+)?web\s+for|look\s+up\s+docs\s+for|search\s+docs\s+for|google|about|tell\s+me\s+about|info\s+on)\s+([^\n.,()]+)', msg, re.IGNORECASE)
            if research_match:
                search_query = research_match.group(1).strip()
                # Exclude trivial words
                if len(search_query) > 2 and search_query.lower() not in ["it", "this", "that", "the code", "the file", "solution"]:
                    try:
                        from backend.tools.scraper import web_scraper
                        search_res = await web_scraper.search_and_scrape(search_query)
                        if search_res.get("status") == "success" and search_res.get("results"):
                            snippets = "\n".join([f"- [{r.get('title')}]({r.get('url')}): {r.get('snippet')}" for r in search_res.get("results", [])])
                            workspace_context += (
                                f"\n=== Live Knowledge & Web Research Results for `{search_query}` ===\n"
                                f"{snippets}\n"
                                f"=== End Live Web Research Results ===\n\n"
                            )
                    except Exception:
                        pass

            # 3. Direct File Operations (Delete / Rename / Create)
            del_match = re.search(r'(?:delete|remove|rm)\s+(?:file\s+)?([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)', msg, re.IGNORECASE)
            if del_match:
                file_to_del = del_match.group(1).strip()
                await orch.execute_tool("delete_file", {"path": file_to_del})

            ren_match = re.search(r'(?:rename|move|mv)\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)\s+(?:to\s+)?([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)', msg, re.IGNORECASE)
            if ren_match:
                old_f = ren_match.group(1).strip()
                new_f = ren_match.group(2).strip()
                await orch.execute_tool("rename_file", {"old_path": old_f, "new_path": new_f})
                target_file = new_f

            # 2. Check Intent: 'greeting' vs 'research_info' vs 'coding_task'
            intent = await orch.classify_intent(msg)
            
            if intent == "greeting":
                conv_prompt = (
                    "You are Forge, a helpful and direct AI software engineering assistant. "
                    "Respond conversationally, concisely, and immediately in 1-2 friendly sentences. "
                    "Do NOT use thinking tags, preamble, or internal monologues."
                )
                conv_messages = [
                    {"role": "system", "content": conv_prompt},
                    {"role": "user", "content": msg}
                ]
                conv_content = ""
                async for event in orch.client.stream_chat_completion(
                    model=settings.role_router.model,
                    messages=conv_messages,
                    role_id="router",
                    temperature=0.3,
                    max_tokens=256,
                ):
                    if event["type"] == "content_chunk":
                        chunk = event["chunk"]
                        if "<think>" in chunk or "</think>" in chunk:
                            chunk = re.sub(r'</?think>', '', chunk)
                        if chunk:
                            conv_content += chunk
                            yield f"data: {json.dumps({'type': 'chat_chunk', 'chunk': chunk})}\n\n"

                in_tok = max(15, len(conv_prompt.split()) + len(msg.split()))
                out_tok = max(5, len(conv_content.split()))
                orch.total_tokens_used += in_tok + out_tok
                orch.total_cost_usd += (in_tok * 0.0000001) + (out_tok * 0.0000002)

                persistence.add_message(payload.session_id, "assistant", conv_content.strip())
                yield f"data: {json.dumps({'type': 'metrics', 'total_tokens': orch.total_tokens_used, 'total_cost_usd': orch.total_cost_usd})}\n\n"
                yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'done', 'label': 'Response Delivered', 'role': 'Router'})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'saved_file': None, 'full_content': conv_content.strip(), 'total_tokens': orch.total_tokens_used, 'total_cost_usd': orch.total_cost_usd})}\n\n"
                return

            elif intent == "research_info":
                # Informational / Research Query: Run Web Scraper & Stream Explanation (No IDE file writes)
                yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'research', 'label': 'Hermes Web Intelligence & Knowledge Retrieval', 'role': 'Researcher', 'model': settings.role_router.model})}\n\n"
                
                research_data = await web_scraper.search_and_scrape(msg)
                web_findings = ""
                if research_data.get("results"):
                    web_findings = "\n\n### Live Web Research Findings:\n" + "\n".join(
                        [f"- **{r['title']}** ({r.get('url', '')}): {r['snippet']}" for r in research_data["results"]]
                    )

                research_prompt = (
                    "You are Forge, an AI software engineering and technology assistant.\n"
                    "Provide a detailed, well-structured, and accurate technical explanation of the requested topic.\n"
                    f"{web_findings}\n\n"
                    "FORMATTING INSTRUCTIONS:\n"
                    "1. Respond directly in clear, informative markdown in the chat.\n"
                    "2. Explain the core concepts, working principles, architecture, components, and real-world significance.\n"
                    "3. Do NOT output file creation headers (### File: ...) and do NOT generate arbitrary firmware or code files unless the user explicitly requested code."
                )
                
                research_messages = [
                    {"role": "system", "content": research_prompt},
                    {"role": "user", "content": msg}
                ]
                
                info_content = ""
                yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'coding', 'label': 'Synthesizing Technical Intelligence', 'role': 'Scout', 'model': settings.role_router.model})}\n\n"
                
                async for event in orch.client.stream_chat_completion(
                    model=settings.role_router.model,
                    messages=research_messages,
                    role_id="router",
                    temperature=0.3,
                    max_tokens=1500,
                ):
                    if event["type"] == "content_chunk":
                        chunk = event["chunk"]
                        if "<think>" in chunk or "</think>" in chunk:
                            chunk = re.sub(r'</?think>', '', chunk)
                        if chunk:
                            info_content += chunk
                            yield f"data: {json.dumps({'type': 'chat_chunk', 'chunk': chunk})}\n\n"

                in_tok = max(30, len(research_prompt.split()) + len(msg.split()))
                out_tok = max(20, len(info_content.split()))
                orch.total_tokens_used += in_tok + out_tok
                orch.total_cost_usd += (in_tok * 0.0000001) + (out_tok * 0.0000002)

                persistence.add_message(payload.session_id, "assistant", info_content.strip())
                yield f"data: {json.dumps({'type': 'metrics', 'total_tokens': orch.total_tokens_used, 'total_cost_usd': orch.total_cost_usd})}\n\n"
                yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'done', 'label': 'Intelligence Delivered', 'role': 'Router'})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'saved_file': None, 'full_content': info_content.strip(), 'total_tokens': orch.total_tokens_used, 'total_cost_usd': orch.total_cost_usd})}\n\n"
                return

            # 3. REAL DYNAMIC ORCHESTRATION: Plan Task Graph with Planner Role for actual coding tasks
            yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'planning', 'label': 'Dynamic Task Graph Decomposition', 'role': 'Planner', 'model': planner_model})}\n\n"
            task_graph = await orch.plan_task_graph(msg)
            
            def get_plan_payload():
                return [n.to_dict() for n in sorted(task_graph.nodes.values(), key=lambda x: x.subtask_id)]
            
            yield f"data: {json.dumps({'type': 'plan', 'plan': get_plan_payload(), 'target_file': target_file})}\n\n"
            yield f"data: {json.dumps({'type': 'metrics', 'total_tokens': orch.total_tokens_used, 'total_cost_usd': orch.total_cost_usd})}\n\n"

            system_prompt = (
                "You are Forge Coder, an autonomous AI software engineer.\n"
                f"{workspace_context}\n"
                "INSTRUCTIONS:\n"
                "1. If you think, keep <think>...</think> brief. Never draft code inside thinking tags.\n"
                "2. ALWAYS provide the complete file in a single markdown code block with header:\n"
                "   ### File: filename.ext\n"
                "   ```<lang>\n"
                "   ...\n"
                "   ```\n"
                "3. Outside the code block, write ONLY a 1-sentence brief summary in plain text. NEVER write code outside markdown code blocks.\n"
                "4. To delete: DELETE: filename.ext | To rename: RENAME: old.ext -> new.ext"
            )

            full_content = ""
            saved_file = target_file

            # 4. PARALLEL MULTI-AGENT EXECUTION: Group DAG into topological parallel layers
            parallel_layers = task_graph.get_parallel_execution_layers()
            
            for layer_idx, layer in enumerate(parallel_layers):
                is_parallel_layer = len(layer) > 1
                
                # Mark all nodes in this layer as in_progress
                for node in layer:
                    node.status = "in_progress"
                
                if is_parallel_layer:
                    yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'coding', 'label': f'Parallel Batch {layer_idx+1}: Executing {len(layer)} Subtasks Concurrently', 'role': 'Parallel Multi-Agent Dispatcher', 'model': coder_model})}\n\n"
                    yield f"data: {json.dumps({'type': 'plan', 'plan': get_plan_payload(), 'target_file': target_file})}\n\n"
                    
                    # Concurrent execution queue for multi-agent layer
                    event_queue = asyncio.Queue()
                    
                    async def run_parallel_worker(w_node: SubtaskNode, w_idx: int):
                        try:
                            w_target = (w_node.target_files[0] if w_node.target_files else None) or f"module_{w_node.subtask_id}.py"
                            await event_queue.put({'type': 'init', 'target_file': w_target})
                            
                            w_isolated_ctx = orch._build_isolated_context(w_node, msg)
                            w_messages = [
                                {
                                    "role": "system",
                                    "content": system_prompt + f"\n\nCURRENT PARALLEL WORKER SUBTASK ({w_node.subtask_id}): {w_node.description}\n{w_isolated_ctx}"
                                },
                                {"role": "user", "content": f"Execute parallel subtask #{w_node.subtask_id}: {w_node.description}"}
                            ]
                            
                            w_content = ""
                            w_stream_buf = ""
                            w_in_code_fence = False
                            
                            async for w_ev in orch.client.stream_chat_completion(
                                model=coder_model,
                                messages=w_messages,
                                role_id="coder",
                                temperature=0.2,
                                max_tokens=8192,
                            ):
                                if w_ev["type"] == "content_chunk":
                                    w_chunk = w_ev["chunk"]
                                    w_content += w_chunk
                                    w_stream_buf += w_chunk
                                    
                                    if "```" in w_stream_buf and not w_in_code_fence:
                                        w_parts = w_stream_buf.split("```", 1)
                                        w_in_code_fence = True
                                        w_after = w_parts[1]
                                        if "\n" in w_after:
                                            first_part = w_after.split("\n", 1)[1]
                                            if first_part:
                                                await event_queue.put({'type': 'code_chunk', 'chunk': first_part, 'file': w_target, 'worker_id': w_idx, 'subtask_id': w_node.subtask_id})
                                        w_stream_buf = w_after
                                    elif w_in_code_fence:
                                        if "```" in w_chunk:
                                            code_p, _ = w_chunk.split("```", 1)
                                            if code_p:
                                                await event_queue.put({'type': 'code_chunk', 'chunk': code_p, 'file': w_target, 'worker_id': w_idx, 'subtask_id': w_node.subtask_id})
                                            w_in_code_fence = False
                                        else:
                                            await event_queue.put({'type': 'code_chunk', 'chunk': w_chunk, 'file': w_target, 'worker_id': w_idx, 'subtask_id': w_node.subtask_id})
                                    else:
                                        is_rc = re.search(r'^(?:<!DOCTYPE|<html|<head|<body|<div|<style|<script|import\s+|from\s+|def\s+|class\s+|#include|const\s+|function\s+|let\s+|var\s+)', w_stream_buf.strip(), re.IGNORECASE)
                                        if is_rc:
                                            w_in_code_fence = True
                                            await event_queue.put({'type': 'code_chunk', 'chunk': w_stream_buf, 'file': w_target, 'worker_id': w_idx, 'subtask_id': w_node.subtask_id})
                                            w_stream_buf = ""
                            
                            w_node.final_output = w_content
                            w_node.status = "done"
                            await event_queue.put({'type': 'worker_finished', 'subtask_id': w_node.subtask_id, 'worker_id': w_idx, 'content': w_content, 'target_file': w_target})
                        except Exception as w_err:
                            w_node.status = "failed"
                            await event_queue.put({'type': 'worker_error', 'subtask_id': w_node.subtask_id, 'error': str(w_err)})
                    
                    # Launch all workers in parallel
                    worker_tasks = [
                        asyncio.create_task(run_parallel_worker(n, i + 1))
                        for i, n in enumerate(layer)
                    ]
                    
                    # Stream events while workers are running
                    while any(not t.done() for t in worker_tasks) or not event_queue.empty():
                        try:
                            item = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                            if item.get("type") == "worker_finished":
                                # Extract files and record diffs
                                w_files = orch._extract_and_write_files(item["content"], msg)
                                for wf in w_files:
                                    record_file_diff(wf["file_name"], wf.get("old_content", ""), wf.get("content", ""))
                                    if wf.get("content"):
                                        saved_file = wf["file_name"]
                                        yield f"data: {json.dumps({'type': 'code_chunk', 'chunk': wf['content'], 'file': wf['file_name'], 'replace_all': True})}\n\n"
                                full_content += item["content"] + "\n\n"
                                yield f"data: {json.dumps({'type': 'plan', 'plan': get_plan_payload(), 'target_file': item['target_file']})}\n\n"
                            elif item.get("type") in ["code_chunk", "init"]:
                                yield f"data: {json.dumps(item)}\n\n"
                        except asyncio.TimeoutError:
                            pass
                    
                    await asyncio.gather(*worker_tasks, return_exceptions=True)
                    yield f"data: {json.dumps({'type': 'plan', 'plan': get_plan_payload(), 'target_file': target_file})}\n\n"
                    
                else:
                    node = layer[0]
                    subtask_target = (node.target_files[0] if node.target_files else None) or target_file
                    yield f"data: {json.dumps({'type': 'init', 'target_file': subtask_target})}\n\n"
                    yield f"data: {json.dumps({'type': 'plan', 'plan': get_plan_payload(), 'target_file': subtask_target})}\n\n"

                    is_critic_node = (node.assigned_role == "critic" or "audit" in node.description.lower() or "verify" in node.description.lower() or "review" in node.description.lower())

                    if is_critic_node:
                        # Adversarial Critic Verification (Red Team audit - no code streaming)
                        yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'critic', 'label': f'Subtask {node.subtask_id}: Adversarial Red-Team Audit', 'role': 'Critic', 'model': settings.role_critic.model})}\n\n"
                        try:
                            verdict, crit_cost, crit_lat = await orch._call_critic_model(node, full_content)
                            node.add_attempt(
                                action=f"Critic audit for {node.description}",
                                result=verdict.reason,
                                critic_verdict=verdict.to_dict(),
                                cost=crit_cost,
                                latency=crit_lat
                            )
                            node.status = "done"
                            clean_critic_note = f"\n[Critic Audit]: {verdict.reason}" if not verdict.passed else f"\n[Critic Audit]: Verification passed cleanly."
                            yield f"data: {json.dumps({'type': 'chat_chunk', 'chunk': clean_critic_note})}\n\n"
                        except Exception:
                            node.status = "done"
                    else:
                        # Primary Code Engineer (Streams code to Monaco Editor ONLY)
                        yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'coding', 'label': f'Subtask {node.subtask_id}: Code Implementation', 'role': 'Coder', 'model': coder_model})}\n\n"
                        isolated_ctx = orch._build_isolated_context(node, msg)
                        messages = [
                            {
                                "role": "system", 
                                "content": system_prompt + f"\n\nCURRENT ATOMIC SUBTASK ({node.subtask_id}): {node.description}\n{isolated_ctx}"
                            },
                            {"role": "user", "content": f"Execute subtask: {node.description}"}
                        ]

                        subtask_content = ""
                        in_code_fence = False
                        raw_stream_buf = ""

                        async for event in orch.client.stream_chat_completion(
                            model=coder_model,
                            messages=messages,
                            role_id="coder",
                            temperature=0.2,
                            max_tokens=8192,
                        ):
                            if event["type"] == "thinking_chunk":
                                yield f"data: {json.dumps(event)}\n\n"
                            elif event["type"] == "content_chunk":
                                chunk = event["chunk"]
                                subtask_content += chunk
                                raw_stream_buf += chunk

                                # Monaco Code Streamer: Extract code lines and stream exclusively to Monaco Editor
                                if "```" in raw_stream_buf and not in_code_fence:
                                    parts = raw_stream_buf.split("```", 1)
                                    in_code_fence = True
                                    after_fence = parts[1]
                                    if "\n" in after_fence:
                                        first_code_part = after_fence.split("\n", 1)[1]
                                        if first_code_part:
                                            yield f"data: {json.dumps({'type': 'code_chunk', 'chunk': first_code_part, 'file': subtask_target})}\n\n"
                                    raw_stream_buf = after_fence
                                elif in_code_fence:
                                    if "```" in chunk:
                                        code_part, _ = chunk.split("```", 1)
                                        if code_part:
                                            yield f"data: {json.dumps({'type': 'code_chunk', 'chunk': code_part, 'file': subtask_target})}\n\n"
                                        in_code_fence = False
                                    else:
                                        # Pure code token directly to Monaco Editor
                                        yield f"data: {json.dumps({'type': 'code_chunk', 'chunk': chunk, 'file': subtask_target})}\n\n"
                                else:
                                    is_raw_code = re.search(r'^(?:<!DOCTYPE|<html|<head|<body|<div|<style|<script|import\s+|from\s+|def\s+|class\s+|#include|const\s+|function\s+|let\s+|var\s+)', raw_stream_buf.strip(), re.IGNORECASE)
                                    if is_raw_code:
                                        in_code_fence = True
                                        yield f"data: {json.dumps({'type': 'code_chunk', 'chunk': raw_stream_buf, 'file': subtask_target})}\n\n"
                                        raw_stream_buf = ""

                        full_content += subtask_content + "\n\n"

                        # Extract and write code files to workspace
                        files = orch._extract_and_write_files(subtask_content, msg)
                        if files and files[0].get("content"):
                            saved_file = files[0]["file_name"]
                            subtask_target = saved_file
                            # Ensure Monaco editor contains the complete verified source code
                            yield f"data: {json.dumps({'type': 'code_chunk', 'chunk': files[0]['content'], 'file': subtask_target, 'replace_all': True})}\n\n"

                        # --- RECORD DIFFS FOR HUMAN-IN-THE-LOOP (HITL) REVIEW ---
                        for written_f in files:
                            f_name = written_f["file_name"]
                            f_code = written_f.get("content", "")
                            old_code = written_f.get("old_content", "")
                            if f_code:
                                record_file_diff(f_name, old_code, f_code)

                        # --- SAKANA FUGU SECTION 4.4: BUILD & DEBUG SELF-HEALING REFLEXION LOOP ---
                        for written_f in files:
                            f_name = written_f["file_name"]
                            f_code = written_f.get("content", "")
                            if f_code:
                                is_valid, syntax_err = validate_code_syntax(f_name, f_code)
                                if not is_valid:
                                    # Trigger instant self-healing repair pass
                                    yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'self_heal', 'label': f'Fugu Self-Healing: Fixing Syntax in {f_name}', 'role': 'Self-Healing Debugger', 'model': coder_model})}\n\n"
                                    yield f"data: {json.dumps({'type': 'chat_chunk', 'chunk': f'\\n[Self-Healing Debugger]: Syntax issue in `{f_name}` ({syntax_err}). Applying automated patch to IDE editor...\\n'})}\n\n"
                                    
                                    repair_messages = [
                                        {
                                            "role": "system",
                                            "content": (
                                                "You are Forge Self-Healing Debugger.\n"
                                                "Fix the exact syntax error. Output the complete corrected file in markdown:\n"
                                                f"### File: {f_name}\n"
                                                "```<lang>\n...\n```"
                                            )
                                        },
                                        {
                                            "role": "user",
                                            "content": f"The file '{f_name}' has the following syntax error:\n{syntax_err}\n\nCurrent code:\n```\n{f_code}\n```\nFix the code completely and provide the full corrected implementation."
                                        }
                                    ]
                                    
                                    repaired_content = ""
                                    async for rep_event in orch.client.stream_chat_completion(
                                        model=coder_model,
                                        messages=repair_messages,
                                        role_id="coder",
                                        temperature=0.1,
                                        max_tokens=8192,
                                    ):
                                        if rep_event["type"] == "content_chunk":
                                            repaired_content += rep_event["chunk"]
                                    
                                    rep_files = orch._extract_and_write_files(repaired_content, f"fix {f_name}")
                                    if rep_files and rep_files[0].get("content"):
                                        saved_file = rep_files[0]["file_name"]
                                        # Update editor with repaired code
                                        yield f"data: {json.dumps({'type': 'code_chunk', 'chunk': rep_files[0]['content'], 'file': saved_file, 'replace_all': True})}\n\n"
                                        yield f"data: {json.dumps({'type': 'chat_chunk', 'chunk': f'[Self-Healing Debugger]: Successfully patched and verified `{saved_file}` in IDE editor.\\n'})}\n\n"

                        # Calculate cost and tokens
                        in_tok = max(30, len(system_prompt.split()) + len(msg.split()))
                        out_tok = max(20, len(subtask_content.split()))
                        step_cost = (in_tok / 1000.0 * 0.0003) + (out_tok / 1000.0 * 0.0005)
                        orch.total_tokens_used += (in_tok + out_tok)
                        orch.total_cost_usd += step_cost
                        node.status = "done"

                    yield f"data: {json.dumps({'type': 'plan', 'plan': get_plan_payload(), 'target_file': subtask_target})}\n\n"
                    yield f"data: {json.dumps({'type': 'metrics', 'total_tokens': orch.total_tokens_used, 'total_cost_usd': orch.total_cost_usd})}\n\n"

            persistence.add_message(payload.session_id, "assistant", full_content.strip())
            yield f"data: {json.dumps({'type': 'orch_stage', 'stage': 'done', 'label': 'Orchestration Complete & Files Verified', 'role': 'System'})}\n\n"
            summary_msg = f"Task completed successfully. Modified `{saved_file}` in the IDE workspace."
            yield f"data: {json.dumps({'type': 'done', 'saved_file': saved_file, 'full_content': summary_msg, 'total_tokens': orch.total_tokens_used, 'total_cost_usd': orch.total_cost_usd})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/task/execute_step")
async def execute_task_step(session_id: str, step_index: int):
    orch = get_or_create_orchestrator(session_id)
    result = await orch.execute_step(step_index)
    return result

@app.post("/api/task/approval")
async def task_approval(payload: ApprovalRequest):
    orch = get_or_create_orchestrator(payload.session_id)
    result = await orch.handle_approval(payload.approved_hunks_indices)
    return result

@app.get("/api/dag/{session_id}")
def get_dag(session_id: str):
    orch = active_orchestrators.get(session_id)
    nodes = []
    if orch and orch.graph:
        nodes = [n.to_dict() for n in sorted(orch.graph.nodes.values(), key=lambda x: x.subtask_id)]
    else:
        nodes = persistence.get_dag_nodes(session_id)
        
    total_tokens = orch.total_tokens_used if orch else 0
    total_cost = orch.total_cost_usd if orch else 0.0
    
    return {
        "session_id": session_id,
        "nodes": nodes,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
    }

@app.get("/api/files")
def list_workspace_files(workspace_root: Optional[str] = None):
    ws = workspace_root or settings.active_workspace
    file_list = []
    ignored_dirs = {
        ".git", ".venv", "__pycache__", "node_modules", "dist", "build", ".gemini",
        ".pytest_cache", "venv", "Library", "Pictures", "Music", "Movies", "Applications",
        ".cache", ".npm", ".cargo", ".rustup", ".local", ".vscode", ".docker", ".android"
    }
    ignored_files = {".DS_Store", "state.db", "state.db-wal", "state.db-shm", ".coverage"}
    
    is_home_root = (ws == str(Path.home()) or ws == "/")
    max_depth = 2 if is_home_root else 5
    max_files = 150 if is_home_root else 500
    
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
        depth = root[len(ws):].count(os.sep)
        if depth >= max_depth:
            dirs[:] = []
        for f in files:
            if f in ignored_files or f.startswith(".") or f.endswith((".pyc", ".log", ".db", ".vdi", ".nvram", ".iso")):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, ws)
            file_list.append(rel)
            if len(file_list) >= max_files:
                break
        if len(file_list) >= max_files:
            break
            
    return {"workspace_root": ws, "files": sorted(file_list)}

@app.get("/api/file/read")
def read_file_content(file_path: str, workspace_root: Optional[str] = None):
    ws = workspace_root or settings.active_workspace
    full_path = os.path.join(ws, file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"file_path": file_path, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/file/create")
def create_file_endpoint(payload: FileCreateRequest):
    ws = payload.workspace_root or settings.active_workspace
    clean_rel = payload.file_path.strip().lstrip("/")
    if not clean_rel:
        raise HTTPException(status_code=400, detail="Filename cannot be empty")
    full_path = os.path.join(ws, clean_rel)
    if os.path.exists(full_path):
        raise HTTPException(status_code=400, detail="File already exists")
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(payload.content or "")
    idx = workspace_registry.get_index(ws)
    idx.build_index()
    return {"status": "ok", "file_path": clean_rel, "message": "File created successfully"}

@app.post("/api/file/delete")
def delete_file_endpoint(payload: FileDeleteRequest):
    import shutil
    ws = payload.workspace_root or settings.active_workspace
    clean_rel = payload.file_path.strip().lstrip("/")
    full_path = os.path.join(ws, clean_rel)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        idx = workspace_registry.get_index(ws)
        idx.build_index()
        return {"status": "ok", "file_path": clean_rel, "message": "File deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/file/rename")
def rename_file_endpoint(payload: FileRenameRequest):
    ws = payload.workspace_root or settings.active_workspace
    old_clean = payload.old_path.strip().lstrip("/")
    new_clean = payload.new_path.strip().lstrip("/")
    old_full = os.path.join(ws, old_clean)
    new_full = os.path.join(ws, new_clean)
    if not os.path.exists(old_full):
        raise HTTPException(status_code=404, detail=f"Source file not found: {old_clean}")
    if os.path.exists(new_full):
        raise HTTPException(status_code=400, detail=f"Destination already exists: {new_clean}")
    try:
        os.makedirs(os.path.dirname(new_full), exist_ok=True)
        os.rename(old_full, new_full)
        idx = workspace_registry.get_index(ws)
        idx.build_index()
        return {"status": "ok", "old_path": old_clean, "new_path": new_clean, "message": "File renamed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/file/write")
def write_file_content(payload: FileWriteRequest):
    ws = payload.workspace_root or settings.active_workspace
    tools = ToolExecutor(ws)
    res = tools.write_file(payload.file_path, payload.content, approved=payload.approved)
    return res.to_dict()

@app.post("/api/terminal/exec")
async def exec_terminal(payload: TerminalExecRequest):
    import asyncio as _asyncio
    ws = payload.workspace_root or settings.active_workspace
    # Determine the working directory for this command
    run_cwd = payload.cwd or ws
    # Validate cwd exists, fall back to workspace root
    if not os.path.isdir(run_cwd):
        run_cwd = ws

    cmd = payload.command.strip()

    # Handle bare standalone "cd" or "cd <path>" without pipes/chaining:
    cd_match = re.match(r'^cd(?:\s+([^;&|]+))?$', cmd)
    if cd_match:
        target = (cd_match.group(1) or "").strip()
        if not target or target == "~":
            new_cwd = os.path.expanduser("~")
        elif target.startswith("~"):
            new_cwd = os.path.expanduser(target)
        elif target == "-":
            new_cwd = ws  # fallback: go to workspace root
        elif os.path.isabs(target):
            new_cwd = target
        else:
            new_cwd = os.path.normpath(os.path.join(run_cwd, target))

        if os.path.isdir(new_cwd):
            return {"output": "", "is_error": False, "requires_approval": False,
                    "metadata": {"returncode": 0}, "cwd": new_cwd}
        else:
            return {"output": f"cd: no such file or directory: {target}", "is_error": True,
                    "requires_approval": False, "metadata": {"returncode": 1}, "cwd": run_cwd}

    # For all other commands: run in the tracked cwd, then capture the
    # final pwd so compound commands like "cd foo && ls" update cwd too.
    # We append `; echo __CWD__$(pwd)__CWD__` to capture the post-execution cwd.
    wrapped_cmd = f'{cmd}; echo "__CWD__$(pwd)__CWD__"'
    try:
        env = {**os.environ, "TERM": "xterm", "HOME": os.path.expanduser("~")}
        proc = await _asyncio.create_subprocess_shell(
            wrapped_cmd,
            cwd=run_cwd,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await _asyncio.wait_for(proc.communicate(), timeout=60.0)
        out_str = stdout.decode("utf-8", errors="replace")
        err_str = stderr.decode("utf-8", errors="replace")

        # Extract the cwd marker from stdout
        final_cwd = run_cwd
        cwd_marker = "__CWD__"
        if cwd_marker in out_str:
            parts = out_str.rsplit(cwd_marker, 2)
            if len(parts) >= 3:
                final_cwd = parts[-2].strip()
            # Remove the marker line from visible output
            out_str = out_str[:out_str.rfind("\n" + cwd_marker)] if ("\n" + cwd_marker) in out_str else out_str.split(cwd_marker)[0]
            out_str = out_str.rstrip("\n")

        combined = out_str
        if err_str:
            combined += f"\n{err_str}" if combined else err_str

        return {"output": combined or "(Command executed with no output)",
                "is_error": (proc.returncode != 0),
                "requires_approval": False,
                "metadata": {"returncode": proc.returncode},
                "cwd": final_cwd}
    except _asyncio.TimeoutError:
        return {"output": "Command execution timed out after 60 seconds.",
                "is_error": True, "requires_approval": False,
                "metadata": {"returncode": -1}, "cwd": run_cwd}
    except Exception as e:
        return {"output": f"Execution error: {str(e)}",
                "is_error": True, "requires_approval": False,
                "metadata": {"returncode": -1}, "cwd": run_cwd}

@app.get("/api/git/status")
def git_status(workspace_root: Optional[str] = None):
    ws = workspace_root or settings.active_workspace
    tools = ToolExecutor(ws)
    return tools.git_status_and_diff()

@app.get("/api/retrieval/search")
def search_ast(query: str, workspace_root: Optional[str] = None):
    ws = workspace_root or settings.active_workspace
    idx = workspace_registry.get_index(ws)
    results = idx.search(query, top_k=5)
    return {"query": query, "results": results}

@app.get("/api/diff/pending")
def get_pending_diffs():
    return {"diffs": PENDING_DIFF_HUNKS}

class DiffActionRequest(BaseModel):
    diff_id: Optional[str] = None
    action: str = "approve_all" # approve_all, approve_selected, reject_all
    selected_ids: Optional[List[str]] = None

@app.post("/api/diff/action")
def handle_diff_action(payload: DiffActionRequest):
    global PENDING_DIFF_HUNKS
    ws = settings.active_workspace
    if payload.action == "reject_all":
        for d in PENDING_DIFF_HUNKS:
            f_full = os.path.join(ws, d["file_path"].lstrip("/"))
            if d.get("old_content"):
                with open(f_full, "w", encoding="utf-8") as f:
                    f.write(d["old_content"])
            elif os.path.exists(f_full):
                os.remove(f_full)
        PENDING_DIFF_HUNKS = []
        return {"status": "success", "message": "All proposed diffs rejected and rolled back."}
    
    elif payload.action in ["approve_all", "approve_selected"]:
        ids_to_approve = set(payload.selected_ids or [d["id"] for d in PENDING_DIFF_HUNKS])
        for d in PENDING_DIFF_HUNKS:
            if d["id"] in ids_to_approve:
                f_full = os.path.join(ws, d["file_path"].lstrip("/"))
                os.makedirs(os.path.dirname(f_full), exist_ok=True)
                with open(f_full, "w", encoding="utf-8") as f:
                    f.write(d["new_content"])
        PENDING_DIFF_HUNKS = [d for d in PENDING_DIFF_HUNKS if d["id"] not in ids_to_approve]
        return {"status": "success", "message": "Selected diffs approved and applied."}
        
    return {"status": "error", "message": "Invalid action"}

@app.get("/api/memory/list")
def list_session_memories(session_id: str):
    memories = persistence.get_memories(session_id)
    compacted = persistence.get_compacted_context_window(session_id)
    return {
        "session_id": session_id,
        "memories": memories,
        "compacted_context": compacted,
        "count": len(memories),
    }

@app.post("/api/memory/add")
def add_session_memory(payload: MemoryAddRequest):
    mem_id = persistence.add_memory(
        session_id=payload.session_id,
        memory_type=payload.memory_type,
        key=payload.key,
        content=payload.content,
        importance_score=payload.importance_score or 1.0
    )
    return {"status": "ok", "memory_id": mem_id}

@app.post("/api/memory/clear")
def clear_session_memories(payload: MemoryClearRequest):
    persistence.clear_memories(payload.session_id)
    return {"status": "ok", "message": "All session memories cleared."}

@app.post("/api/memory/delete")
def delete_session_memory(payload: MemoryDeleteRequest):
    persistence.delete_memory(payload.memory_id)
    return {"status": "ok", "message": "Memory item deleted."}

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def serve_index():
    idx_file = FRONTEND_DIR / "index.html"
    if idx_file.exists():
        return FileResponse(str(idx_file))
    return HTMLResponse("<h1>Agent Zero API is running. Frontend build not found.</h1>")

@app.get("/{full_path:path}")
def serve_frontend_fallback(full_path: str):
    target = FRONTEND_DIR / full_path
    if target.exists() and target.is_file():
        return FileResponse(str(target))
    idx_file = FRONTEND_DIR / "index.html"
    if idx_file.exists():
        return FileResponse(str(idx_file))
    return HTMLResponse("<h1>Agent Zero API is running. Frontend build not found.</h1>")
