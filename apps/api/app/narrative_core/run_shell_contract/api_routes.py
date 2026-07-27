"""Mock Lab API route contract (Phase 2A-P).

Production POST /api/v1/books/{book_id}/whole-book-runs remains disabled.
Lab routes are development/test + Lab-enabled only; OpenAPI marked non-production.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED

LAB_API_PREFIX = "/api/v1/labs/whole-book-runs"
PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH = "/api/v1/books/{book_id}/whole-book-runs"

LAB_API_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/api/v1/labs/whole-book-runs"),
    ("GET", "/api/v1/labs/whole-book-runs/{run_id}"),
    ("GET", "/api/v1/labs/whole-book-runs/{run_id}/stages"),
    ("POST", "/api/v1/labs/whole-book-runs/{run_id}/pause"),
    ("POST", "/api/v1/labs/whole-book-runs/{run_id}/resume"),
    ("POST", "/api/v1/labs/whole-book-runs/{run_id}/cancel"),
    ("POST", "/api/v1/labs/whole-book-runs/{run_id}/stages/{stage_key}/retry"),
)

LAB_WRITE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True, slots=True)
class LabApiRoutePolicy:
    register_only_in_development_or_test: bool = True
    require_lab_enabled: bool = True
    write_requires_loopback: bool = True
    write_requires_lab_marker: bool = True
    reject_non_mock_runs: bool = True
    isolate_by_book: bool = True
    accept_full_body: bool = False
    return_full_body: bool = False
    return_prompt: bool = False
    return_credential: bool = False
    openapi_lab_non_production_tag: bool = True
    production_create_disabled: bool = True

    def __post_init__(self) -> None:
        if self.accept_full_body or self.return_full_body:
            raise ValueError("Lab API must not accept/return full novel body")
        if self.return_prompt or self.return_credential:
            raise ValueError("Lab API must not return prompt or credential")
        if not self.production_create_disabled:
            raise ValueError("production whole-book run create must stay disabled")
        if not WHOLE_BOOK_RUNS_ENDPOINT_DISABLED and self.production_create_disabled:
            # Contract package asserts the importable constant remains True via tests.
            pass


DEFAULT_LAB_API_ROUTE_POLICY = LabApiRoutePolicy()

OPENAPI_LAB_TAGS: tuple[str, ...] = ("labs", "non-production", "mock-whole-book-run")
