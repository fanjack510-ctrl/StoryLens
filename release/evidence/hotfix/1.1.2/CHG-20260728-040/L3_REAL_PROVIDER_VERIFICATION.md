# L3 Real Provider Verification — CHG-20260728-040

- Success: **True**
- Provider/Model: `aliyun_qwen_plus` / `qwen3.7-plus`
- Batches: 2
- Logical calls: 2
- Actual HTTP calls: 2
- Candidates covered: 20
- Fixed 768 absent: True
- Retry limits strictly increasing: True
- Estimated cost CNY: 0.02787
- Formal DB writes: 0 (temp DB deleted=True)

Initial limits:
```json
[
  {
    "batch_index": 0,
    "target_count": 10,
    "context_count": 1,
    "initial_output_limit": 1792,
    "effective_hard_cap": 4000
  },
  {
    "batch_index": 1,
    "target_count": 10,
    "context_count": 1,
    "initial_output_limit": 1792,
    "effective_hard_cap": 4000
  }
]
```

Call log (no prompt/response bodies):
```json
[
  {
    "call_index": 1,
    "requested_output_tokens": 1792,
    "finish_reason": "stop",
    "input_tokens": 4484,
    "output_tokens": 620,
    "total_tokens": 5104,
    "estimated_cost_cny": 0.013928,
    "latency_ms": 12889,
    "http_status": 200,
    "model": "qwen3.7-plus",
    "request_id": "09c9c4bf-5c62-97d9-a534-f7ef8569b95d"
  },
  {
    "call_index": 2,
    "requested_output_tokens": 1792,
    "finish_reason": "stop",
    "input_tokens": 4491,
    "output_tokens": 620,
    "total_tokens": 5111,
    "estimated_cost_cny": 0.013942,
    "latency_ms": 12593,
    "http_status": 200,
    "model": "qwen3.7-plus",
    "request_id": "56174cf1-8579-9467-8f75-5c53a9cd5b4f"
  }
]
```
