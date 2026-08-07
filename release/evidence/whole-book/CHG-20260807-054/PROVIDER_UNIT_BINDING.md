# PROVIDER_UNIT_BINDING — CHG-20260807-054

## Shared pipeline

`execute_minimal_pipeline_v1`（`whole_book_minimal_pipeline_v1_service.py`）:

1. `extract_entities_events` → window units（characters/events 上游）
2. `materialize_assets`
3. `synthesize_overview`
4. `synthesize_structure_stages`
5. `synthesize_chapter_functions` → finalize

Fixture Preview：`build_fixture_transports`
Formal Create：`build_formal_gateway_transports`

## Formal transports → ModelGateway

| Stage / Unit | Transport | Provider | Model |
|---|---|---|---|
| window analysis | `GatewayWindowAnalysisTransport` | `aliyun_qwen_plus` | `qwen3.7-plus` |
| overview | `GatewayOverviewTransport` | same | same |
| structure_stages | `GatewayStructureTransport` | same | same |
| chapter_functions (+ repair unit key) | `GatewayChapterFunctionsTransport` | same | same |

Orchestrator records `provider_id` / `model_name` from transport attrs（不再硬编码 fake）。

## characters_events

- **Not** fixture-only / static materialize / overview-invented / old-asset reuse on formal path
- Produced by real window Provider Units → materialize（同一 Run / Snapshot）

## Contract

继续使用冻结 Provider Unit Contract + Pydantic / enum / evidence / repair 路径；Fake 与 Real 仅在 adapter 层分流。
