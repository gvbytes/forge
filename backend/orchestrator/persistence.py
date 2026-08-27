import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from backend.config import settings

class PersistenceManager:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    workspace_root TEXT,
                    created_at REAL,
                    updated_at REAL,
                    status TEXT,
                    plan_json TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    created_at REAL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS dag_nodes (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    parent_id TEXT,
                    node_type TEXT,
                    agent_name TEXT,
                    model TEXT,
                    provider TEXT,
                    status TEXT,
                    input_data TEXT,
                    output_data TEXT,
                    thought TEXT,
                    tokens_used INTEGER,
                    cost_usd REAL,
                    latency_seconds REAL,
                    created_at REAL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    step_index INTEGER,
                    state_snapshot TEXT,
                    created_at REAL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    memory_type TEXT,
                    key TEXT,
                    content TEXT,
                    importance_score REAL DEFAULT 1.0,
                    created_at REAL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
            """)

    def create_session(self, session_id: str, workspace_root: str) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, workspace_root, created_at, updated_at, status, plan_json) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, workspace_root, now, now, "active", json.dumps([]))
            )

    def update_session_plan(self, session_id: str, plan: List[Dict[str, Any]]) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET plan_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(plan), now, session_id)
            )

    def add_message(self, session_id: str, role: str, content: str) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, now)
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def add_memory(
        self,
        session_id: str,
        memory_type: str,
        key: str,
        content: str,
        importance_score: float = 1.0
    ) -> int:
        now = time.time()
        with self._get_connection() as conn:
            # Avoid duplicate identical keys for the session
            conn.execute(
                "DELETE FROM memories WHERE session_id = ? AND key = ?",
                (session_id, key)
            )
            cursor = conn.execute(
                "INSERT INTO memories (session_id, memory_type, key, content, importance_score, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, memory_type, key, content, importance_score, now)
            )
            return cursor.lastrowid

    def get_memories(
        self,
        session_id: str,
        memory_type: Optional[str] = None,
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if memory_type:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE session_id = ? AND memory_type = ? ORDER BY importance_score DESC, created_at DESC LIMIT ?",
                    (session_id, memory_type, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE session_id = ? ORDER BY importance_score DESC, created_at DESC LIMIT ?",
                    (session_id, limit)
                ).fetchall()
            return [dict(r) for r in rows]

    def get_compacted_context_window(self, session_id: str, max_tokens: int = 1200) -> str:
        """Returns a dense, bullet-point compacted context of prior conversation turns and facts."""
        messages = self.get_messages(session_id)
        memories = self.get_memories(session_id)
        
        parts: List[str] = []
        if memories:
            fact_lines = [f"- [{m['memory_type'].upper()}] {m['key']}: {m['content']}" for m in memories[:15]]
            parts.append("### Project & Session Memory Facts:\n" + "\n".join(fact_lines))
            
        if messages:
            # Take last 4 recent messages in full, summarize earlier ones
            recent = messages[-4:]
            earlier = messages[:-4]
            
            if earlier:
                summary_bullets = []
                for m in earlier:
                    text_snippet = m['content'].strip().split("\n")[0][:120]
                    summary_bullets.append(f"- {m['role'].capitalize()}: {text_snippet}")
                parts.append("### Prior Context Summary:\n" + "\n".join(summary_bullets[-8:]))
                
            recent_turns = []
            for m in recent:
                snippet = m['content'] if len(m['content']) < 300 else m['content'][:300] + "..."
                recent_turns.append(f"{m['role'].upper()}: {snippet}")
            parts.append("### Recent Conversation Context:\n" + "\n\n".join(recent_turns))
            
        return "\n\n".join(parts)

    def delete_memory(self, memory_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

    def clear_memories(self, session_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM memories WHERE session_id = ?", (session_id,))

    def record_dag_node(
        self,
        node_id: str,
        session_id: str,
        parent_id: Optional[str],
        node_type: str,
        agent_name: str,
        model: str,
        provider: str,
        status: str,
        input_data: Any,
        output_data: Any,
        thought: str = "",
        tokens_used: int = 0,
        cost_usd: float = 0.0,
        latency_seconds: float = 0.0,
    ) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO dag_nodes (
                    id, session_id, parent_id, node_type, agent_name, model, provider,
                    status, input_data, output_data, thought, tokens_used, cost_usd,
                    latency_seconds, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node_id, session_id, parent_id, node_type, agent_name, model, provider,
                status, json.dumps(input_data), json.dumps(output_data), thought,
                tokens_used, cost_usd, latency_seconds, now
            ))

    def get_dag_nodes(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM dag_nodes WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["input_data"] = json.loads(d["input_data"])
                    d["output_data"] = json.loads(d["output_data"])
                except Exception:
                    pass
                result.append(d)
            return result

    def save_checkpoint(self, checkpoint_id: str, session_id: str, step_index: int, state: Dict[str, Any]) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO checkpoints (id, session_id, step_index, state_snapshot, created_at) VALUES (?, ?, ?, ?, ?)",
                (checkpoint_id, session_id, step_index, json.dumps(state), now)
            )

    def load_latest_checkpoint(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT state_snapshot FROM checkpoints WHERE session_id = ? ORDER BY step_index DESC LIMIT 1",
                (session_id,)
            ).fetchone()
            if row:
                return json.loads(row["state_snapshot"])
            return None

persistence = PersistenceManager()
