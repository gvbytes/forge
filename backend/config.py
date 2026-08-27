import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

DEFAULT_CONFIG_DIR = Path.home() / ".agent_zero"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_DB_PATH = DEFAULT_CONFIG_DIR / "state.db"

class RoleConfig:
    def __init__(self, role_id: str, name: str, model: str, api_key: str, description: str):
        self.role_id = role_id
        self.name = name
        self.model = model
        self.api_key = api_key
        self.description = description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "model": self.model,
            "api_key": self.api_key,
            "description": self.description,
        }

class Settings:
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.config_dir = config_path.parent
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.nvidia_base_url: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        
        # 4 Dedicated Configurable Roles & Keys (NVIDIA NIM < 80B Tier)
        self.role_planner = RoleConfig(
            role_id="planner",
            name="Lead Conductor / Architect",
            model="openai/gpt-oss-20b",
            api_key="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",
            description="Dynamic workflow generation, decomposition, and topology routing",
        )
        self.role_coder = RoleConfig(
            role_id="coder",
            name="Primary Code Engineer",
            model="openai/gpt-oss-20b",
            api_key="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",
            description="Core multi-file implementation, code modifications, and diff synthesis",
        )
        self.role_critic = RoleConfig(
            role_id="critic",
            name="Adversarial Critic / Verifier",
            model="meta/muse-glimmer-30b",
            api_key="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",
            description="Auditing edge cases, logical soundness, and regression prevention",
        )
        self.role_router = RoleConfig(
            role_id="router",
            name="Router / Fast Scout",
            model="openai/gpt-oss-20b",
            api_key="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",
            description="High-speed query triage, AST symbol search, and /bytheway spot queries",
        )
        
        self.max_budget_usd: float = 0.50
        self.timeout_seconds: int = 2700
        self.c_base: float = 0.15
        self.t_base: float = 1320
        self.w_c: float = 0.65
        self.w_t: float = 0.35
        self.penalty_exponent: float = 2.5
        
        self.max_turns: int = 15
        self.max_retries_per_step: int = 3
        self.compaction_token_threshold: int = 24000
        
        self.active_workspace: str = str(Path(__file__).parent.parent / "home")
        self.db_path: Path = DEFAULT_DB_PATH
        
        self.load_from_disk()

    def get_role_config(self, role_id: str) -> RoleConfig:
        mapping = {
            "planner": self.role_planner,
            "conductor": self.role_planner,
            "coder": self.role_coder,
            "lead_engineer": self.role_coder,
            "critic": self.role_critic,
            "adversarial_debugger": self.role_critic,
            "router": self.role_router,
            "fast_tool_agent": self.role_router,
            "synthesizer": self.role_coder,
        }
        return mapping.get(role_id, self.role_coder)

    def load_from_disk(self) -> None:
        project_home = str(Path(__file__).parent.parent / "home")
        os.makedirs(project_home, exist_ok=True)
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "roles" in data:
                        roles = data["roles"]
                        if "planner" in roles:
                            self.role_planner.model = roles["planner"].get("model", self.role_planner.model)
                            self.role_planner.api_key = roles["planner"].get("api_key", self.role_planner.api_key)
                        if "coder" in roles:
                            self.role_coder.model = roles["coder"].get("model", self.role_coder.model)
                            self.role_coder.api_key = roles["coder"].get("api_key", self.role_coder.api_key)
                        if "critic" in roles:
                            self.role_critic.model = roles["critic"].get("model", self.role_critic.model)
                            self.role_critic.api_key = roles["critic"].get("api_key", self.role_critic.api_key)
                        if "router" in roles:
                            self.role_router.model = roles["router"].get("model", self.role_router.model)
                            self.role_router.api_key = roles["router"].get("api_key", self.role_router.api_key)
                    if "nvidia_base_url" in data and data["nvidia_base_url"]:
                        self.nvidia_base_url = data["nvidia_base_url"]
                    if "active_workspace" in data and data["active_workspace"]:
                        ws = data["active_workspace"].strip()
                        if ws in ["/home", "home", "workspace", "/workspace"]:
                            self.active_workspace = project_home
                        elif not os.path.exists(ws):
                            self.active_workspace = project_home
                        else:
                            self.active_workspace = os.path.abspath(os.path.expanduser(ws))
            except Exception:
                pass

    def save_to_disk(self) -> None:
        data = {
            "nvidia_base_url": self.nvidia_base_url,
            "active_workspace": self.active_workspace,
            "roles": {
                "planner": self.role_planner.to_dict(),
                "coder": self.role_coder.to_dict(),
                "critic": self.role_critic.to_dict(),
                "router": self.role_router.to_dict(),
            }
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def update_role(self, role_id: str, model: Optional[str] = None, api_key: Optional[str] = None) -> None:
        cfg = self.get_role_config(role_id)
        if model:
            cfg.model = model
        if api_key:
            cfg.api_key = api_key
        self.save_to_disk()

settings = Settings()
