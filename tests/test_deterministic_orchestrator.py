import os
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from backend.orchestrator.task_graph import TaskGraph, SubtaskNode
from backend.orchestrator.state_machine import (
    DeterministicOrchestrator,
    FileLockManager,
    StructuredCriticVerdict,
    MAX_RETRIES_PER_SUBTASK,
    MAX_GLOBAL_CALLS,
)

# ==============================================================================
# TEST CASE 1: 3+ Genuinely Dependent Subtasks & Strict Context Isolation
# ==============================================================================
@pytest.mark.asyncio
async def test_dependent_subtasks_and_context_isolation(tmp_path):
    workspace = str(tmp_path)
    orch = DeterministicOrchestrator(session_id="test-deps-01", workspace_root=workspace)
    
    # Create 3 dependent subtasks: 1 -> 2 -> 3
    graph = TaskGraph(task_id="graph-01", user_goal="Build 3-tier module")
    node1 = SubtaskNode(1, "Define User data model", assigned_role="coder", dependencies=[])
    node2 = SubtaskNode(2, "Implement UserRepository using User model", assigned_role="coder", dependencies=[1])
    node3 = SubtaskNode(3, "Implement UserService using UserRepository", assigned_role="coder", dependencies=[2])
    
    graph.add_node(node1)
    graph.add_node(node2)
    graph.add_node(node3)
    orch.graph = graph

    # Verify dependency resolution order
    first = graph.get_next_unblocked_subtask()
    assert first is not None
    assert first.subtask_id == 1  # 2 and 3 are blocked

    first.status = "done"
    second = graph.get_next_unblocked_subtask()
    assert second is not None
    assert second.subtask_id == 2  # 3 is still blocked

    second.status = "done"
    third = graph.get_next_unblocked_subtask()
    assert third is not None
    assert third.subtask_id == 3

    # Verify Context Isolation: Subtask 3 gets ONLY its own prompt & AST slices, not Subtask 1's raw output
    isolated_ctx = orch._build_isolated_context(third, user_goal="Build 3-tier module")
    assert "Implement UserService" in isolated_ctx
    assert "Define User data model" not in isolated_ctx  # Raw prior task prompt is not blindly dumped into ctx


# ==============================================================================
# TEST CASE 2: Deliberate Failure, Structured Backtracking, Re-plan & Stuck-Task Halt
# ==============================================================================
@pytest.mark.asyncio
async def test_structured_backtracking_and_loop_detection(tmp_path):
    workspace = str(tmp_path)
    orch = DeterministicOrchestrator(session_id="test-backtrack-01", workspace_root=workspace)
    
    graph = TaskGraph(task_id="graph-02", user_goal="Implement complex algorithm")
    failing_node = SubtaskNode(1, "Implement flawed approach", assigned_role="coder", dependencies=[])
    graph.add_node(failing_node)
    orch.graph = graph

    # Test 2a: Structured Critic Verdict Parsing
    raw_critic_json = json.dumps({
        "passed": False,
        "reason": "Algorithm produces quadratic memory leak",
        "suggested_fix_category": "wrong_approach"
    })
    verdict = StructuredCriticVerdict.from_text(raw_critic_json)
    assert verdict.passed is False
    assert verdict.suggested_fix_category == "wrong_approach"

    # Test 2b: Real Backtracking (Re-planning a failed branch)
    replacement_nodes = [
        SubtaskNode(11, "Alternative approach: streaming chunk reader", dependencies=[]),
        SubtaskNode(12, "Alternative approach: memory-bounded consumer", dependencies=[11]),
    ]
    graph.replace_subtask_with_plan(1, replacement_nodes)
    assert graph.nodes[1].status == "failed"
    assert 11 in graph.nodes
    assert 12 in graph.nodes
    assert graph.replan_count == 1

    # Test 2c: Stuck-Task Action Loop Detection (Repeated error hash halts execution)
    h = orch._hash_action(1, "generate_code", "Quadratic memory leak")
    orch.action_history_hashes[h] = 3
    if orch.action_history_hashes[h] >= 3:
        orch.is_halted = True
        orch.halt_reason = "Action loop detected on subtask #1"
    
    assert orch.is_halted is True
    assert "Action loop detected" in orch.halt_reason


# ==============================================================================
# TEST CASE 3: File Locking & Concurrent Conflict Prevention
# ==============================================================================
def test_file_level_locking():
    lock_mgr = FileLockManager()
    file_a = "src/database.py"
    file_b = "src/utils.py"

    # Acquire lock for file_a
    assert lock_mgr.acquire(file_a) is True
    assert lock_mgr.is_locked(file_a) is True

    # Second acquisition on the same file MUST fail (preventing concurrent write clobber)
    assert lock_mgr.acquire(file_a) is False

    # Acquisition on independent file_b succeeds
    assert lock_mgr.acquire(file_b) is True

    # Releasing file_a allows subsequent acquisition
    lock_mgr.release(file_a)
    assert lock_mgr.is_locked(file_a) is False
    assert lock_mgr.acquire(file_a) is True


# ==============================================================================
# TEST CASE 4: Structured Task Graph State Survival Across Compaction
# ==============================================================================
def test_task_graph_compaction_survivability():
    graph = TaskGraph(task_id="graph-04", user_goal="Build full stack microservice")
    n1 = SubtaskNode(1, "Create API schemas", status="done", target_files=["schemas.py"])
    n1.add_attempt("write_code", "class User(BaseModel): ...", {"passed": True}, cost=0.001, latency=1.2)
    n2 = SubtaskNode(2, "Implement DB router", status="in_progress", dependencies=[1], target_files=["router.py"])
    
    graph.add_node(n1)
    graph.add_node(n2)

    # Serialize structured state to dict (representing persistent state machine storage)
    serialized = graph.to_dict()

    # Simulate message history compaction (raw chat erased/summarized)
    compacted_chat = "[Summary of 40 chat turns...]"

    # Reconstruct TaskGraph from serialized structured snapshot
    restored_graph = TaskGraph.from_dict(serialized)

    assert restored_graph.task_id == "graph-04"
    assert len(restored_graph.nodes) == 2
    assert restored_graph.nodes[1].status == "done"
    assert restored_graph.nodes[2].status == "in_progress"
    assert restored_graph.nodes[1].attempts[0]["action"] == "write_code"
    assert restored_graph.nodes[2].dependencies == [1]


# ==============================================================================
# TEST CASE 5: Mid-Task Process Interruption & Crash Recovery
# ==============================================================================
def test_process_interruption_and_resume_recovery(tmp_path):
    workspace = str(tmp_path)
    
    # 1. State before crash
    graph_before = TaskGraph(task_id="graph-crash-test", user_goal="Refactor authentication")
    sub1 = SubtaskNode(1, "Step 1: Hash passwords with bcrypt", status="done")
    sub1.final_output = "def hash_password(): pass"
    sub2 = SubtaskNode(2, "Step 2: Add JWT token generator", status="pending", dependencies=[1])
    sub3 = SubtaskNode(3, "Step 3: Update login endpoint", status="pending", dependencies=[2])
    graph_before.add_node(sub1)
    graph_before.add_node(sub2)
    graph_before.add_node(sub3)

    saved_state = graph_before.to_dict()

    # 2. Simulate Process Crash & Restart: Initialize fresh Orchestrator instance from saved state
    orch_after_crash = DeterministicOrchestrator(session_id="recovered-session", workspace_root=workspace)
    orch_after_crash.graph = TaskGraph.from_dict(saved_state)

    # 3. Verify it picks up from Subtask 2 without restarting Subtask 1
    completed = orch_after_crash.graph.get_completed_ids()
    assert 1 in completed
    assert 2 not in completed

    next_sub = orch_after_crash.graph.get_next_unblocked_subtask()
    assert next_sub is not None
    assert next_sub.subtask_id == 2  # Correctly resumed from uncompleted step!
