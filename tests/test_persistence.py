import tempfile
from pathlib import Path
import pytest
from backend.orchestrator.persistence import PersistenceManager

def test_persistence_session_and_dag_recording():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = PersistenceManager(db_path=db_path)
        
        session_id = "test-session-123"
        manager.create_session(session_id, tmpdir)
        
        manager.add_message(session_id, "user", "Refactor authentication flow")
        msgs = manager.get_messages(session_id)
        assert len(msgs) == 1
        assert msgs[0]["content"] == "Refactor authentication flow"
        
        manager.record_dag_node(
            node_id="node-1",
            session_id=session_id,
            parent_id=None,
            node_type="planner",
            agent_name="Architect",
            model="meta/llama-3.3-70b-instruct",
            provider="NVIDIA NIM",
            status="completed",
            input_data={"task": "refactor"},
            output_data={"steps": 3},
            thought="Decomposed task into steps",
            tokens_used=150,
            cost_usd=0.0001,
            latency_seconds=0.45
        )
        
        nodes = manager.get_dag_nodes(session_id)
        assert len(nodes) == 1
        assert nodes[0]["agent_name"] == "Architect"
        assert nodes[0]["output_data"]["steps"] == 3
