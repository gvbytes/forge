import os
from typing import List, Dict, Any, Optional
from backend.config import settings

class ContextCompactor:
    def __init__(self, token_threshold: int = 24000):
        self.token_threshold = token_threshold

    def estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4

    def should_compact(self, messages: List[Dict[str, str]]) -> bool:
        return self.estimate_tokens(messages) > self.token_threshold

    def extract_agents_md(self, workspace_root: str) -> str:
        agents_md_path = os.path.join(workspace_root, "AGENTS.md")
        if os.path.exists(agents_md_path):
            try:
                with open(agents_md_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                pass
        return ""

    def compact(
        self,
        messages: List[Dict[str, str]],
        workspace_root: str,
        active_plan: Optional[List[Dict[str, Any]]] = None,
        key_decisions: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        if not self.should_compact(messages):
            return messages

        agents_rules = self.extract_agents_md(workspace_root)
        
        system_msgs = [m for m in messages if m.get("role") == "system"]
        base_system_prompt = system_msgs[0]["content"] if system_msgs else "You are Agent Zero, an expert autonomous coding assistant."
        
        recent_window = messages[-6:]
        historical_turns = messages[:-6]
        
        summary_points = []
        if key_decisions:
            summary_points.extend(key_decisions)
            
        for turn in historical_turns:
            content = turn.get("content", "")
            role = turn.get("role", "")
            if role == "user" and len(content) < 200:
                summary_points.append(f"User Goal: {content}")
            elif "diff --git" in content:
                summary_points.append("Patch applied to target files.")
            elif "[Linter Error]" in content or "[Test Failure]" in content:
                lines = [l for l in content.splitlines() if "Error" in l or "Failure" in l]
                if lines:
                    summary_points.append(f"Past Fix Encountered: {lines[0]}")

        plan_summary = ""
        if active_plan:
            plan_summary = "\nActive Plan Status:\n" + "\n".join(
                f"- Step {p.get('step_id', i+1)}: {p.get('title', '')} [{p.get('status', 'pending')}]"
                for i, p in enumerate(active_plan)
            )

        compacted_system = f"{base_system_prompt}\n\n=== AGENTS.md RULES (PRESERVED) ===\n{agents_rules}\n\n=== COMPACTED STATE & DECISION SUMMARY ===\n"
        if summary_points:
            compacted_system += "\n".join(f"* {pt}" for pt in summary_points[-10:])
        if plan_summary:
            compacted_system += f"\n{plan_summary}"

        new_messages = [{"role": "system", "content": compacted_system}]
        for turn in recent_window:
            if turn.get("role") != "system":
                new_messages.append(turn)

        return new_messages
