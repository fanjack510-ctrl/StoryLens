# REAL_PROVIDER_CALLS — CHG-20260807-054

Run ID：1（isolated temp DB）

| attempt_id | provider_id | model_name | status | input_tokens | output_tokens |
|---|---|---|---|---|---|
| 1 | aliyun_qwen_plus | qwen3.7-plus | succeeded | 13222 | 1024 |
| 2 | aliyun_qwen_plus | qwen3.7-plus | succeeded | 613 | 592 |
| 3 | aliyun_qwen_plus | qwen3.7-plus | succeeded | 1469 | 50 |
| 4 | aliyun_qwen_plus | qwen3.7-plus | succeeded | 412 | 370 |

Mapping（同 Run）：
1. window analysis（characters/events 上游）
2. overview
3. structure_stages
4. chapter_functions

- FAILED PROVIDER CALLS：0
- RETRY CALLS：0
- REPAIR CALLS：0（本短样本未触发 CF contract repair）
- DUPLICATE PROVIDER CALLS：0
- 无完整 prompt / response / API Key 写入本文件
