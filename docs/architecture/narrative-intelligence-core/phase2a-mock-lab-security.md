# Phase 2A Mock Lab Security

## Flag

`WHOLE_BOOK_MOCK_LAB_ENABLED` default **false**. Release builds stay closed.

## Allow only when ALL true

1. environment is `development` or `test`
2. `WHOLE_BOOK_MOCK_LAB_ENABLED=true`
3. request from loopback
4. request declares mock lab marker (`X-StoryLens-Mock-Lab: 1`)
5. Engine is `MockWholeBookAnalysisEngine` (`mock_whole_book_v0`)
6. Engine `non_production=true`
7. Book Snapshot `completed`
8. Capability Context marked Lab/test
9. no formal License bypass
10. no commercial usage write

## Decision DTO

`MockLabAuthorizationDecision`: allowed, reason_code, environment, loopback, lab_enabled, requested_engine_id, engine_is_mock, non_production, evaluated_at.

## Deny reasons

- MOCK_LAB_DISABLED
- MOCK_LAB_ENVIRONMENT_NOT_ALLOWED
- MOCK_LAB_LOOPBACK_REQUIRED
- MOCK_LAB_ENGINE_REQUIRED
- MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE
- MOCK_LAB_REQUEST_MARKER_REQUIRED

## Hard rules

- Lab auth must not mutate Capability metadata
- Lab auth must not mark `whole_book_analysis` shipped
- Lab auth must not persist as formal License
- Lab path must fail closed in production builds
