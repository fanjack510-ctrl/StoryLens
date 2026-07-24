"""Phase 2B Agent P — Private Engine Runtime foundation tests.

Focused suite only. Does not run full pytest collection.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

import pytest

from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey, WholeBookStageKey
from app.narrative_core.private_engine_contract.checkpoint import build_fake_checkpoint
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineError,
    PrivateEngineErrorCode,
)
from app.narrative_core.private_engine_contract.manifest import (
    PRIVATE_ENGINE_MANIFEST_SCHEMA,
    PRIVATE_ENGINE_MANIFEST_VERSION,
    EngineImplementationKind,
    fake_mock_manifest,
    fake_private_manifest,
)
from app.narrative_core.private_engine_contract.prompt_pack import (
    fake_prompt_pack_manifest,
)
from app.narrative_core.private_engine_contract.protocol import PrivateEngineExecutionRequest
from app.narrative_core.private_engine_contract.provider_gateway import ProviderInferenceRequest
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
from app.narrative_core.services.fake_private_whole_book_engine import FakePrivateWholeBookEngine
from app.narrative_core.services.private_engine_manifest_loader import (
    DefaultPrivateWholeBookEngineLoader,
    PrivateEngineManifestRepository,
    PromptPackCompatibilityValidator,
    PromptPackManifestRepository,
    write_fake_engine_package,
    write_fake_prompt_pack,
)
from app.narrative_core.services.private_engine_runtime_adapter import (
    PrivateWholeBookEngineRuntimeAdapter,
)
from app.narrative_core.services.private_engine_signature import (
    TEST_PUBLIC_KEY_FIXTURE,
    DeterministicFakeSignatureVerifier,
    PrivateEnginePackageVerifier,
    PromptPackPackageVerifier,
    compute_content_sha256_hex,
    deterministic_fake_signature,
)
from app.narrative_core.services.whole_book_engine_adapters import BudgetGuardAdapter
from app.narrative_core.services.whole_book_engine_registry import PRODUCTION_DEFAULT_ENGINE_ID
from app.narrative_core.services.whole_book_provider_gateway import (
    DefaultWholeBookProviderGateway,
    ExistingCredentialServiceAdapter,
    FakeProviderAdapter,
    NoCredentialFakeResolver,
    ProviderAdapterRegistry,
    assert_no_credential_in_logs,
)


def _request(**overrides):
    base = dict(
        run_id=1,
        stage_key=WholeBookStageKey.ANALYZE_STRUCTURE,
        attempt=0,
        book_id=1,
        book_snapshot_id=10,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        requested_module_keys=(WholeBookModuleKey.BOOK_OVERVIEW,),
        resolved_module_keys=(WholeBookModuleKey.BOOK_OVERVIEW,),
        context_bundle_ref="ctx:fake:bundle:1",
        provider_policy={"provider_kind": "fake"},
        budget_policy={"estimated_tokens": 8},
        output_locale="zh",
        source_language="zh",
        configuration_fingerprint="test-fp:fixed",
        prompt_pack_ref="fake.prompt_pack.first_four",
        cancellation_ref=None,
        checkpoint_ref=None,
        mock=False,
        requested_at=datetime(2026, 7, 23, 0, 0, 0),
    )
    base.update(overrides)
    return PrivateEngineExecutionRequest(**base)


def _provider_request(**overrides):
    base = dict(
        request_id="req-1",
        provider_kind="fake",
        model_route="fake/default",
        task_type="book_overview",
        system_instruction_ref="fake://instruction/first_four",
        prompt_pack_ref="fake.prompt_pack.first_four",
        input_bundle_ref="ctx:fake:bundle:1",
        response_schema_ref="fake://schema/book_overview",
        temperature_policy={"temperature": 0},
        token_budget=100,
        cost_budget=0.0,
        timeout_policy={"timeout_ms": 1000},
        retry_policy={"max_retries": 0},
        cancellation_ref=None,
        data_handling_policy={"execution_location": "local"},
        metadata={"synthetic": True},
    )
    base.update(overrides)
    return ProviderInferenceRequest(**base)


def test_01_manifest_discover(tmp_path: Path) -> None:
    write_fake_engine_package(tmp_path, fake_private_manifest())
    repo = PrivateEngineManifestRepository(tmp_path, production=False)
    found = repo.discover_manifests()
    assert len(found) == 1
    assert found[0].engine_id == "fake.signed.private_engine"


def test_02_schema_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "engine.manifest.json").write_text(
        json.dumps({"manifest_schema": "wrong", "manifest_version": "9.9.9", "engine_id": "x"}),
        encoding="utf-8",
    )
    repo = PrivateEngineManifestRepository(tmp_path, production=False)
    with pytest.raises(PrivateEngineError) as exc:
        repo.inspect_manifest("bad")
    assert exc.value.code in {
        PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE,
        PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
    }


def test_03_duplicate_engine(tmp_path: Path) -> None:
    manifest = fake_private_manifest()
    write_fake_engine_package(tmp_path, manifest, package_dirname="a")
    write_fake_engine_package(tmp_path, manifest, package_dirname="b")
    repo = PrivateEngineManifestRepository(tmp_path, production=False)
    with pytest.raises(PrivateEngineError) as exc:
        repo.discover_manifests()
    assert exc.value.detail_code == "duplicate_engine_id_version"


def test_04_package_hash(tmp_path: Path) -> None:
    content = b"fake-package-bytes"
    expected = compute_content_sha256_hex(content)
    verifier = PrivateEnginePackageVerifier(production=False)
    verifier.verify_package_hash(expected_hash=expected, actual_content=content)
    with pytest.raises(PrivateEngineError) as exc:
        verifier.verify_package_hash(expected_hash=expected, actual_content=b"other")
    assert exc.value.code == PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID


def test_05_signature_invalid(tmp_path: Path) -> None:
    manifest = fake_private_manifest(signed=True)
    package_dir = write_fake_engine_package(tmp_path, manifest, include_signature=True)
    (package_dir / "engine.signature.txt").write_text("fake-sig:deadbeef", encoding="utf-8")
    repo = PrivateEngineManifestRepository(tmp_path, production=False)
    loader = DefaultPrivateWholeBookEngineLoader(repository=repo, production=False)
    with pytest.raises(PrivateEngineError) as exc:
        loader.verify_package(manifest.engine_id)
    assert exc.value.code == PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID


def test_06_protocol_incompatible(tmp_path: Path) -> None:
    manifest = fake_private_manifest(protocol_version="storylens.private_engine.v0")
    write_fake_engine_package(tmp_path, manifest)
    repo = PrivateEngineManifestRepository(tmp_path, production=False)
    loader = DefaultPrivateWholeBookEngineLoader(repository=repo, production=False)
    with pytest.raises(PrivateEngineError) as exc:
        loader.verify_package(manifest.engine_id)
    assert exc.value.code == PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE


def test_07_app_version_incompatible(tmp_path: Path) -> None:
    manifest = fake_private_manifest(minimum_app_version="9.9.9")
    write_fake_engine_package(tmp_path, manifest)
    verifier = PrivateEnginePackageVerifier(app_version="1.0.5", production=False)
    inspection_sig = deterministic_fake_signature(
        package_hash=manifest.package_hash,
        subject_id=manifest.engine_id,
    )
    with pytest.raises(PrivateEngineError) as exc:
        verifier.verify_package(manifest, signature=inspection_sig)
    assert exc.value.code == PrivateEngineErrorCode.PRIVATE_ENGINE_APP_VERSION_INCOMPATIBLE


def test_08_production_unsigned_reject() -> None:
    manifest = replace(fake_private_manifest(signed=False), signed=False, signature_algorithm=None, non_production=False)
    verifier = PrivateEnginePackageVerifier(production=True)
    with pytest.raises(PrivateEngineError) as exc:
        verifier.verify_manifest(manifest, signature_valid=False)
    assert exc.value.code in {
        PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID,
        PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
    }


def test_09_production_fake_reject(tmp_path: Path) -> None:
    write_fake_engine_package(tmp_path, fake_private_manifest())
    repo = PrivateEngineManifestRepository(tmp_path, production=True)
    assert repo.discover_manifests() == ()
    loader = DefaultPrivateWholeBookEngineLoader(repository=repo, production=True)
    with pytest.raises(PrivateEngineError) as exc:
        loader.load("fake.signed.private_engine")
    assert exc.value.code == PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND


def test_10_no_mock_fallback(tmp_path: Path) -> None:
    write_fake_engine_package(tmp_path, fake_mock_manifest())
    repo = PrivateEngineManifestRepository(tmp_path, production=False)
    loader = DefaultPrivateWholeBookEngineLoader(repository=repo, production=False)
    with pytest.raises(PrivateEngineError) as exc:
        loader.load("mock.whole_book_analysis_engine")
    assert exc.value.detail_code == "no_mock_fallback"


def test_11_loader_load_fake(tmp_path: Path) -> None:
    write_fake_engine_package(tmp_path, fake_private_manifest())
    repo = PrivateEngineManifestRepository(tmp_path, production=False)
    loader = DefaultPrivateWholeBookEngineLoader(repository=repo, production=False)
    handle = loader.load("fake.signed.private_engine")
    assert handle.fake is True
    assert handle.real_binary is False
    assert handle.loaded is True


def test_12_loader_unload(tmp_path: Path) -> None:
    write_fake_engine_package(tmp_path, fake_private_manifest())
    loader = DefaultPrivateWholeBookEngineLoader(
        repository=PrivateEngineManifestRepository(tmp_path),
        production=False,
    )
    loader.load("fake.signed.private_engine")
    loader.unload("fake.signed.private_engine")
    loader.unload("fake.signed.private_engine")
    assert loader.get_loaded_engine("fake.signed.private_engine") is None


def test_13_health(tmp_path: Path) -> None:
    write_fake_engine_package(tmp_path, fake_private_manifest())
    loader = DefaultPrivateWholeBookEngineLoader(
        repository=PrivateEngineManifestRepository(tmp_path),
        production=False,
    )
    loader.load("fake.signed.private_engine")
    health = loader.health_check("fake.signed.private_engine")
    assert health.healthy is True
    assert "no_novel_analysis" in health.details or "fake" in health.details


def test_14_resolve_compatible(tmp_path: Path) -> None:
    write_fake_engine_package(tmp_path, fake_private_manifest())
    loader = DefaultPrivateWholeBookEngineLoader(
        repository=PrivateEngineManifestRepository(tmp_path),
        production=False,
    )
    resolved = loader.resolve_compatible_engine(
        mode=WholeBookAnalysisMode.NATIVE,
        app_version="1.0.5",
        production=False,
    )
    assert resolved is not None
    assert resolved.engine_id == "fake.signed.private_engine"
    assert (
        loader.resolve_compatible_engine(
            mode=WholeBookAnalysisMode.NATIVE,
            app_version="1.0.5",
            production=True,
        )
        is None
    )


def test_15_runtime_request_translation() -> None:
    pack = fake_prompt_pack_manifest().manifest
    engine = FakePrivateWholeBookEngine()
    adapter = PrivateWholeBookEngineRuntimeAdapter(engine=engine, prompt_pack=pack)
    req = _request()
    translated = adapter.translate_request(req)
    assert translated.context_bundle_ref == req.context_bundle_ref
    assert translated.book_snapshot_id == 10


def test_16_snapshot_binding() -> None:
    adapter = PrivateWholeBookEngineRuntimeAdapter(
        engine=FakePrivateWholeBookEngine(),
        prompt_pack=fake_prompt_pack_manifest().manifest,
    )
    with pytest.raises(PrivateEngineError) as exc:
        adapter.validate_execution_request(_request(book_snapshot_id=0))
    assert exc.value.code == PrivateEngineErrorCode.CONTEXT_BUNDLE_SNAPSHOT_MISMATCH


def test_17_fingerprint() -> None:
    pack = fake_prompt_pack_manifest().manifest
    adapter = PrivateWholeBookEngineRuntimeAdapter(
        engine=FakePrivateWholeBookEngine(),
        prompt_pack=pack,
    )
    fp = adapter.build_configuration_fingerprint(_request())
    assert "engine_id=" in fp
    assert pack.prompt_hash in fp
    assert "snapshot=10" in fp


def test_18_prompt_pack_version() -> None:
    pack = fake_prompt_pack_manifest().manifest
    adapter = PrivateWholeBookEngineRuntimeAdapter(
        engine=FakePrivateWholeBookEngine(),
        prompt_pack=pack,
    )
    req = _request()
    result = adapter.execute(req)
    cp = build_fake_checkpoint(
        book_snapshot_id=req.book_snapshot_id,
        configuration_fingerprint=req.configuration_fingerprint,
        context_bundle_hash=req.context_bundle_ref,
        prompt_pack_id=pack.prompt_pack_id,
        prompt_pack_version="9.9.9-other",
    )
    with pytest.raises(PrivateEngineError) as exc:
        adapter.resume(req, cp)
    assert exc.value.code == PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE
    assert result.status == "completed"


def test_19_result_translation() -> None:
    adapter = PrivateWholeBookEngineRuntimeAdapter(
        engine=FakePrivateWholeBookEngine(),
        prompt_pack=fake_prompt_pack_manifest().manifest,
    )
    result = adapter.execute(_request())
    assert result.asset_candidates == ()
    assert result.validation_summary.get("canonical") is False
    assert result.validation_summary.get("asset_written") is False
    assert "api_key" not in json.dumps(asdict(result), default=str)


def test_20_cancel() -> None:
    engine = FakePrivateWholeBookEngine()
    adapter = PrivateWholeBookEngineRuntimeAdapter(
        engine=engine,
        prompt_pack=fake_prompt_pack_manifest().manifest,
    )
    assert adapter.cancel("cancel-1") is True
    with pytest.raises(PrivateEngineError) as exc:
        adapter.execute(_request(cancellation_ref="cancel-1"))
    assert exc.value.code == PrivateEngineErrorCode.PROVIDER_CANCELLED


def test_21_checkpoint() -> None:
    pack = fake_prompt_pack_manifest().manifest
    adapter = PrivateWholeBookEngineRuntimeAdapter(
        engine=FakePrivateWholeBookEngine(),
        prompt_pack=pack,
    )
    req = _request()
    first = adapter.execute(req)
    assert first.checkpoint is not None
    resumed = adapter.resume(req, first.checkpoint)
    assert resumed.status == "resumed"


def test_22_provider_policy() -> None:
    gw = DefaultWholeBookProviderGateway()
    gw.validate_policy({"provider_kind": "fake", "model_route": "fake/default"})
    with pytest.raises(PrivateEngineError):
        gw.validate_policy({})
    with pytest.raises(PrivateEngineError):
        gw.validate_policy({"provider_kind": "openai", "model_route": "gpt"})


def test_23_fake_provider_execute() -> None:
    gw = DefaultWholeBookProviderGateway(credential_resolver=NoCredentialFakeResolver())
    response = gw.execute(_provider_request())
    assert response.status == "success"
    assert response.structured_output is not None
    assert response.structured_output.get("fake") is True


def test_24_provider_failure() -> None:
    adapter = FakeProviderAdapter(fail_next=True)
    registry = ProviderAdapterRegistry()
    registry.register(adapter)
    gw = DefaultWholeBookProviderGateway(registry=registry)
    with pytest.raises(PrivateEngineError) as exc:
        gw.execute(_provider_request())
    assert exc.value.code == PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID


def test_25_provider_cancel() -> None:
    gw = DefaultWholeBookProviderGateway()
    assert gw.cancel("c-1") is True
    with pytest.raises(PrivateEngineError) as exc:
        gw.execute(_provider_request(cancellation_ref="c-1"))
    assert exc.value.code == PrivateEngineErrorCode.PROVIDER_CANCELLED


def test_26_budget_retry() -> None:
    guard = BudgetGuardAdapter(max_tokens=200, allow=True)
    adapter = FakeProviderAdapter(fail_next=True)
    registry = ProviderAdapterRegistry()
    registry.register(adapter)
    gw = DefaultWholeBookProviderGateway(registry=registry, budget_guard=guard)
    response = gw.execute(_provider_request(retry_policy={"max_retries": 1}))
    assert response.status == "success"
    assert response.retry_count >= 1

    guard2 = BudgetGuardAdapter(max_tokens=1, allow=True)
    gw2 = DefaultWholeBookProviderGateway(budget_guard=guard2)
    with pytest.raises(PrivateEngineError) as exc:
        gw2.execute(_provider_request())
    assert exc.value.code == PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED


def test_27_usage_normalize() -> None:
    gw = DefaultWholeBookProviderGateway()
    response = gw.execute(_provider_request())
    usage = gw.normalize_usage(response)
    assert usage.synthetic is True


def test_28_credential_absent_from_dto() -> None:
    req = _provider_request()
    payload = asdict(req)
    for banned in ("api_key", "credential", "credentials", "authorization"):
        assert banned not in payload
        assert banned not in json.dumps(payload)


def test_29_credential_absent_from_logs() -> None:
    class _Store:
        def available(self) -> bool:
            return True

        def get(self, name: str) -> str | None:
            return "sk-test-should-not-log"

        def set(self, name: str, value: str) -> None:
            raise NotImplementedError

        def delete(self, name: str) -> None:
            raise NotImplementedError

    adapter = ExistingCredentialServiceAdapter(store=_Store(), enabled=True)
    secret = adapter.resolve("fake")
    assert secret == "sk-test-should-not-log"
    log_line = "provider execute kind=fake status=ok"
    assert_no_credential_in_logs(log_line)
    with pytest.raises(AssertionError):
        assert_no_credential_in_logs(f"provider key={secret}")


def test_30_prompt_manifest(tmp_path: Path) -> None:
    write_fake_prompt_pack(tmp_path)
    repo = PromptPackManifestRepository(tmp_path, production=False)
    packs = repo.discover()
    assert len(packs) == 1
    assert packs[0].prompt_pack_id == "fake.prompt_pack.first_four"
    assert "prompt_body" not in asdict(packs[0])


def test_31_prompt_compatibility() -> None:
    pack = fake_prompt_pack_manifest().manifest
    validator = PromptPackCompatibilityValidator()
    validator.assert_compatible(pack, engine_version="0.0.1-fake")
    with pytest.raises(PrivateEngineError) as exc:
        validator.assert_compatible(pack, engine_version="9.9.9")
    assert exc.value.code == PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE


def test_32_prompt_body_absent(tmp_path: Path) -> None:
    bad = tmp_path / "bad_pack"
    bad.mkdir()
    payload = {
        "prompt_pack_id": "x",
        "prompt_pack_version": "1",
        "private": False,
        "signed": False,
        "package_hash": "fake-prompt-pack-hash-0001",
        "supported_engine_versions": ["0.0.1-fake"],
        "supported_modules": ["book_overview"],
        "supported_languages": ["zh"],
        "output_schema_versions": ["1.0.0"],
        "instruction_ref": "fake://i",
        "template_refs": {},
        "example_set_refs": [],
        "evaluation_policy_ref": None,
        "created_at": "2026-07-23T00:00:00",
        "prompt_hash": "h",
        "non_production": True,
        "prompt_body": "SECRET PROMPT",
    }
    (bad / "prompt_pack.manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    repo = PromptPackManifestRepository(tmp_path, production=False)
    with pytest.raises(PrivateEngineError):
        repo.load_manifest("bad_pack")


def test_33_no_network() -> None:
    with pytest.raises(ValueError):
        DefaultWholeBookProviderGateway(allow_network=True)
    gw = DefaultWholeBookProviderGateway()
    assert gw.allow_network is False


def test_34_no_model() -> None:
    gw = DefaultWholeBookProviderGateway()
    health = gw.health_check("fake")
    assert "no_model_call" in health.details


def test_35_formal_run_disabled() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    assert PRODUCTION_DEFAULT_ENGINE_ID is None


def test_36_version_manager_check() -> None:
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "scripts/version_manager.py", "check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_37_change_registry_check() -> None:
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "scripts/change_registry.py", "check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_38_git_diff_check() -> None:
    import subprocess

    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["git", "diff", "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_39_path_traversal_rejected(tmp_path: Path) -> None:
    write_fake_engine_package(tmp_path, fake_private_manifest())
    repo = PrivateEngineManifestRepository(tmp_path, production=False)
    with pytest.raises(PrivateEngineError) as exc:
        repo.inspect_manifest("../outside")
    assert exc.value.detail_code in {"path_traversal_rejected", "path_outside_root"}


def test_40_production_default_engine_none_source_lock() -> None:
    root = Path(__file__).resolve().parents[3]
    text = (root / "apps/api/app/narrative_core/services/whole_book_engine_registry.py").read_text(
        encoding="utf-8"
    )
    assert re.search(
        r"^PRODUCTION_DEFAULT_ENGINE_ID:\s*str\s*\|\s*None\s*=\s*None\s*$",
        text,
        re.MULTILINE,
    )


def test_41_fake_signature_not_production_grade() -> None:
    verifier = DeterministicFakeSignatureVerifier()
    assert verifier.production_grade is False
    assert "NOT_FOR_PRODUCTION" in TEST_PUBLIC_KEY_FIXTURE
    assert PRIVATE_ENGINE_MANIFEST_SCHEMA
    assert PRIVATE_ENGINE_MANIFEST_VERSION
    assert EngineImplementationKind.LOCAL_PRIVATE_PACKAGE


def test_42_prompt_pack_not_engine_manifest(tmp_path: Path) -> None:
    engine_dir = write_fake_engine_package(tmp_path, fake_private_manifest())
    prompt_dir = tmp_path / "confused"
    prompt_dir.mkdir()
    (prompt_dir / "prompt_pack.manifest.json").write_text(
        (engine_dir / "engine.manifest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    repo = PromptPackManifestRepository(tmp_path, production=False)
    with pytest.raises(PrivateEngineError):
        repo.load_manifest("confused")


def test_43_production_unsigned_prompt_pack_reject() -> None:
    pack = fake_prompt_pack_manifest().manifest
    verifier = PromptPackPackageVerifier(production=True)
    with pytest.raises(PrivateEngineError) as exc:
        verifier.verify_manifest(pack)
    assert exc.value.code == PrivateEngineErrorCode.PROMPT_PACK_SIGNATURE_INVALID
