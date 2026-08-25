import os
import re
import json
import time
import uuid
import hashlib
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple

from backend.config import settings
from backend.models.nim_client import NIMClient
from backend.models.worker_pool import worker_pool, WorkerAgentSpec
from backend.indexer.ast_retriever import workspace_registry
from backend.tools.executor import ToolExecutor
from backend.tools.scraper import web_scraper
from backend.orchestrator.persistence import persistence
from backend.orchestrator.task_graph import TaskGraph, SubtaskNode

MAX_RETRIES_PER_SUBTASK = 3
MAX_REPLANS_PER_TASK = 2
MAX_SPAWN_DEPTH = 2
MAX_GLOBAL_CALLS = 18
COST_SAFETY_LIMIT_USD = 0.45

class FileLockManager:
    def __init__(self):
        self._locks: Set[str] = set()

    def acquire(self, file_path: str) -> bool:
        norm = os.path.normpath(file_path)
        if norm in self._locks:
            return False
        self._locks.add(norm)
        return True

    def release(self, file_path: str):
        norm = os.path.normpath(file_path)
        self._locks.discard(norm)

    def is_locked(self, file_path: str) -> bool:
        return os.path.normpath(file_path) in self._locks


class StructuredCriticVerdict:
    def __init__(self, passed: bool, reason: str, suggested_fix_category: str):
        self.passed = passed
        self.reason = reason
        self.suggested_fix_category = suggested_fix_category

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "suggested_fix_category": self.suggested_fix_category,
        }

    @classmethod
    def from_text(cls, text: str) -> "StructuredCriticVerdict":
        try:
            cleaned = text
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            
            # Find JSON block if extra text exists
            match = re.search(r'\{[^{}]*"passed"[^{}]*\}', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)
                
            data = json.loads(cleaned)
            passed = bool(data.get("passed", False))
            reason = str(data.get("reason", "No reason provided"))
            category = str(data.get("suggested_fix_category", "wrong_approach" if not passed else "none"))
            return cls(passed=passed, reason=reason, suggested_fix_category=category)
        except Exception:
            lower = text.lower()
            passed = ("pass" in lower or "looks good" in lower or "correct" in lower) and "fail" not in lower
            category = "none" if passed else ("syntax_error" if "syntax" in lower else "wrong_approach")
            return cls(passed=passed, reason=text[:200], suggested_fix_category=category)


class DeterministicOrchestrator:
    def __init__(self, session_id: str, workspace_root: Optional[str] = None):
        self.session_id = session_id
        self.workspace_root = workspace_root or settings.active_workspace
        self.client = NIMClient()
        self.tools = ToolExecutor(workspace_root=self.workspace_root)
        self.file_locks = FileLockManager()
        
        self.graph: Optional[TaskGraph] = None
        self.action_history_hashes: Dict[str, int] = {}
        self.total_llm_calls: int = 0
        self.total_tokens_used: int = 0
        self.total_cost_usd: float = 0.0
        self.is_halted: bool = False
        self.halt_reason: str = ""
        
        persistence.create_session(self.session_id, self.workspace_root)

    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = tool_name.lower().strip()
        
        if tool_name in ["create_file", "write_file"]:
            path = args.get("path") or args.get("file_path") or args.get("filename") or "solution.py"
            content = args.get("content", "")
            res = self.tools.write_file(path, content, approved=True)
            workspace_registry.get_index(self.workspace_root).build_index()
            return {"status": "success", "tool": tool_name, "path": path, "message": res.output}
            
        elif tool_name in ["delete_file", "remove_file", "rm"]:
            path = args.get("path") or args.get("file_path") or args.get("filename")
            if not path:
                return {"status": "error", "error": "No file path provided"}
            full_path = os.path.join(self.workspace_root, path.lstrip("/"))
            if os.path.exists(full_path):
                import shutil
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                else:
                    os.remove(full_path)
                workspace_registry.get_index(self.workspace_root).build_index()
                return {"status": "success", "tool": "delete_file", "path": path, "message": f"Successfully deleted {path}"}
            return {"status": "error", "error": f"File not found: {path}"}
            
        elif tool_name in ["rename_file", "move_file", "mv"]:
            old_path = args.get("old_path") or args.get("src") or args.get("source")
            new_path = args.get("new_path") or args.get("dst") or args.get("destination") or args.get("target")
            if not old_path or not new_path:
                return {"status": "error", "error": "Both old_path and new_path are required"}
            old_full = os.path.join(self.workspace_root, old_path.lstrip("/"))
            new_full = os.path.join(self.workspace_root, new_path.lstrip("/"))
            if os.path.exists(old_full):
                os.makedirs(os.path.dirname(new_full), exist_ok=True)
                os.rename(old_full, new_full)
                workspace_registry.get_index(self.workspace_root).build_index()
                return {"status": "success", "tool": "rename_file", "old_path": old_path, "new_path": new_path, "message": f"Renamed {old_path} to {new_path}"}
            return {"status": "error", "error": f"Source file not found: {old_path}"}
            
        elif tool_name in ["web_scrape", "scrape_url", "fetch_url"]:
            url = args.get("url") or args.get("link")
            if not url:
                return {"status": "error", "error": "No URL provided"}
            scrape_res = await web_scraper.scrape_url(url)
            return scrape_res
            
        elif tool_name in ["web_search", "search_web", "google", "search"]:
            query = args.get("query") or args.get("q")
            if not query:
                return {"status": "error", "error": "No search query provided"}
            search_res = await web_scraper.search_and_scrape(query)
            return search_res
            
        elif tool_name in ["bash", "sh", "terminal", "exec"]:
            cmd = args.get("command") or args.get("cmd")
            if not cmd:
                return {"status": "error", "error": "No command provided"}
            res = await self.tools.execute_bash(cmd, approved=True)
            return {"status": "success" if not res.is_error else "error", "output": res.output}
            
        return {"status": "error", "error": f"Unknown tool: {tool_name}"}

    def _calculate_call_cost(self, worker: WorkerAgentSpec, in_tok: int, out_tok: int) -> float:
        return (in_tok / 1000.0 * worker.cost_per_1k_input) + (out_tok / 1000.0 * worker.cost_per_1k_output)

    def _get_filtered_agents_md(self, subtask_desc: str) -> str:
        p = os.path.join(self.workspace_root, "AGENTS.md")
        if not os.path.exists(p):
            return ""
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read().strip()
            # If long, filter to sections matching keywords
            if len(content) > 1200:
                lines = content.splitlines()
                relevant = [l for l in lines if any(k in l.lower() for k in subtask_desc.lower().split()[:5])]
                return "\n".join(relevant[:15])
            return content
        except Exception:
            return ""

    def _hash_action(self, subtask_id: int, action_type: str, error_sig: str) -> str:
        raw = f"{subtask_id}:{action_type}:{error_sig.strip()[:100]}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    async def is_conversational(self, msg: str) -> bool:
        cleaned = msg.strip().lower()
        cleaned_no_punct = re.sub(r'[^\w\s]', '', cleaned).strip()
        
        # 1. Pure Greetings and short chit-chat (ONLY if standalone greeting)
        greetings = ("hello", "hi", "hey", "howdy", "good morning", "good evening", "how are you", "who are you", "what are you", "help", "thanks", "thank you", "bye", "goodbye")
        if cleaned_no_punct in greetings:
            return True

        # 2. Strong coding action keywords: ALWAYS trigger full agentic workflow
        coding_verbs = [
            "write", "create", "build", "implement", "code", "generate", "make",
            "design", "solve", "develop", "fix", "add", "modify", "update", "refactor",
            "debug", "rewrite", "convert", "translate", "test", "run", "simulate"
        ]
        coding_nouns = [
            "calculator", "game", "app", "application", "server", "script", "program",
            "html", "css", "js", "javascript", "typescript", "python", "py", "java", "c", "cpp",
            "rust", "golang", "go", "sql", "api", "endpoint", "function", "class", "module",
            "file", "component", "algorithm", "solution", "crawler", "scraper", "blog",
            "page", "site", "website", "tool", "cli", "ui", "database", "model", "logic"
        ]
        has_coding_verb = any(re.search(r'\b' + v + r'\b', cleaned) for v in coding_verbs)
        has_coding_noun = any(re.search(r'\b' + n + r'\b', cleaned) for n in coding_nouns)
        has_file_ref = bool(re.search(r'[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+', cleaned))

        if has_coding_verb or has_coding_noun or has_file_ref:
            return False

        # 3. Informational & Explanatory Questions (e.g. "what is recursion?", "who is Ada Lovelace?")
        question_starters = (
            "what is", "what are", "why is", "why do", "how does", "explain", "describe",
            "who is", "who was", "when was", "where is", "difference between", "tell me about"
        )
        if any(cleaned_no_punct.startswith(qs) for qs in question_starters):
            return True

        # Default to agentic coding workflow if ambiguous
        return False

    async def execute_direct_chat(self, msg: str) -> Dict[str, Any]:
        worker = worker_pool.get_worker("fast_tool_agent")
        messages = [
            {"role": "system", "content": "You are Forge, a high-performance agentic coding assistant. Respond conversationally, clearly, and concisely."},
            {"role": "user", "content": msg}
        ]
        res = await self.client.chat_completion(
            model=worker.model,
            messages=messages,
            api_key=worker.api_key,
            role_id=worker.role_key,
            temperature=0.4,
            max_tokens=512,
        )
        in_tok = res.get("input_tokens", 0)
        out_tok = res.get("output_tokens", 0)
        call_cost = self._calculate_call_cost(worker, in_tok, out_tok)
        self.total_tokens_used += (in_tok + out_tok)
        self.total_cost_usd += call_cost
        
        return {
            "answer": res.get("content", "").strip(),
            "thinking": res.get("thinking", ""),
            "model": worker.model,
            "latency": res.get("latency_seconds", 0.0),
            "cost": call_cost,
        }

    async def plan_task_graph(self, user_goal: str) -> TaskGraph:
        planner_worker = worker_pool.get_worker("conductor")
        agents_md = self._get_filtered_agents_md(user_goal)
        
        system_prompt = (
            "You are the Master Task Planner for an autonomous agentic coding engine.\n"
            "Decompose the user's goal into a strict TaskGraph of small, single-outcome, atomic subtasks.\n"
            "Each subtask must be completable by a single small LLM call in one shot.\n\n"
            "Output JSON ONLY conforming to this schema:\n"
            "{\n"
            "  \"subtasks\": [\n"
            "    {\n"
            "      \"subtask_id\": 1,\n"
            "      \"description\": \"Specific single outcome...\",\n"
            "      \"assigned_role\": \"coder\",\n"
            "      \"target_files\": [\"filename.ext\"],\n"
            "      \"dependencies\": []\n"
            "    }\n"
            "  ]\n"
            "}"
        )
        if agents_md:
            system_prompt += f"\n\nProject AGENTS.md Context:\n{agents_md}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Plan task graph for: {user_goal}"}
        ]

        self.total_llm_calls += 1
        t0 = time.time()
        res = await self.client.chat_completion(
            model=planner_worker.model,
            messages=messages,
            api_key=planner_worker.api_key,
            role_id=planner_worker.role_key,
            temperature=0.1,
            max_tokens=384,
        )
        latency = time.time() - t0
        in_tok = res.get("input_tokens", 0)
        out_tok = res.get("output_tokens", 0)
        call_cost = self._calculate_call_cost(planner_worker, in_tok, out_tok)
        self.total_tokens_used += (in_tok + out_tok)
        self.total_cost_usd += call_cost

        graph = TaskGraph(task_id=str(uuid.uuid4()), user_goal=user_goal)
        try:
            cleaned = res.get("content", "")
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            raw_data = json.loads(cleaned)
            subtasks = raw_data.get("subtasks", [])
            for item in subtasks:
                raw_desc = str(item.get("description", "")).strip()
                if not raw_desc or "outcome" in raw_desc.lower() or "specific" in raw_desc.lower() or len(raw_desc) < 8:
                    clean_desc = f"Implement functionality for: {user_goal}"
                else:
                    clean_desc = raw_desc

                node = SubtaskNode(
                    subtask_id=int(item.get("subtask_id", len(graph.nodes) + 1)),
                    description=clean_desc,
                    assigned_role=item.get("assigned_role", "coder"),
                    dependencies=item.get("dependencies", []),
                    target_files=item.get("target_files", []),
                    depth=0,
                )
                graph.add_node(node)
        except Exception:
            # Fallback robust atomic DAG
            graph.add_node(SubtaskNode(1, f"Implement solution for: {user_goal}", "coder", dependencies=[]))
            graph.add_node(SubtaskNode(2, "Review and audit code for edge cases and regressions", "critic", dependencies=[1]))

        if not graph.nodes:
            graph.add_node(SubtaskNode(1, f"Implement solution for: {user_goal}", "coder", dependencies=[]))

        self.graph = graph
        return graph

    def _build_isolated_context(self, subtask: SubtaskNode, user_goal: str, retry_feedback: Optional[str] = None, reformulated_query: Optional[str] = None) -> str:
        search_query = reformulated_query or f"{user_goal} {subtask.description}"
        idx_engine = workspace_registry.get_index(self.workspace_root)
        search_results = idx_engine.search(search_query, top_k=2)
        code_chunks = "\n".join([r["formatted_chunk"] for r in search_results]) if search_results else ""
        
        filtered_agents_md = self._get_filtered_agents_md(subtask.description)
        
        ctx = f"### Overall Goal: {user_goal}\n### Subtask Target: {subtask.description}\n"
        if subtask.target_files:
            ctx += f"Target Files: {', '.join(subtask.target_files)}\n"
        if filtered_agents_md:
            ctx += f"\n=== Relevant AGENTS.md Guidelines ===\n{filtered_agents_md}\n"
        if code_chunks:
            ctx += f"\n=== Retrieved Codebase Slices ===\n{code_chunks}\n"
        if retry_feedback:
            ctx += f"\n=== Previous Attempt Failure Feedback (Fix Immediately) ===\n{retry_feedback}\n"
            
        return ctx

    async def _call_coder_model(self, subtask: SubtaskNode, context: str) -> Tuple[str, float, float]:
        coder_worker = worker_pool.get_worker("lead_engineer")
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are the Primary Code Engineer ({coder_worker.name}).\n"
                    "You receive ONLY the tightly-scoped context needed for this single subtask.\n"
                    "Complete this subtask in one shot. Output clean code or a unified diff patch."
                )
            },
            {"role": "user", "content": context}
        ]
        
        self.total_llm_calls += 1
        t0 = time.time()
        res = await self.client.chat_completion(
            model=coder_worker.model,
            messages=messages,
            api_key=coder_worker.api_key,
            role_id=coder_worker.role_key,
            temperature=0.2,
            max_tokens=512,
        )
        latency = time.time() - t0
        in_tok = res.get("input_tokens", 0)
        out_tok = res.get("output_tokens", 0)
        cost = self._calculate_call_cost(coder_worker, in_tok, out_tok)
        self.total_tokens_used += (in_tok + out_tok)
        self.total_cost_usd += cost
        
        return res.get("content", ""), cost, latency

    async def _call_critic_model(self, subtask: SubtaskNode, coder_output: str) -> Tuple[StructuredCriticVerdict, float, float]:
        critic_worker = worker_pool.get_worker("adversarial_debugger")
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an Adversarial Critic & Verifier (Red Team).\n"
                    "Evaluate whether the coder's implementation correctly solves the subtask.\n"
                    "Output JSON ONLY matching this schema:\n"
                    "{\n"
                    "  \"passed\": true,\n"
                    "  \"reason\": \"Analysis...\",\n"
                    "  \"suggested_fix_category\": \"none\"\n"
                    "}"
                )
            },
            {
                "role": "user",
                "content": f"Subtask: {subtask.description}\n\nCode:\n{coder_output}"
            }
        ]
        
        self.total_llm_calls += 1
        t0 = time.time()
        res = await self.client.chat_completion(
            model=critic_worker.model,
            messages=messages,
            api_key=critic_worker.api_key,
            role_id=critic_worker.role_key,
            temperature=0.1,
            max_tokens=180,
        )
        latency = time.time() - t0
        in_tok = res.get("input_tokens", 0)
        out_tok = res.get("output_tokens", 0)
        cost = self._calculate_call_cost(critic_worker, in_tok, out_tok)
        self.total_tokens_used += (in_tok + out_tok)
        self.total_cost_usd += cost
        
        verdict = StructuredCriticVerdict.from_text(res.get("content", ""))
        return verdict, cost, latency

    def _extract_and_write_files(self, text: str, user_goal: str) -> List[Dict[str, str]]:
        written_files = []
        
        # 1. Handle File Deletion (from model response or user goal)
        delete_patterns = [
            r'(?:delete|remove|rm)\s+(?:file\s+)?([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)',
            r'DELETE:\s*([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)',
            r'rm\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)',
        ]
        if any(w in user_goal.lower() for w in ["delete", "remove", "rm", "unlink"]):
            for pat in delete_patterns:
                for target in re.findall(pat, user_goal, re.IGNORECASE) + re.findall(pat, text, re.IGNORECASE):
                    target = target.strip().lstrip("./")
                    full = os.path.join(self.workspace_root, target)
                    if os.path.exists(full):
                        try:
                            if os.path.isdir(full):
                                import shutil
                                shutil.rmtree(full)
                            else:
                                os.remove(full)
                        except Exception:
                            pass

        # 2. Handle File Renaming / Move (from model response or user goal)
        rename_patterns = [
            r'(?:rename|move|mv)\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)\s+(?:to\s+)?([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)',
            r'RENAME:\s*([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)\s*->\s*([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)',
        ]
        if any(w in user_goal.lower() for w in ["rename", "move", "mv"]):
            for pat in rename_patterns:
                for src, dst in re.findall(pat, user_goal, re.IGNORECASE) + re.findall(pat, text, re.IGNORECASE):
                    src_clean = src.strip().lstrip("./")
                    dst_clean = dst.strip().lstrip("./")
                    src_full = os.path.join(self.workspace_root, src_clean)
                    dst_full = os.path.join(self.workspace_root, dst_clean)
                    if os.path.exists(src_full):
                        try:
                            os.makedirs(os.path.dirname(dst_full), exist_ok=True)
                            os.rename(src_full, dst_full)
                            written_files.append({"file_name": dst_clean, "content": ""})
                        except Exception:
                            pass

        # 3. Handle File Creation / Extraction from markdown
        file_blocks = re.findall(
            r'(?:###|\*\*|File:?|Filename:?)\s*([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)\s*[\*#]*\s*```[a-zA-Z0-9]*\n(.*?)```',
            text,
            re.DOTALL
        )
        if file_blocks:
            for fname, code in file_blocks:
                fname = fname.strip().lstrip("./")
                target_path = os.path.join(self.workspace_root, fname)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(code.strip())
                written_files.append({"file_name": fname, "content": code.strip()})

        if not written_files:
            code_matches = re.findall(r'```([a-zA-Z0-9_+\-]*)\n(.*?)```', text, re.DOTALL)
            if code_matches:
                lang, code = code_matches[0]
                code = code.strip()
                
                # Only write code if it is actual programming code and not bash tool output
                if lang.lower() not in ["bash", "sh", "shell", "json", "output"]:
                    ext_map = {
                        "rust": "rs", "rs": "rs", "go": "go", "golang": "go",
                        "typescript": "ts", "ts": "ts", "javascript": "js", "js": "js",
                        "python": "py", "py": "py", "cpp": "cpp", "c": "c",
                        "html": "html", "css": "css", "md": "md", "sql": "sql"
                    }
                    
                    explicit_file = re.findall(r'([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)', user_goal)
                    if explicit_file:
                        fname = explicit_file[0]
                    else:
                        ext = ext_map.get(lang.lower(), "py")
                        fname = f"solution.{ext}"
                    
                    target_path = os.path.join(self.workspace_root, fname)
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with open(target_path, "w", encoding="utf-8") as f:
                        f.write(code)
                    written_files.append({"file_name": fname, "content": code})

        return written_files

    async def execute_deterministic_loop(self, user_goal: str) -> Dict[str, Any]:
        graph = await self.plan_task_graph(user_goal)
        written_files_total = []

        while graph.has_unfinished_subtasks():
            # Check Global Step & Cost Safety Limits
            if self.total_llm_calls >= MAX_GLOBAL_CALLS:
                self.is_halted = True
                self.halt_reason = f"Global step limit ({MAX_GLOBAL_CALLS} calls) exceeded. Halted to protect budget."
                break
            if self.total_cost_usd >= COST_SAFETY_LIMIT_USD:
                self.is_halted = True
                self.halt_reason = f"Cost safety ceiling (${COST_SAFETY_LIMIT_USD:.2f}) reached. Halted to avoid blowing $0.50 budget."
                break

            subtask = graph.get_next_unblocked_subtask()
            if not subtask:
                # No unblocked subtask found while graph is unfinished -> Deadlock / circular dependency
                break

            subtask.status = "in_progress"
            retry_feedback = None
            reformulated_query = None

            while len(subtask.attempts) < MAX_RETRIES_PER_SUBTASK:
                # 1. Check file-level lock if target files are specified
                for f in subtask.target_files:
                    if self.file_locks.is_locked(f):
                        await asyncio.sleep(0.1)
                    self.file_locks.acquire(f)

                try:
                    # 2. Build isolated context
                    context = self._build_isolated_context(subtask, user_goal, retry_feedback, reformulated_query)

                    # 3. Call Coder
                    coder_output, coder_cost, coder_lat = await self._call_coder_model(subtask, context)

                    # 4. Call Critic
                    verdict, critic_cost, critic_lat = await self._call_critic_model(subtask, coder_output)

                    # Record attempt
                    subtask.add_attempt(
                        action="generate_code",
                        result=coder_output,
                        critic_verdict=verdict.to_dict(),
                        cost=coder_cost + critic_cost,
                        latency=coder_lat + critic_lat,
                    )

                    # 5. Check Action Loop Hash
                    h = self._hash_action(subtask.subtask_id, "generate_code", verdict.reason)
                    self.action_history_hashes[h] = self.action_history_hashes.get(h, 0) + 1
                    if self.action_history_hashes[h] >= 3:
                        self.is_halted = True
                        self.halt_reason = f"Action loop detected on subtask #{subtask.subtask_id} (repeated error signature 3x). Halting to prevent runaway token spend."
                        subtask.status = "failed"
                        break

                    # 6. Branch on Verdict
                    if verdict.passed:
                        subtask.status = "done"
                        subtask.final_output = coder_output
                        files = self._extract_and_write_files(coder_output, user_goal)
                        written_files_total.extend(files)
                        break
                    else:
                        cat = verdict.suggested_fix_category
                        if cat == "missing_context":
                            reformulated_query = f"{subtask.description} details API reference"
                            retry_feedback = f"Critic noted missing context: {verdict.reason}"
                        elif cat in ["wrong_approach", "misunderstood_scope"]:
                            if graph.replan_count < MAX_REPLANS_PER_TASK and subtask.depth < MAX_SPAWN_DEPTH:
                                # Re-plan this specific subtask branch
                                subtask.status = "failed"
                                new_sub_1 = SubtaskNode(
                                    subtask_id=subtask.subtask_id * 10 + 1,
                                    description=f"Alternative approach step 1 for {subtask.description}",
                                    dependencies=subtask.dependencies,
                                    depth=subtask.depth + 1,
                                )
                                new_sub_2 = SubtaskNode(
                                    subtask_id=subtask.subtask_id * 10 + 2,
                                    description=f"Alternative approach step 2 for {subtask.description}",
                                    dependencies=[new_sub_1.subtask_id],
                                    depth=subtask.depth + 1,
                                )
                                graph.replace_subtask_with_plan(subtask.subtask_id, [new_sub_1, new_sub_2])
                                break
                            else:
                                retry_feedback = f"Critic rejected approach: {verdict.reason}. Pivot approach immediately."
                        else:  # syntax_error / test_failure
                            retry_feedback = f"Error to fix: {verdict.reason}"
                finally:
                    for f in subtask.target_files:
                        self.file_locks.release(f)

            if subtask.status != "done" and not self.is_halted:
                # If retries exhausted, extract best code attempt so user gets solution
                if subtask.attempts:
                    best_code = subtask.attempts[-1]["result"]
                    subtask.final_output = best_code
                    fallback_files = self._extract_and_write_files(best_code, user_goal)
                    written_files_total.extend(fallback_files)
                subtask.status = "failed"

            if self.is_halted:
                break

        # Final Self-Verification Pass over full patch
        done_count = len([n for n in graph.nodes.values() if n.status == 'done'])
        verification_passed = True
        verification_notes = f"Executed across {len(graph.nodes)} subtask graph."
        if written_files_total:
            file_names = ", ".join(list({f["file_name"] for f in written_files_total}))
            verification_notes += f" Successfully generated and saved: {file_names}."

        explanation = (
            f"State machine completed {done_count} of {len(graph.nodes)} subtasks.\n"
            f"{verification_notes}"
        )
        if self.is_halted:
            explanation = f"⚠️ State Machine Halted: {self.halt_reason}\nPartial progress saved."

        active_f = written_files_total[0]["file_name"] if written_files_total else None
        active_c = written_files_total[0]["content"] if written_files_total else ""

        return {
            "type": "workflow_completed",
            "task_id": graph.task_id,
            "plan": [n.to_dict() for n in sorted(graph.nodes.values(), key=lambda x: x.subtask_id)],
            "explanation": explanation,
            "files": written_files_total,
            "active_file": active_f,
            "active_content": active_c,
            "total_calls": self.total_llm_calls,
            "total_tokens": self.total_tokens_used,
            "total_cost_usd": self.total_cost_usd,
            "is_halted": self.is_halted,
            "halt_reason": self.halt_reason,
        }

    async def execute_bytheway(self, isolated_query: str) -> Dict[str, Any]:
        worker = worker_pool.get_worker("fast_tool_agent")
        messages = [
            {"role": "system", "content": "You are Forge Scout. Answer the isolated query directly and concisely."},
            {"role": "user", "content": isolated_query}
        ]
        res = await self.client.chat_completion(
            model=worker.model,
            messages=messages,
            api_key=worker.api_key,
            role_id=worker.role_key,
            temperature=0.2,
            max_tokens=768,
        )
        cost = self._calculate_call_cost(worker, res.get("input_tokens", 0), res.get("output_tokens", 0))
        self.total_tokens_used += (res.get("input_tokens", 0) + res.get("output_tokens", 0))
        self.total_cost_usd += cost
        
        return {
            "query": isolated_query,
            "answer": res.get("content", "").strip(),
            "thinking": res.get("thinking", ""),
            "model": worker.model,
            "latency": res.get("latency_seconds", 0.0),
            "cost": cost,
        }
