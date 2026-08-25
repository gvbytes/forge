import pytest
import pytest_asyncio
from backend.config import settings
from backend.models.router import SmartRouter, RoutingDecision
from backend.models.nim_client import NIMClient

@pytest.mark.asyncio
async def test_router_decision_logic():
    router = SmartRouter(client=NIMClient(api_key="mock_key"))
    
    dec_bytheway = router.decide_route(task_type="bytheway", prompt_length=100)
    assert dec_bytheway.model == settings.fast_model
    
    dec_code = router.decide_route(task_type="code_generation", prompt_length=2000, complexity_score=2)
    assert dec_code.model == settings.code_model
    
    dec_reasoning = router.decide_route(task_type="planning", prompt_length=2000, complexity_score=3)
    assert dec_reasoning.model == settings.reasoning_model

@pytest.mark.asyncio
async def test_router_execution_and_cost_tracking():
    router = SmartRouter(client=NIMClient(api_key="mock_key"))
    messages = [{"role": "user", "content": "Write quick test function"}]
    
    resp, dec = await router.execute_with_fallback(
        task_type="bytheway",
        messages=messages
    )
    
    assert "content" in resp
    assert router.total_tokens_used > 0
    assert len(router.routing_history) == 1
    assert router.routing_history[0]["model"] == settings.fast_model
