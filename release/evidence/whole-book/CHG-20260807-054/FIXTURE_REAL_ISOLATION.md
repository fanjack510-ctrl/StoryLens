# FIXTURE_REAL_ISOLATION — CHG-20260807-054

## Formal Create

- Entry: `POST .../whole-book/free/create` → `create_free_whole_book_analysis_v1`
- `ResultOrigin.formal`
- Transports: Gateway* only
- Forbidden: Fixture transport、CountingFake 作为正式默认、静默降级

## Fixture Preview

- Entry: `create-fixture` / `runs/fixture`
- `ResultOrigin.fixture`
- Transports: Fixture* only
- Independent of `STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED`（real flag 只闸 formal create）
- 即使 real flag ON，fixture run 不写 `aliyun_qwen_plus` attempts

## Validation

- Formal provenance on fixture run: forbidden
- Formal provenance allowed when `run.result_origin == formal`
