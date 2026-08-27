import os
import re
from typing import Dict, List, Optional, Any
from pathlib import Path

# Built-in specialized Skill Packs
EMBEDDED_SKILLS: Dict[str, Dict[str, Any]] = {
    "fastapi": {
        "keywords": ["fastapi", "rest api", "endpoint", "backend server", "uvicorn", "pydantic"],
        "prompt": (
            "FASTAPI BEST PRACTICES SKILL:\n"
            "- Use APIRouter with typed Pydantic models for request/response bodies.\n"
            "- Include CORS middleware (allow_origins=['*']) when serving web frontends.\n"
            "- Use async def route handlers and status_code declarations."
        )
    },
    "react_tailwind": {
        "keywords": ["react", "tailwind", "component", "frontend ui", "lucide", "html", "css", "monaco"],
        "prompt": (
            "MODERN FRONTEND & UI SKILL:\n"
            "- Use modern semantic HTML5, clean responsive CSS flexbox/grid, and zero external runtime dependencies if standalone.\n"
            "- Provide complete, self-contained single-page layouts with crisp dark-mode palettes."
        )
    },
    "unit_testing": {
        "keywords": ["test", "pytest", "unit test", "unittest", "assert", "coverage", "mock"],
        "prompt": (
            "UNIT TESTING & VERIFICATION SKILL:\n"
            "- Write pytest-compliant standalone unit test functions prefixed with `test_`.\n"
            "- Cover standard cases, edge cases (empty, None, boundary numbers), and error assertions (pytest.raises)."
        )
    },
    "sqlite_db": {
        "keywords": ["database", "sqlite", "sql", "table", "schema", "query", "migration"],
        "prompt": (
            "SQLITE RELATIONAL DATABASE SKILL:\n"
            "- Use parameterized SQL queries (`?` placeholders) to prevent SQL injection vulnerabilities.\n"
            "- Create tables with `CREATE TABLE IF NOT EXISTS` and primary keys."
        )
    },
    "security_hardening": {
        "keywords": ["security", "auth", "token", "hash", "sanitize", "secret", "owasp", "ctf"],
        "prompt": (
            "SECURITY HARDENING SKILL:\n"
            "- Never hardcode API keys or secrets in plaintext.\n"
            "- Always validate and sanitize user inputs before processing or passing to subprocess/eval."
        )
    }
}

class SkillManager:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.abspath(workspace_root)
        self.skills_dir = os.path.join(self.workspace_root, ".forge", "skills")

    def get_matching_skills(self, task_description: str) -> str:
        """Finds and formats all matching skill instructions for a given subtask."""
        desc_lower = task_description.lower()
        matched_prompts: List[str] = []

        # 1. Check embedded skill catalog
        for skill_id, skill_data in EMBEDDED_SKILLS.items():
            if any(kw in desc_lower for kw in skill_data["keywords"]):
                matched_prompts.append(skill_data["prompt"])

        # 2. Check on-disk .forge/skills/*.md files
        if os.path.exists(self.skills_dir):
            try:
                for fname in os.listdir(self.skills_dir):
                    if fname.endswith(".md"):
                        skill_name = fname[:-3]
                        if skill_name in desc_lower or any(part in desc_lower for part in skill_name.split("_")):
                            fpath = os.path.join(self.skills_dir, fname)
                            with open(fpath, "r", encoding="utf-8") as f:
                                matched_prompts.append(f"CUSTOM SKILL ({skill_name}):\n" + f.read().strip())
            except Exception:
                pass

        if not matched_prompts:
            return ""

        return "\n\n[Active Domain Skills]:\n" + "\n---\n".join(matched_prompts)

skill_manager = SkillManager(workspace_root=os.getcwd())
