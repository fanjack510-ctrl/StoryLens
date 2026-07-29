# CHG-20260729-009 Manual Environment Validation Failure Audit

## Summary

Settings UI 「重新验证」调用的是 `POST /api/v1/desktop/ai-setup/recommended-qwen`，
不是 `/api/v1/model-providers/{name}/test`。

隔离环境已启用 `STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1`，请求**进入了 Fake generate**，
**未发生真实阿里云 HTTP**。但 Fake 合成文本面向章节分析 Parser，对 connection-test /
recommended-qwen 最小探测返回的是场景 JSON（无 `status: "ok"`），产品逻辑将其映射为
`MODEL_NOT_AVAILABLE`（文案「模型不存在或无权限」），并**覆盖**了原先预置的成功
validation snapshot。

结论：验收环境缺口（Fake 未覆盖 Settings 验证契约），不是 CHG-009 健康一致性业务规则回归。

## Evidence (isolated DB snapshot after 20:25)

- `validated_at`: `2026-07-29T12:25:48.936607+00:00`（本地显示约 `2026-07-29 20:25`）
- `validation_status`: `failed`
- `failure_category`: `MODEL_NOT_AVAILABLE`
- `failure_message`: `模型返回了非预期响应`
- `provider_key`: `aliyun_qwen_plus`
- `model_id` / `response_model`: `qwen3.7-plus`
- `provider_request_id`: `null`（符合 Fake / 未记真实 Provider request id）

Source code mapping:

```text
recommended_ai_setup._async_model_validate
  → provider.generate(...)
  → extract_json_object / json.loads
  → if payload.get("status") != "ok":
        error_code = MODEL_NOT_AVAILABLE
        detail = "模型返回了非预期响应"
ai_validation_snapshot.FAILURE_CATEGORY_COPY["MODEL_NOT_AVAILABLE"]
  → "模型不存在或无权限"
```

API access log (MG): multiple `POST /api/v1/desktop/ai-setup/recommended-qwen` → HTTP 200
（业务失败以 JSON `ok:false` 返回，不是 4xx/5xx）。

## Checklist answers

| # | Question | Answer |
|---|----------|--------|
| 1 | UI 调用了哪个验证 API？ | `POST /api/v1/desktop/ai-setup/recommended-qwen`（`configureRecommendedQwenService`，`persist:false` 时为「重新验证」） |
| 2 | API 是否进入 Fake Provider？ | **是**。`OpenAICompatibleProvider.generate` 在 smoke fake 启用时走 `chapter_smoke_fake_generate` |
| 3 | transport 类型？ | Chapter-analysis smoke fake transport（进程内合成，非 httpx 出站） |
| 4 | resolved provider？ | `aliyun_qwen_plus` |
| 5 | resolved model？ | `qwen3.7-plus`（`plus_model` / snapshot `model_id`） |
| 6 | 是否发生外部网络请求？ | **未发现** dashscope 出站；失败 detail 为「非预期响应」而非 HTTP/鉴权错误；`provider_request_id=null` |
| 7 | 「模型不存在或无权限」由哪段逻辑返回？ | `ai_validation_snapshot.FAILURE_CATEGORY_COPY["MODEL_NOT_AVAILABLE"]`，由 `_async_model_validate` 在 Fake JSON 缺 `status=ok` 时写入 |
| 8 | Fake 模型白名单是否包含 qwen3.7-plus？ | Smoke fake **不按模型白名单拦截**；模型名原样回传。问题不是白名单 |
| 9 | connection_test 是否绕过 Fake？ | Settings 验证**不走** `run_connection_test`；走 recommended-qwen → `provider.generate`。该 generate **未绕过** Fake，但 Fake **响应契约错误** |
| 10 | Fake 只覆盖 generate，没有覆盖 connection_test？ | Fake 覆盖了 generate 入口；**未**为 connection-test / recommended-qwen 最小 JSON（`{"status":"ok"}`）提供正确合成。`/test` connection_test 若调用，同样会因 Fake 返回场景 JSON 而 Schema 失败 |
| 11 | 失败结果是否覆盖 validation snapshot？ | **是**。`configure_recommended_qwen` 失败分支调用 `_record_probe_snapshot(ok=False, failure_category=MODEL_NOT_AVAILABLE)` |
| 12 | 是否错误读取正式 Keyring？ | MG launcher 注入 `FakeCredentialStore`；snapshot credential fingerprint 与隔离 Fake key 一致；config-profile 曾报告 `FakeCredentialStore` / `shares_with_packaged=false`。本次失败模式不符合「读到真实 Key 后真实 404/无权限」 |

## Root cause (environment)

1. 旧 MG 只预置成功 snapshot，未用真实 UI 验证链路验收。
2. Smoke Fake 面向章节分析 Parser；Settings/connection minimal probe 需要 `{"status":"ok"}`。
3. Fake 返回场景 JSON → 产品判 `MODEL_NOT_AVAILABLE` → 覆盖成功 snapshot → 人工复测阻塞。

## Remediation for V2 MG (harness only; no product rule change)

- Launcher patch：当 prompt 为 connection-test / recommended-qwen 最小探测时，Fake 返回 `{"status":"ok"}`。
- Fake 同时覆盖：Settings 验证、`connection_test` generate、分析 generate。
- 禁止仅 DB 预置成功 snapshot 交给用户；用户环境初始 `NOT_VERIFIED`，必须能点击「重新验证」成功。
- 继续 FakeCredentialStore + Real Provider OFF；外部网络计数 0；不写正式 AppData/Keyring。

## Classification

`MANUAL RETEST BLOCKED BY INVALID TEST ENVIRONMENT`
