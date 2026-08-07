# REAL_PATH_IMPLEMENTATION — CHG-20260807-054

## Code changes (Public)

| File | Change |
|---|---|
| `whole_book_free_product_v1_service.py` | Remove capability hard stub; formal create → resolve provider + shared pipeline |
| `whole_book_minimal_pipeline_v1_service.py` | **NEW** shared pipeline + fixture/formal transport builders |
| `whole_book_fixture_pipeline_v1_service.py` | Delegate to shared pipeline with Fixture transports only |
| `whole_book_gateway_transport_v1.py` | **NEW** Gateway window/overview/structure/CF transports |
| `whole_book_provider_orchestrator.py` | Return `result_payload`; provider/model from transport |
| `whole_book_minimal_{extraction,overview,structure,chapter_functions}_v1_service.py` | Prefer orchestrator `result_payload`（避免二次 invoke） |
| `whole_book_window_response_validation_v1.py` | Formal provenance only forbidden on fixture runs |
| `tests/test_whole_book_chg054_real_provider_path.py` | Wiring tests |

## Desktop / Private

- Desktop: **not modified**（API 正式 Create 已可走通）
- Private: **not modified**（经现有 ModelGateway / keyring 边界调用）

## Product path

Prepare → Cost Estimate → Consent → Create → Provider Units → Materialize → project_result → finalize
