import os
import tempfile
import pytest
from backend.orchestrator.compaction import ContextCompactor

def test_compaction_and_agents_md_preservation():
    with tempfile.TemporaryDirectory() as tmpdir:
        agents_md = os.path.join(tmpdir, "AGENTS.md")
        with open(agents_md, "w", encoding="utf-8") as f:
            f.write("# Coding Standards\n- Always use 4-space indentation.\n- Run pytest before finalizing.")

        compactor = ContextCompactor(token_threshold=50) # low threshold to trigger compaction
        
        messages = [
            {"role": "system", "content": "Base System Prompt."},
            {"role": "user", "content": "Turn 1: Please set up the database module."},
            {"role": "assistant", "content": "Turn 1 Response: Database configured."},
            {"role": "user", "content": "Turn 2: Add connection pooling."},
            {"role": "assistant", "content": "Turn 2 Response: Pooling added."},
            {"role": "user", "content": "Turn 3: Fix query timeout bug."},
            {"role": "assistant", "content": "Turn 3 Response: Fixed query timeout."},
            {"role": "user", "content": "Turn 4: Latest instructions."},
        ]

        assert compactor.should_compact(messages) is True
        
        compacted = compactor.compact(
            messages=messages,
            workspace_root=tmpdir,
            key_decisions=["Created initial database schema."]
        )

        sys_content = compacted[0]["content"]
        assert "Always use 4-space indentation" in sys_content
        assert "Created initial database schema." in sys_content
        assert len(compacted) < len(messages)
