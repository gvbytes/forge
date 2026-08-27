import json
from typing import List, Dict, Any, Optional, Set

class SubtaskNode:
    def __init__(
        self,
        subtask_id: int,
        description: str,
        assigned_role: str = "coder",
        context_refs: Optional[List[str]] = None,
        dependencies: Optional[List[int]] = None,
        target_files: Optional[List[str]] = None,
        status: str = "pending",
        depth: int = 0,
    ):
        self.subtask_id = subtask_id
        self.description = description
        self.assigned_role = assigned_role
        self.context_refs = context_refs or []
        self.dependencies = dependencies or []
        self.target_files = target_files or []
        self.status = status  # "pending", "in_progress", "done", "failed", "skipped"
        self.depth = depth
        self.attempts: List[Dict[str, Any]] = []
        self.final_output: str = ""

    def add_attempt(self, action: str, result: str, critic_verdict: Dict[str, Any], cost: float, latency: float):
        self.attempts.append({
            "action": action,
            "result": result,
            "critic_verdict": critic_verdict,
            "cost": cost,
            "latency": latency,
            "attempt_number": len(self.attempts) + 1,
        })

    def is_blocked(self, completed_ids: Set[int]) -> bool:
        return any(dep not in completed_ids for dep in self.dependencies)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "description": self.description,
            "assigned_role": self.assigned_role,
            "context_refs": self.context_refs,
            "dependencies": self.dependencies,
            "target_files": self.target_files,
            "status": self.status,
            "depth": self.depth,
            "attempts_count": len(self.attempts),
            "attempts": self.attempts,
            "final_output": self.final_output,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubtaskNode":
        node = cls(
            subtask_id=data["subtask_id"],
            description=data["description"],
            assigned_role=data.get("assigned_role", "coder"),
            context_refs=data.get("context_refs", []),
            dependencies=data.get("dependencies", []),
            target_files=data.get("target_files", []),
            status=data.get("status", "pending"),
            depth=data.get("depth", 0),
        )
        node.attempts = data.get("attempts", [])
        node.final_output = data.get("final_output", "")
        return node


class TaskGraph:
    def __init__(self, task_id: str, user_goal: str):
        self.task_id = task_id
        self.user_goal = user_goal
        self.nodes: Dict[int, SubtaskNode] = {}
        self.replan_count: int = 0
        self.total_tokens_used: int = 0
        self.total_cost_usd: float = 0.0

    def add_node(self, node: SubtaskNode):
        self.nodes[node.subtask_id] = node

    def get_completed_ids(self) -> Set[int]:
        return {node.subtask_id for node in self.nodes.values() if node.status == "done"}

    def get_ready_subtasks(
        self,
        running_subtask_ids: Optional[Set[int]] = None,
        locked_files: Optional[Set[str]] = None
    ) -> List[SubtaskNode]:
        """Returns all unblocked subtasks that are ready to run concurrently."""
        completed = self.get_completed_ids()
        running = running_subtask_ids or set()
        active_locks = locked_files or set()
        
        ready_nodes: List[SubtaskNode] = []
        newly_claimed_files: Set[str] = set()

        for node in sorted(self.nodes.values(), key=lambda n: n.subtask_id):
            if node.subtask_id in running:
                continue
            if node.status == "pending" and not node.is_blocked(completed):
                # Check for file conflict with currently running or already claimed nodes in this batch
                has_file_conflict = any(
                    f in active_locks or f in newly_claimed_files
                    for f in (node.target_files or [])
                )
                if not has_file_conflict:
                    ready_nodes.append(node)
                    for f in (node.target_files or []):
                        newly_claimed_files.add(f)

        return ready_nodes

    def get_parallel_execution_layers(self) -> List[List[SubtaskNode]]:
        """Decomposes the DAG into ordered parallel execution layers (Kahn's topological grouping)."""
        completed: Set[int] = set()
        layers: List[List[SubtaskNode]] = []
        remaining_node_ids = set(self.nodes.keys())

        while remaining_node_ids:
            current_layer = [
                self.nodes[nid] for nid in sorted(remaining_node_ids)
                if not self.nodes[nid].is_blocked(completed)
            ]
            if not current_layer:
                # Cycle or unresolved dependency: take remaining in sequential order
                current_layer = [self.nodes[min(remaining_node_ids)]]
            
            layers.append(current_layer)
            for n in current_layer:
                completed.add(n.subtask_id)
                remaining_node_ids.remove(n.subtask_id)

        return layers

    def get_next_unblocked_subtask(self) -> Optional[SubtaskNode]:
        completed = self.get_completed_ids()
        for node in sorted(self.nodes.values(), key=lambda n: n.subtask_id):
            if node.status == "pending" and not node.is_blocked(completed):
                return node
        return None

    def has_unfinished_subtasks(self) -> bool:
        return any(node.status in ["pending", "in_progress"] for node in self.nodes.values())

    def get_all_subtasks_status(self) -> Dict[str, int]:
        counts = {"pending": 0, "in_progress": 0, "done": 0, "failed": 0, "skipped": 0}
        for n in self.nodes.values():
            counts[n.status] = counts.get(n.status, 0) + 1
        return counts

    def replace_subtask_with_plan(self, failed_subtask_id: int, new_nodes: List[SubtaskNode]):
        if failed_subtask_id in self.nodes:
            self.nodes[failed_subtask_id].status = "failed"
        
        for new_node in new_nodes:
            self.nodes[new_node.subtask_id] = new_node
        self.replan_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_goal": self.user_goal,
            "replan_count": self.replan_count,
            "total_tokens_used": self.total_tokens_used,
            "total_cost_usd": self.total_cost_usd,
            "nodes": [n.to_dict() for n in sorted(self.nodes.values(), key=lambda n: n.subtask_id)],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskGraph":
        graph = cls(task_id=data["task_id"], user_goal=data["user_goal"])
        graph.replan_count = data.get("replan_count", 0)
        graph.total_tokens_used = data.get("total_tokens_used", 0)
        graph.total_cost_usd = data.get("total_cost_usd", 0.0)
        for n_data in data.get("nodes", []):
            graph.add_node(SubtaskNode.from_dict(n_data))
        return graph
