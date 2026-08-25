import os
import re
import json
import time
import uuid
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

from backend.config import settings
from backend.models.nim_client import NIMClient
from backend.models.worker_pool import worker_pool, WorkerAgentSpec
from backend.indexer.ast_retriever import workspace_registry
from backend.tools.executor import ToolExecutor, DiffHunk
from backend.tools.scraper import web_scraper
from backend.orchestrator.persistence import persistence

class ConductorWorkflowStep:
    def __init__(
        self,
        step_id: int,
        worker_id: str,
        subtask: str,
        access_list: List[int],
        strategy: str = "sequential",
        status: str = "pending",
        output: str = "",
    ):
        self.step_id = step_id
        self.worker_id = worker_id
        self.subtask = subtask
        self.access_list = access_list
        self.strategy = strategy
        self.status = status
        self.output = output

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "worker_id": self.worker_id,
            "subtask": self.subtask,
            "access_list": self.access_list,
            "strategy": self.strategy,
            "status": self.status,
            "output": self.output,
        }

class ConductorOrchestrator:
    def __init__(self, session_id: str, workspace_root: Optional[str] = None):
        self.session_id = session_id
        self.workspace_root = workspace_root or settings.active_workspace
        self.client = NIMClient()
        self.tools = ToolExecutor(workspace_root=self.workspace_root)
        
        self.workflow: List[ConductorWorkflowStep] = []
        self.step_outputs: Dict[int, str] = {}
        self.active_step_index: int = 0
        self.total_tokens_used: int = 0
        self.total_cost_usd: float = 0.0
        
        self.is_paused_for_approval: bool = False
        self.pending_approval_data: Optional[Dict[str, Any]] = None
        
        persistence.create_session(self.session_id, self.workspace_root)

    def _get_agents_md(self) -> str:
        p = os.path.join(self.workspace_root, "AGENTS.md")
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                pass
        return ""

    def _calculate_call_cost(self, worker: WorkerAgentSpec, in_tok: int, out_tok: int) -> float:
        return (in_tok / 1000.0 * worker.cost_per_1k_input) + (out_tok / 1000.0 * worker.cost_per_1k_output)

    def is_conversational(self, msg: str) -> bool:
        cleaned = msg.strip().lower()
        greetings = ["hello", "hi", "hey", "how are you", "who are you", "what are you", "what is this", "help", "good morning", "good evening"]
        if cleaned in greetings:
            return True
        action_keywords = [
            "add", "fix", "build", "test", "run", "write", "delete", "update", "create",
            "diff", "patch", "implement", "refactor", "modify", "scrape", "search", "browse", "fetch"
        ]
        words = cleaned.split()
        if len(words) <= 3 and not any(kw in cleaned for kw in action_keywords):
            return True
        return False

    async def execute_direct_chat(self, msg: str) -> Dict[str, Any]:
        worker = worker_pool.get_worker("fast_tool_agent")
        messages = [
            {"role": "system", "content": "You are Forge, a high-performance agentic coding assistant. Respond conversationally, clearly, and concisely to the user in the language of their project."},
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
            "model": worker.model,
            "latency": res.get("latency_seconds", 0.0),
            "cost": call_cost,
        }

    async def devise_workflow(self, user_goal: str) -> List[ConductorWorkflowStep]:
        conductor_worker = worker_pool.get_worker("conductor")
        pool_manifest = worker_pool.get_pool_manifest()
        agents_md = self._get_agents_md()
        
        system_prompt = (
            "You are the Conductor of an advanced multi-agent coding orchestra (Sakana Fugu & Hermes architecture).\n"
            "Analyze the user goal and dynamically construct a modular execution graph.\n"
            "Languages supported: Polyglot (Rust, Go, TypeScript, JavaScript, Python, C/C++, Java, HTML/CSS, Shell).\n\n"
            f"{pool_manifest}\n\n"
            "Rules for Access Lists (Sakana Fugu Intra-Workflow Isolation):\n"
            "- To prevent context collapse, each step's access_list must contain ONLY the step IDs of prior steps it needs to observe.\n\n"
            "Output JSON format ONLY as an array of step objects:\n"
            "[\n"
            "  {\n"
            "    \"step_id\": 1,\n"
            "    \"worker_id\": \"lead_engineer\",\n"
            "    \"subtask\": \"Actionable instructions for this worker...\",\n"
            "    \"access_list\": [],\n"
            "    \"strategy\": \"sequential\"\n"
            "  },\n"
            "  {\n"
            "    \"step_id\": 2,\n"
            "    \"worker_id\": \"adversarial_debugger\",\n"
            "    \"subtask\": \"Audit edge cases and logic regressions...\",\n"
            "    \"access_list\": [1],\n"
            "    \"strategy\": \"adversarial_debate\"\n"
            "  },\n"
            "  {\n"
            "    \"step_id\": 3,\n"
            "    \"worker_id\": \"synthesizer\",\n"
            "    \"subtask\": \"Synthesize final verified multi-file patch...\",\n"
            "    \"access_list\": [1, 2],\n"
            "    \"strategy\": \"sequential\"\n"
            "  }\n"
            "]"
        )
        
        if agents_md:
            system_prompt += f"\n\nProject AGENTS.md Context:\n{agents_md}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Devise multi-agent graph for: {user_goal}"}
        ]

        node_id = str(uuid.uuid4())
        t0 = time.time()
        res = await self.client.chat_completion(
            model=conductor_worker.model,
            messages=messages,
            api_key=conductor_worker.api_key,
            role_id=conductor_worker.role_key,
            temperature=0.2,
            max_tokens=1024,
        )
        latency = time.time() - t0
        content = res.get("content", "")
        
        in_tok = res.get("input_tokens", 0)
        out_tok = res.get("output_tokens", 0)
        call_cost = self._calculate_call_cost(conductor_worker, in_tok, out_tok)
        self.total_tokens_used += (in_tok + out_tok)
        self.total_cost_usd += call_cost

        steps: List[ConductorWorkflowStep] = []
        try:
            cleaned = content
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            raw_list = json.loads(cleaned)
            for item in raw_list:
                steps.append(ConductorWorkflowStep(
                    step_id=item.get("step_id", len(steps) + 1),
                    worker_id=item.get("worker_id", "lead_engineer"),
                    subtask=item.get("subtask", "Perform task step"),
                    access_list=item.get("access_list", []),
                    strategy=item.get("strategy", "sequential"),
                ))
        except Exception:
            steps = [
                ConductorWorkflowStep(1, "lead_engineer", f"Implement core changes for: {user_goal}", []),
                ConductorWorkflowStep(2, "adversarial_debugger", "Review implementation for edge cases and regressions.", [1]),
                ConductorWorkflowStep(3, "synthesizer", "Synthesize verified patch.", [1, 2]),
            ]

        self.workflow = steps
        self.step_outputs.clear()
        persistence.update_session_plan(self.session_id, [s.to_dict() for s in self.workflow])
        
        persistence.record_dag_node(
            node_id=node_id,
            session_id=self.session_id,
            parent_id=None,
            node_type="conductor_plan",
            agent_name=conductor_worker.name,
            model=conductor_worker.model,
            provider="NVIDIA NIM",
            status="completed",
            input_data={"user_goal": user_goal},
            output_data=[s.to_dict() for s in steps],
            thought=f"Constructed dynamic {len(steps)}-step Sakana Fugu graph with intra-workflow isolation.",
            tokens_used=in_tok + out_tok,
            cost_usd=call_cost,
            latency_seconds=latency,
        )

        return self.workflow

    async def execute_step(self, step_idx: int) -> Dict[str, Any]:
        if step_idx < 0 or step_idx >= len(self.workflow):
            return {"status": "error", "message": "Invalid step index"}

        current_step = self.workflow[step_idx]
        current_step.status = "running"
        worker = worker_pool.get_worker(current_step.worker_id)
        
        # 1. Hermes Web Scraping / Search Capability Check
        web_context = ""
        urls_in_task = re.findall(r'https?://[^\s]+', current_step.subtask)
        if urls_in_task:
            scraped = await web_scraper.scrape_url(urls_in_task[0])
            if scraped["status"] == "success":
                web_context = f"\n=== Hermes Scraped Web Context ({scraped['title']}) ===\n{scraped['content']}\n"
        elif any(k in current_step.subtask.lower() for k in ["search docs", "scrape", "documentation", "online reference"]):
            search_res = await web_scraper.search_and_scrape(current_step.subtask, max_results=2)
            if search_res["status"] == "success" and search_res["results"]:
                snippets = [f"- {r['title']} ({r['url']}): {r['snippet']}" for r in search_res["results"]]
                web_context = "\n=== Hermes Live Web Documentation ===\n" + "\n".join(snippets) + "\n"

        # 2. AST Code Retrieval
        idx_engine = workspace_registry.get_index(self.workspace_root)
        search_results = idx_engine.search(current_step.subtask, top_k=3)
        context_chunks = "\n".join([r["formatted_chunk"] for r in search_results]) if search_results else ""
        
        # 3. Assemble Scoped Context using Access List (Intra-Workflow Isolation)
        scoped_history = []
        for prior_id in current_step.access_list:
            if prior_id in self.step_outputs:
                prior_step_obj = next((s for s in self.workflow if s.step_id == prior_id), None)
                role_label = prior_step_obj.worker_id if prior_step_obj else f"Step {prior_id}"
                scoped_history.append(f"=== Output from [{role_label}] (Step {prior_id}) ===\n{self.step_outputs[prior_id]}")

        agents_md = self._get_agents_md()
        worker_system_prompt = (
            f"You are the '{worker.name}' (Role: {worker.role}, Specialty: {worker.specialty}).\n"
            "You are working in an autonomous multi-agent engineering team.\n"
            "Execute your assigned subtask rigorously. Produce clean, production-grade code or verified diff patches."
        )
        if agents_md:
            worker_system_prompt += f"\n\nProject AGENTS.md Rules:\n{agents_md}"

        user_content = f"Assigned Subtask: {current_step.subtask}\n"
        if web_context:
            user_content += web_context
        if scoped_history:
            user_content += "\n=== Accessible Context from Prior Agents ===\n" + "\n\n".join(scoped_history) + "\n"
        if context_chunks:
            user_content += f"\n=== Relevant Codebase AST Slices ===\n{context_chunks}\n"

        messages = [
            {"role": "system", "content": worker_system_prompt},
            {"role": "user", "content": user_content}
        ]

        node_id = str(uuid.uuid4())
        t0 = time.time()
        res = await self.client.chat_completion(
            model=worker.model,
            messages=messages,
            api_key=worker.api_key,
            role_id=worker.role_key,
            temperature=0.2,
            max_tokens=1536,
        )
        latency = time.time() - t0
        output_content = res.get("content", "")
        
        in_tok = res.get("input_tokens", 0)
        out_tok = res.get("output_tokens", 0)
        call_cost = self._calculate_call_cost(worker, in_tok, out_tok)
        self.total_tokens_used += (in_tok + out_tok)
        self.total_cost_usd += call_cost

        current_step.output = output_content
        self.step_outputs[current_step.step_id] = output_content
        current_step.status = "completed"

        persistence.record_dag_node(
            node_id=node_id,
            session_id=self.session_id,
            parent_id=None,
            node_type=f"worker_{current_step.worker_id}",
            agent_name=worker.name,
            model=worker.model,
            provider="NVIDIA NIM",
            status="completed",
            input_data={"subtask": current_step.subtask, "access_list": current_step.access_list},
            output_data={"content": output_content},
            thought=f"Executed subtask {current_step.step_id} using {worker.name} ({worker.specialty}).",
            tokens_used=in_tok + out_tok,
            cost_usd=call_cost,
            latency_seconds=latency,
        )

        return {
            "step": current_step.to_dict(),
            "output": output_content,
        }

    def _extract_and_write_files(self, text: str, user_goal: str) -> List[Dict[str, str]]:
        written_files = []
        
        # 1. Look for explicit file blocks across all languages
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

        # 2. Look for code blocks with language tags
        if not written_files:
            code_matches = re.findall(r'```([a-zA-Z0-9_+\-]*)\n(.*?)```', text, re.DOTALL)
            if code_matches:
                lang, code = code_matches[0]
                code = code.strip()
                
                # Deduce extension from goal or language tag
                ext_map = {
                    "rust": "rs", "rs": "rs",
                    "go": "go", "golang": "go",
                    "typescript": "ts", "ts": "ts", "tsx": "tsx",
                    "javascript": "js", "js": "js", "jsx": "jsx",
                    "python": "py", "py": "py",
                    "cpp": "cpp", "c++": "cpp", "c": "c",
                    "java": "java", "html": "html", "css": "css",
                    "sh": "sh", "bash": "sh", "json": "json", "markdown": "md", "md": "md"
                }
                
                # Check if user specified a filename in prompt
                explicit_file = re.findall(r'([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)', user_goal)
                if explicit_file:
                    fname = explicit_file[0]
                else:
                    ext = ext_map.get(lang.lower(), "txt")
                    base = "solution"
                    if "test" in user_goal.lower():
                        base = "test_solution"
                    fname = f"{base}.{ext}" if ext != "txt" else "main.py"
                
                target_path = os.path.join(self.workspace_root, fname)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(code)
                written_files.append({"file_name": fname, "content": code})

        return written_files

    def _clean_explanation(self, text: str) -> str:
        cleaned = re.sub(r'```.*?```', '', text, flags=re.DOTALL).strip()
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        if not cleaned or len(cleaned) < 20:
            return "Task successfully processed across the multi-agent workflow. The generated code is open in your IDE editor."
        return cleaned

    async def execute_full_workflow(self, user_goal: str) -> Dict[str, Any]:
        steps = await self.devise_workflow(user_goal)
        for i in range(len(steps)):
            await self.execute_step(i)

        latest_output = self.step_outputs.get(steps[-1].step_id, "") or self.step_outputs.get(1, "")
        written = self._extract_and_write_files(latest_output, user_goal)
        explanation = self._clean_explanation(latest_output)

        try:
            idx_engine = workspace_registry.get_index(self.workspace_root)
            idx_engine.build_index()
        except Exception:
            pass

        return {
            "type": "workflow_completed",
            "plan": [s.to_dict() for s in self.workflow],
            "explanation": explanation,
            "files": written,
            "active_file": written[0]["file_name"] if written else None,
            "active_content": written[0]["content"] if written else "",
        }

    async def execute_bytheway(self, isolated_query: str) -> Dict[str, Any]:
        scout_worker = worker_pool.get_worker("fast_tool_agent")
        
        web_info = ""
        if any(k in isolated_query.lower() for k in ["scrape", "search", "http://", "https://", "latest docs"]):
            search_res = await web_scraper.search_and_scrape(isolated_query, max_results=2)
            if search_res["status"] == "success" and search_res["results"]:
                web_info = "\n[Hermes Live Web Reference]:\n" + "\n".join([f"- {r['title']}: {r['snippet']}" for r in search_res["results"]])

        messages = [
            {"role": "system", "content": "You are Forge Scout, a fast software engineering scout. Answer the isolated query directly and concisely in the appropriate language."},
            {"role": "user", "content": isolated_query + web_info}
        ]

        node_id = str(uuid.uuid4())
        t0 = time.time()
        res = await self.client.chat_completion(
            model=scout_worker.model,
            messages=messages,
            api_key=scout_worker.api_key,
            role_id=scout_worker.role_key,
            temperature=0.2,
            max_tokens=768,
        )
        latency = time.time() - t0
        content = res.get("content", "")
        
        in_tok = res.get("input_tokens", 0)
        out_tok = res.get("output_tokens", 0)
        call_cost = self._calculate_call_cost(scout_worker, in_tok, out_tok)
        self.total_tokens_used += (in_tok + out_tok)
        self.total_cost_usd += call_cost

        persistence.record_dag_node(
            node_id=node_id,
            session_id=self.session_id,
            parent_id=None,
            node_type="bytheway_scout",
            agent_name=scout_worker.name,
            model=scout_worker.model,
            provider="NVIDIA NIM",
            status="completed",
            input_data={"query": isolated_query},
            output_data={"content": content},
            thought="Executed zero-context isolated query with Hermes web scraping capability.",
            tokens_used=in_tok + out_tok,
            cost_usd=call_cost,
            latency_seconds=latency,
        )

        return {
            "query": isolated_query,
            "answer": content,
            "model": scout_worker.model,
            "latency": latency,
            "cost": call_cost,
        }
