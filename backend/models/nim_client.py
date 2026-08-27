import time
import httpx
import re
import json
from typing import List, Dict, Any, Optional, AsyncGenerator
from backend.config import settings

class NIMClient:
    _shared_async_client: Optional[httpx.AsyncClient] = None

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.nvidia_base_url).rstrip("/")
        self._working_model_cache: Dict[str, str] = {}

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls._shared_async_client is None or cls._shared_async_client.is_closed:
            cls._shared_async_client = httpx.AsyncClient(
                verify=False,
                timeout=httpx.Timeout(connect=5.0, read=35.0, write=10.0, pool=10.0),
                limits=httpx.Limits(max_keepalive_connections=50, max_connections=150, keepalive_expiry=60.0),
            )
        return cls._shared_async_client

    def _get_headers(self, key: str) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}"
        }

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        api_key: Optional[str] = None,
        role_id: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: float = 25.0,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        
        role_cfg = settings.get_role_config(role_id) if role_id else None
        target_model = role_cfg.model if role_cfg else model
        target_key = api_key or (role_cfg.api_key if role_cfg else settings.role_planner.api_key)

        call_plan = [(target_model, target_key)]
        if role_id == "planner" or "nemotron" in target_model:
            call_plan.append(("nvidia/nemotron-3.5-lightning-30b-a3b", settings.role_planner.api_key))
            call_plan.append(("openai/gpt-oss-20b", settings.role_router.api_key))
            call_plan.append(("meta/muse-glimmer-30b", settings.role_critic.api_key))
        elif role_id == "coder" or "gemma" in target_model:
            call_plan.append(("google/gemma-4-31b-it", settings.role_coder.api_key))
            call_plan.append(("mistralai/codestral-22b-instruct-v0.1", settings.role_coder.api_key))
            call_plan.append(("nvidia/nemotron-3.5-lightning-30b-a3b", settings.role_planner.api_key))
        elif role_id == "critic" or "muse" in target_model or "glimmer" in target_model:
            call_plan.append(("meta/muse-glimmer-30b", settings.role_critic.api_key))
            call_plan.append(("nvidia/nemotron-3.5-lightning-30b-a3b", settings.role_planner.api_key))
        else:
            call_plan.append(("openai/gpt-oss-20b", settings.role_router.api_key))
            call_plan.append(("nvidia/nemotron-3.5-lightning-30b-a3b", settings.role_planner.api_key))
            call_plan.append(("meta/muse-glimmer-30b", settings.role_critic.api_key))

        seen = set()
        deduped_plan = []
        for m_name, k_val in call_plan:
            pair = (m_name, k_val)
            if pair not in seen and k_val:
                seen.add(pair)
                deduped_plan.append(pair)

        prepared_messages = list(messages)
        start_time = time.time()
        client = self.get_client()
        last_error = ""

        for attempt_model, attempt_key in deduped_plan:
            payload = {
                "model": attempt_model,
                "messages": prepared_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            per_model_timeout = timeout or 25.0
            try:
                response = await client.post(url, headers=self._get_headers(attempt_key), json=payload, timeout=per_model_timeout)
                elapsed = time.time() - start_time
                if response.status_code == 200:
                    data = response.json()
                    choice = data["choices"][0]["message"]
                    reasoning = choice.get("reasoning_content") or choice.get("reasoning") or ""
                    raw_content = choice.get("content") or ""
                    if "<think>" in raw_content:
                        think_match = re.search(r'<think>(.*?)(?:</think>|$)', raw_content, re.DOTALL)
                        if think_match:
                            extracted_think = think_match.group(1).strip()
                            if not reasoning:
                                reasoning = extracted_think
                            raw_content = re.sub(r'<think>.*?(?:</think>|$)', '', raw_content, flags=re.DOTALL).strip()
                    if not raw_content and reasoning:
                        raw_content = reasoning
                    usage = data.get("usage", {})
                    if role_id:
                        self._working_model_cache[role_id] = attempt_model
                    return {
                        "content": raw_content,
                        "thinking": reasoning,
                        "model": data.get("model", attempt_model),
                        "input_tokens": usage.get("prompt_tokens", 0),
                        "output_tokens": usage.get("completion_tokens", 0),
                        "latency_seconds": elapsed,
                        "cached": False,
                    }
                else:
                    last_error = f"Model {attempt_model} HTTP {response.status_code}: {response.text[:80]}"
                    continue
            except Exception as e:
                last_error = f"Model {attempt_model} exception: {str(e)}"
                continue

        raise RuntimeError(f"NVIDIA NIM API call failed for role '{role_id or model}'. Details: {last_error}")

    async def stream_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        api_key: Optional[str] = None,
        role_id: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = f"{self.base_url}/chat/completions"
        role_cfg = settings.get_role_config(role_id) if role_id else None
        target_model = role_cfg.model if role_cfg else model
        target_key = api_key or (role_cfg.api_key if role_cfg else settings.role_planner.api_key)

        call_plan = [(target_model, target_key)]
        if role_id == "router" or "gpt-oss" in target_model:
            call_plan.append(("openai/gpt-oss-20b", settings.role_router.api_key))
            call_plan.append(("nvidia/nemotron-3.5-lightning-30b-a3b", settings.role_planner.api_key))
            call_plan.append(("meta/muse-glimmer-30b", settings.role_critic.api_key))
        elif role_id == "coder" or "gemma" in target_model:
            call_plan.append(("google/gemma-4-31b-it", settings.role_coder.api_key))
            call_plan.append(("mistralai/codestral-22b-instruct-v0.1", settings.role_coder.api_key))
            call_plan.append(("nvidia/nemotron-3.5-lightning-30b-a3b", settings.role_planner.api_key))
        else:
            call_plan.append(("nvidia/nemotron-3.5-lightning-30b-a3b", settings.role_planner.api_key))
            call_plan.append(("openai/gpt-oss-20b", settings.role_router.api_key))
            call_plan.append(("meta/muse-glimmer-30b", settings.role_critic.api_key))

        client = self.get_client()
        prepared_messages = list(messages)

        for attempt_model, attempt_key in call_plan:
            if not attempt_key:
                continue
            payload = {
                "model": attempt_model,
                "messages": prepared_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
            stream_timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
            accumulated_reasoning = ""
            accumulated_content = ""
            yielded_content_count = 0
            
            try:
                async with client.stream("POST", url, headers=self._get_headers(attempt_key), json=payload, timeout=stream_timeout) as resp:
                    if resp.status_code == 200:
                        in_think = False
                        async for line in resp.aiter_lines():
                            if line.startswith("data: ") and line != "data: [DONE]":
                                raw_json = line[6:].strip()
                                if not raw_json:
                                    continue
                                try:
                                    chunk = json.loads(raw_json)
                                    choices = chunk.get("choices", [])
                                    if not choices:
                                        continue
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content") or ""
                                    reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                                    
                                    if "<think>" in content:
                                        in_think = True
                                        content = content.replace("<think>", "")
                                    if "</think>" in content:
                                        in_think = False
                                        content = content.replace("</think>", "")

                                    if in_think:
                                        accumulated_reasoning += (content or reasoning)
                                        yield {"type": "thinking_chunk", "chunk": content or reasoning}
                                    elif reasoning and not content:
                                        accumulated_reasoning += reasoning
                                        yield {"type": "thinking_chunk", "chunk": reasoning}
                                    elif content:
                                        accumulated_content += content
                                        yielded_content_count += 1
                                        yield {"type": "content_chunk", "chunk": content}
                                except Exception:
                                    pass
                        
                        if yielded_content_count == 0 and accumulated_reasoning:
                            yield {"type": "content_chunk", "chunk": accumulated_reasoning}
                            return
                        elif yielded_content_count > 0:
                            return
            except Exception:
                continue
