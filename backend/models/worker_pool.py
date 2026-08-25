from typing import Dict, Any, List
from backend.config import settings

class WorkerAgentSpec:
    def __init__(
        self,
        worker_id: str,
        role_key: str,
        name: str,
        role: str,
        specialty: str,
        cost_per_1k_input: float,
        cost_per_1k_output: float,
    ):
        self.worker_id = worker_id
        self.role_key = role_key
        self.name = name
        self.role = role
        self.specialty = specialty
        self.cost_per_1k_input = cost_per_1k_input
        self.cost_per_1k_output = cost_per_1k_output

    @property
    def model(self) -> str:
        return settings.get_role_config(self.role_key).model

    @property
    def api_key(self) -> str:
        return settings.get_role_config(self.role_key).api_key

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "role_key": self.role_key,
            "name": self.name,
            "model": self.model,
            "role": self.role,
            "specialty": self.specialty,
            "cost_rates": {
                "input": self.cost_per_1k_input,
                "output": self.cost_per_1k_output,
            }
        }

class WorkerPool:
    def __init__(self):
        self.workers: Dict[str, WorkerAgentSpec] = {
            "conductor": WorkerAgentSpec(
                worker_id="conductor",
                role_key="planner",
                name="Lead Conductor / Architect",
                role="Dynamic workflow decomposition and graph routing",
                specialty="Decomposes high-level coding goals into targeted sub-tasks and access lists",
                cost_per_1k_input=0.0003,
                cost_per_1k_output=0.0005,
            ),
            "lead_engineer": WorkerAgentSpec(
                worker_id="lead_engineer",
                role_key="coder",
                name="Primary Code Engineer",
                role="Implementation and Patch Generation",
                specialty="Writing clean, efficient multi-file implementations and Git diff patches",
                cost_per_1k_input=0.0003,
                cost_per_1k_output=0.0005,
            ),
            "adversarial_debugger": WorkerAgentSpec(
                worker_id="adversarial_debugger",
                role_key="critic",
                name="Adversarial Critic (Red Team)",
                role="Vulnerability & Logic Auditor",
                specialty="Auditing edge cases, race conditions, type mismatches, and logic regressions",
                cost_per_1k_input=0.0003,
                cost_per_1k_output=0.0005,
            ),
            "fast_tool_agent": WorkerAgentSpec(
                worker_id="fast_tool_agent",
                role_key="router",
                name="Fast Tool Operator & Scout",
                role="Fast Intent Triage & /bytheway Spot Queries",
                specialty="High-speed query answering, AST symbol search, and /bytheway Q&A",
                cost_per_1k_input=0.0001,
                cost_per_1k_output=0.0002,
            ),
            "synthesizer": WorkerAgentSpec(
                worker_id="synthesizer",
                role_key="coder",
                name="Dynamic Consensus Synthesizer",
                role="Multi-Agent Consensus & Final Patch Merge",
                specialty="Resolving conflicting agent outputs and synthesizing validated unified diffs",
                cost_per_1k_input=0.0003,
                cost_per_1k_output=0.0005,
            ),
        }

    def get_worker(self, worker_id: str) -> WorkerAgentSpec:
        return self.workers.get(worker_id, self.workers["lead_engineer"])

    def get_pool_manifest(self) -> str:
        manifest = "Available Specialized Worker Agents in Pool:\n"
        for w in self.workers.values():
            manifest += f"- ID: '{w.worker_id}' | Role: {w.name} | Model: {w.model} | Specialty: {w.specialty}\n"
        return manifest

worker_pool = WorkerPool()
