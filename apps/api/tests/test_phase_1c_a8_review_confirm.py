import json

from sqlalchemy import select

from app.db.models import (
    ApplicationSetting,
    BoundaryReviewDecision,
    ProviderConfiguration,
)
from app.model_gateway.base import ProviderCapabilities
from app.services.boundary_review_service import create_review_session
from tests.test_phase_1c_a import seed


def test_confirm_api_returns_pending_transition_ids(client, fake_provider):
    """Legacy /confirm is blocked in confirm_only; incomplete stays on final-proposal path."""
    from app.db.session import get_session_factory
    from app.main import app
    from app.services.credentials.service import get_credential_store

    class Store:
        def available(self):
            return True

        def get(self, _):
            return "secret"

        def set(self, *_):
            pass

        def delete(self, *_):
            pass

    factory = app.dependency_overrides[get_session_factory]()
    app.dependency_overrides[get_credential_store] = lambda: Store()
    fake_provider.name = "aliyun_qwen_plus"
    fake_provider.default_model = "configured-plus"
    fake_provider.capabilities = lambda: ProviderCapabilities(
        max_context_tokens=32000,
        default_timeout_seconds=10,
        enabled=True,
        cloud=True,
        supports_boundary_candidates=True,
        requires_boundary_review=True,
    )
    with factory() as session:
        _, _, _, run = seed(session)
        run.provider = "aliyun_qwen_plus"
        run.model = "configured-plus"
        run.status = "awaiting_boundary_review"
        session.add(ApplicationSetting(key="cloud_enabled", value_json="true"))
        session.add(
            ApplicationSetting(
                key="cloud_budget_settings",
                value_json=json.dumps(
                    {
                        "cloud_request_budget_enabled": True,
                        "cloud_daily_request_limit": 500,
                        "cloud_daily_token_limit": 500000,
                        "cloud_daily_estimated_cost_limit": 50,
                    }
                ),
            )
        )
        session.add(
            ProviderConfiguration(
                provider_name="aliyun_qwen_plus",
                enabled=True,
                disconnected=False,
                allow_auto_route=False,
                base_url="https://redacted.invalid/v1",
                credential_reference="keyring:aliyun_qwen_plus",
            )
        )
        review = create_review_session(session, run)
        session.commit()
        review_id = review.id
        pending = [
            item.transition_id
            for item in session.scalars(
                select(BoundaryReviewDecision).where(
                    BoundaryReviewDecision.review_session_id == review_id,
                    BoundaryReviewDecision.model_candidate.is_(True),
                    BoundaryReviewDecision.user_decision == "pending",
                )
            )
        ]

    denied = client.post(
        f"/api/v1/boundary-reviews/{review_id}/confirm",
        json={"confirmed_by": "tester"},
    )
    assert denied.status_code == 409
    body = denied.json()
    assert body["error_code"] == "CONFIRM_ONLY_MODE"
    assert pending, "seed must leave at least one pending model candidate"

    # Confirm-only path still surfaces incomplete/pending via service contract.
    from app.services.boundary_review_service import BoundaryReviewIncomplete, confirm_review

    with factory() as session:
        from app.db.models import BoundaryReviewSession

        review_row = session.get(BoundaryReviewSession, review_id)
        try:
            confirm_review(session, review_row, "tester")
            raise AssertionError("expected BoundaryReviewIncomplete")
        except BoundaryReviewIncomplete as raised:
            assert raised.pending_count == len(pending)
            assert set(raised.pending_transition_ids) == set(pending)
            detail = raised.as_error_detail()
            assert detail["error_code"] == "BOUNDARY_REVIEW_INCOMPLETE"
            assert detail["retryable"] is False
