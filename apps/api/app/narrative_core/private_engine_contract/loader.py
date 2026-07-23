"""PrivateWholeBookEngineLoader Protocol + Fake loader (Phase 2B-P).

Loader never loads real private binaries. Production rejects unsigned private.
Tests may use Fake Signed Engine. Mock remains a separate path.
Loader does NOT parse License, access ORM, read novel text, or log prompts/credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable

from app.narrative_core.enums import WholeBookAnalysisMode
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)
from app.narrative_core.private_engine_contract.manifest import (
    EngineImplementationKind,
    PrivateWholeBookEngineManifest,
    fake_mock_manifest,
    fake_private_manifest,
    validate_manifest_for_load,
)
from app.narrative_core.private_engine_contract.protocol import PrivateEngineHealth


@dataclass(frozen=True, slots=True)
class FakeSignedEngineHandle:
    """Opaque handle for tests — NOT a real binary / process."""

    engine_id: str
    engine_version: str
    fake: bool = True
    real_binary: bool = False
    loaded: bool = False

    def __post_init__(self) -> None:
        if not self.fake or self.real_binary:
            raise ValueError("FakeSignedEngineHandle must stay fake with no real binary")


@dataclass(frozen=True, slots=True)
class PackageVerificationResult:
    engine_id: str
    package_hash: str
    signature_valid: bool
    protocol_compatible: bool
    detail_code: str | None = None


LOADER_PROTOCOL_METHODS: tuple[str, ...] = (
    "discover",
    "inspect_manifest",
    "verify_package",
    "load",
    "unload",
    "health_check",
    "resolve_compatible_engine",
    "list_available_engines",
)


@runtime_checkable
class PrivateWholeBookEngineLoader(Protocol):
    def discover(self) -> Sequence[PrivateWholeBookEngineManifest]: ...

    def inspect_manifest(self, package_ref: str) -> PrivateWholeBookEngineManifest: ...

    def verify_package(self, package_ref: str) -> PackageVerificationResult: ...

    def load(self, engine_id: str) -> FakeSignedEngineHandle: ...

    def unload(self, engine_id: str) -> None: ...

    def health_check(self, engine_id: str) -> PrivateEngineHealth: ...

    def resolve_compatible_engine(
        self,
        *,
        mode: WholeBookAnalysisMode,
        app_version: str,
        production: bool,
    ) -> PrivateWholeBookEngineManifest | None: ...

    def list_available_engines(self) -> Sequence[str]: ...


@dataclass
class FakePrivateWholeBookEngineLoader:
    """In-memory Fake loader. NEVER loads real binaries."""

    app_version: str = "1.0.5"
    allow_unsigned_in_tests: bool = True
    _manifests: dict[str, PrivateWholeBookEngineManifest] = field(default_factory=dict)
    _loaded: dict[str, FakeSignedEngineHandle] = field(default_factory=dict)
    _signature_valid: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self._manifests:
            private = fake_private_manifest()
            mock = fake_mock_manifest()
            self._manifests = {
                private.engine_id: private,
                mock.engine_id: mock,
            }
            self._signature_valid = {
                private.engine_id: True,
                mock.engine_id: False,
            }

    def discover(self) -> Sequence[PrivateWholeBookEngineManifest]:
        return tuple(self._manifests.values())

    def inspect_manifest(self, package_ref: str) -> PrivateWholeBookEngineManifest:
        # package_ref is treated as engine_id for Fake fixtures only.
        manifest = self._manifests.get(package_ref)
        if manifest is None:
            raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND)
        return manifest

    def verify_package(self, package_ref: str) -> PackageVerificationResult:
        manifest = self.inspect_manifest(package_ref)
        signature_valid = self._signature_valid.get(manifest.engine_id, False)
        protocol_ok = True
        return PackageVerificationResult(
            engine_id=manifest.engine_id,
            package_hash=manifest.package_hash,
            signature_valid=signature_valid,
            protocol_compatible=protocol_ok,
        )

    def load(self, engine_id: str) -> FakeSignedEngineHandle:
        manifest = self._manifests.get(engine_id)
        if manifest is None:
            raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND)

        # Production path simulation: reject unsigned private; never load real binaries.
        production = False  # Fake loader itself is non-production; callers use validate.
        signature_valid = self._signature_valid.get(engine_id, False)
        if manifest.private and not signature_valid and not self.allow_unsigned_in_tests:
            raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID)

        validate_manifest_for_load(
            manifest,
            app_version=self.app_version,
            production=production,
            signature_valid=signature_valid or (
                self.allow_unsigned_in_tests and manifest.implementation_kind != EngineImplementationKind.MOCK
            ),
        )

        handle = FakeSignedEngineHandle(
            engine_id=manifest.engine_id,
            engine_version=manifest.engine_version,
            fake=True,
            real_binary=False,
            loaded=True,
        )
        self._loaded[engine_id] = handle
        return handle

    def unload(self, engine_id: str) -> None:
        self._loaded.pop(engine_id, None)

    def health_check(self, engine_id: str) -> PrivateEngineHealth:
        if engine_id not in self._manifests:
            raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND)
        loaded = engine_id in self._loaded
        return PrivateEngineHealth(
            engine_id=engine_id,
            healthy=True,
            status="ok" if loaded else "discovered",
            protocol_version=self._manifests[engine_id].protocol_version,
            details=("fake", "no_real_binary"),
        )

    def resolve_compatible_engine(
        self,
        *,
        mode: WholeBookAnalysisMode,
        app_version: str,
        production: bool,
    ) -> PrivateWholeBookEngineManifest | None:
        for manifest in self._manifests.values():
            if mode not in manifest.supported_modes:
                continue
            signature_valid = self._signature_valid.get(manifest.engine_id, False)
            try:
                validate_manifest_for_load(
                    manifest,
                    app_version=app_version,
                    production=production,
                    signature_valid=signature_valid,
                )
            except Exception:
                continue
            # Production must not resolve Mock.
            if production and manifest.implementation_kind == EngineImplementationKind.MOCK:
                continue
            return manifest
        return None

    def list_available_engines(self) -> Sequence[str]:
        return tuple(sorted(self._manifests))

    def reject_production_unsigned_private(
        self,
        manifest: PrivateWholeBookEngineManifest,
        *,
        signature_valid: bool,
    ) -> None:
        """Explicit production guard used by contract tests."""

        validate_manifest_for_load(
            manifest,
            app_version=self.app_version,
            production=True,
            signature_valid=signature_valid,
        )
