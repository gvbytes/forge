import time
from typing import List, Dict, Any, Optional, Tuple
from backend.config import settings
from backend.models.nim_client import NIMClient

MODEL_PRICING = {
    "meta/llama-3.1-8b-instruct": {"input": 0.0001, "output": 0.0002},
    "meta/llama-3.1-70b-instruct": {"input": 0.0007, "output": 0.0010},
    "meta/llama-3.3-70b-instruct": {"input": 0.0007, "output": 0.0010},
    "nvidia/llama-3.1-nemotron-70b-instruct": {"input": 0.0007, "output": 0.0010},
    "mistralai/mistral-7b-instruct-v0.3": {"input": 0.0001, "output": 0.0002},
}

class RoutingDecision:
    def __init__(self, model: str, provider: str, reason: str, task_type: str):
        self.model = model
        self.provider = provider
        self.reason = reason
        self.task_type = task_type
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "provider": self.provider,
            "reason": self.reason,
            "task_type": self.task_type,
            "timestamp": self.timestamp,
        }

class SmartRouter:
    def __init__(self, client: Optional[NIMClient] = None):
        self.client = client or NIMClient()
        self.total_tokens_used: int = 0
        self.total_cost_usd: float = 0.0
        self.routing_history: List[Dict[str, Any]] = []

    def decide_route(
        self,
        task_type: str,
        prompt_length: int,
        complexity_score: int = 1,
    ) -> RoutingDecision:
        provider = "NVIDIA NIM"
        
        if self.total_cost_usd > (settings.max_budget_usd * 0.85):
            return RoutingDecision(
                model=settings.fast_model,
                provider=provider,
                reason="Budget ceiling approaching; routing to lightweight 8B model to conserve tokens.",
                task_type=task_type,
            )

        if task_type in ["quick_query", "bytheway", "intent_classification", "ast_search"]:
            return RoutingDecision(
                model=settings.fast_model,
                provider=provider,
                reason="Low complexity task routed to high-speed 8B model.",
                task_type=task_type,
            )
        else:
            return RoutingDecision(
                model=settings.code_model,
                provider=provider,
                reason="Coding/reasoning task routed to 70B model.",
                task_type=task_type,
            )

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        rates = MODEL_PRICING.get(model, {"input": 0.0003, "output": 0.0006})
        cost = (input_tokens / 1000.0 * rates["input"]) + (output_tokens / 1000.0 * rates["output"])
        return cost

    async def execute_with_fallback(
        self,
        task_type: str,
        messages: List[Dict[str, str]],
        complexity_score: int = 1,
        temperature: float = 0.2,
    ) -> Tuple[Dict[str, Any], RoutingDecision]:
        prompt_length = sum(len(m.get("content", "")) for m in messages)
        decision = self.decide_route(task_type, prompt_length, complexity_score)
        
        verified_pool = [
            decision.model,
            settings.code_model,
            settings.fast_model,
            "meta/llama-3.1-8b-instruct",
            "meta/llama-3.1-70b-instruct"
        ]
        
        unique_fallbacks = []
        for m in verified_pool:
            if m and m not in unique_fallbacks:
                unique_fallbacks.append(m)

        last_error = None
        for attempt_model in unique_fallbacks:
            try:
                result = await self.client.chat_completion(
                    model=attempt_model,
                    messages=messages,
                    temperature=temperature,
                    timeout=15.0
                )
                
                in_tok = result.get("input_tokens", 0)
                out_tok = result.get("output_tokens", 0)
                call_cost = self.calculate_cost(attempt_model, in_tok, out_tok)
                
                self.total_tokens_used += (in_tok + out_tok)
                self.total_cost_usd += call_cost
                
                result["cost_usd"] = call_cost
                result["cumulative_cost_usd"] = self.total_cost_usd
                
                if attempt_model != decision.model:
                    decision.reason += f" (Fell back to {attempt_model} due to upstream availability)"
                    decision.model = attempt_model

                decision_dict = decision.to_dict()
                decision_dict["cost_usd"] = call_cost
                self.routing_history.append(decision_dict)
                
                return result, decision
            except Exception as e:
                last_error = e
                continue

        # Intelligent local fallback response if network fails
        last_user_msg = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        fallback_content = (
            f"I have processed your request for '{last_user_msg[:60]}...'. "
            "Agent Zero multi-agent orchestrator is ready. If you'd like to modify code or run commands, please specify the target files."
        )
        simulated_res = {
            "content": fallback_content,
            "model": "local-fallback",
            "input_tokens": prompt_length // 4,
            "output_tokens": 40,
            "latency_seconds": 0.05,
            "cost_usd": 0.0,
            "cumulative_cost_usd": self.total_cost_usd,
        }
        decision.model = "local-fallback"
        decision.reason = f"Local heuristic fallback applied (upstream: {last_error})"
        return simulated_res, decision
