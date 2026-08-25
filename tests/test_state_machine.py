import os
import tempfile
import pytest
import pytest_asyncio
from backend.models.nim_client import NIMClient
from backend.models.router import SmartRouter
from backend.tools.executor import ToolExecutor
from backend.orchestrator.state_machine import AgentZeroOrchestrator

@pytest.mark.asyncio
async def test_state_machine_planning_and_step_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        router = SmartRouter(client=NIMClient(api_key="mock_key"))
        tools = ToolExecutor(tmpdir)
        
        orch = AgentZeroOrchestrator(
            session_id="test-orch-session",
            workspace_root=tmpdir,
            router=router,
            tool_executor=tools,
        )
        
        plan = await orch.plan_task("Add binary search helper")
        assert len(plan) >= 2
        assert plan[0].status == "pending"
        
        step_res = await orch.execute_step(0)
        assert "step" in step_res
        assert step_res["step"]["status"] in ["completed", "waiting_approval"]

@pytest.mark.asyncio
async def test_isolated_bytheway_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        router = SmartRouter(client=NIMClient(api_key="mock_key"))
        orch = AgentZeroOrchestrator(
            session_id="test-bytheway-session",
            workspace_root=tmpdir,
            router=router,
        )
        
        res = await orch.execute_bytheway("What is the time complexity of quicksort?")
        assert res["query"] == "What is the time complexity of quicksort?"
        assert "answer" in res
        assert res["latency"] >= 0.0
