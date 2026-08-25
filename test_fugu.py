import asyncio
import httpx
import json

async def test_fugu():
    url = 'http://127.0.0.1:8000/api/chat/stream'
    payload = {'message': 'write a python function to compute fibonacci numbers', 'session_id': 'test-fugu-separation'}
    
    stages = []
    chat_chunks = []
    code_chunks = []
    metrics = {}
    
    async with httpx.AsyncClient() as client:
        async with client.stream('POST', url, json=payload, timeout=30.0) as resp:
            print('HTTP Status:', resp.status_code)
            async for line in resp.aiter_lines():
                if line.startswith('data: '):
                    raw = line[6:].strip()
                    if raw and raw != '[DONE]':
                        try:
                            ev = json.loads(raw)
                            t = ev.get('type')
                            if t == 'orch_stage':
                                stages.append(ev.get('role', '') + ': ' + ev.get('label', ''))
                            elif t == 'chat_chunk':
                                chat_chunks.append(ev.get('chunk', ''))
                            elif t == 'code_chunk':
                                code_chunks.append(ev.get('chunk', ''))
                            elif t == 'metrics':
                                metrics = ev
                            elif t == 'done':
                                print('\n✓ Task Done Event Received!')
                        except Exception:
                            pass
                            
    print('\n1. FUGU ORCHESTRATION STAGES:')
    for s in stages:
        print('   ->', s)
        
    print(f'\n2. CHAT CHUNKS ({len(chat_chunks)} chunks):')
    chat_text = ''.join(chat_chunks).strip()
    print('   Chat text (Pure explanation):\n  ', repr(chat_text[:140]))
    has_leaked_code = '```' in chat_text
    print('   Has Leaked Code in Chat:', has_leaked_code, '(MUST BE FALSE)')
    
    print(f'\n3. CODE CHUNKS ({len(code_chunks)} chunks):')
    code_text = ''.join(code_chunks)
    print('   Code lines streamed to Monaco Editor:', len(code_text.splitlines()), 'lines')
    print('   Preview of Editor Buffer:\n', '\n'.join(code_text.strip().splitlines()[:6]))
    
    print('\n4. COST METRICS:')
    print('   Total Tokens:', metrics.get('total_tokens'))
    cost_val = metrics.get('total_cost_usd', 0)
    print('   Total Cost USD: $' + f'{cost_val:.6f}')

asyncio.run(test_fugu())
