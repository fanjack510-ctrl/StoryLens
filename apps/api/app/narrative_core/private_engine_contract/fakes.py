"""Central Fake fixture re-exports (Phase 2B-P)."""

from __future__ import annotations

from app.narrative_core.private_engine_contract.candidate import (
    FakeCandidateWriteFixture,
    fake_candidate_write_fixture,
)
from app.narrative_core.private_engine_contract.context import (
    FakeContextPipeline,
    fake_context_bundle,
)
from app.narrative_core.private_engine_contract.evaluation import (
    fake_evaluation_results,
    fake_evaluation_suite,
)
from app.narrative_core.private_engine_contract.evidence import fake_evidence_candidates
from app.narrative_core.private_engine_contract.loader import (
    FakePrivateWholeBookEngineLoader,
    FakeSignedEngineHandle,
)
from app.narrative_core.private_engine_contract.manifest import (
    fake_mock_manifest,
    fake_private_manifest,
)
from app.narrative_core.private_engine_contract.module_runner import FakeModuleRunner
from app.narrative_core.private_engine_contract.prompt_pack import (
    FakePromptPackBody,
    FakePromptPackManifest,
    fake_prompt_pack_manifest,
)
from app.narrative_core.private_engine_contract.provider_gateway import FakeProviderGateway
from app.narrative_core.private_engine_contract.usage import fake_usage_report
from app.narrative_core.private_engine_contract.validation import FakeModuleOutputValidator

__all__ = [
    "FakeCandidateWriteFixture",
    "FakeContextPipeline",
    "FakeModuleOutputValidator",
    "FakeModuleRunner",
    "FakePrivateWholeBookEngineLoader",
    "FakePromptPackBody",
    "FakePromptPackManifest",
    "FakeProviderGateway",
    "FakeSignedEngineHandle",
    "fake_candidate_write_fixture",
    "fake_context_bundle",
    "fake_evaluation_results",
    "fake_evaluation_suite",
    "fake_evidence_candidates",
    "fake_mock_manifest",
    "fake_private_manifest",
    "fake_prompt_pack_manifest",
    "fake_usage_report",
]
