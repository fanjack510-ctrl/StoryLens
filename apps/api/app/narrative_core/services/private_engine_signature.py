"""Private engine / Prompt Pack package verification (Phase 2B Agent P).

Deterministic Fake signature verification for tests only.
Does NOT claim production-grade signing. No private keys are stored.
Does not modify Tauri Updater signature logic.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable

from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineError,
    PrivateEngineErrorCode,
    private_engine_error,
)
from app.narrative_core.private_engine_contract.loader import PackageVerificationResult
from app.narrative_core.private_engine_contract.manifest import (
    PRIVATE_ENGINE_PROTOCOL_ID,
    EngineImplementationKind,
    PrivateWholeBookEngineManifest,
    app_version_in_range,
    validate_manifest_for_load,
)
from app.narrative_core.private_engine_contract.prompt_pack import PromptPackManifest

# Test public key fixture ONLY — never a private key, never production config.
TEST_PUBLIC_KEY_FIXTURE = "storylens.test.public_key.v1.NOT_FOR_PRODUCTION"
FAKE_SIGNATURE_ALGORITHM = "fake-ed25519"
_SHA256_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FAKE_HASH_RE = re.compile(r"^(fake|mock)-[a-z0-9.-]+$", re.IGNORECASE)
_FAKE_ENGINE_ID_RE = re.compile(r"(fake|test)", re.IGNORECASE)


def is_fake_or_test_engine_id(engine_id: str) -> bool:
    return bool(_FAKE_ENGINE_ID_RE.search(engine_id))


def validate_package_hash_format(
    package_hash: str,
    *,
    allow_fake_prefix: bool = True,
) -> None:
    value = package_hash.strip()
    if not value:
        raise private_engine_error(
            PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID,
            detail_code="package_hash_empty",
        )
    if _SHA256_HASH_RE.match(value):
        return
    if allow_fake_prefix and _FAKE_HASH_RE.match(value):
        return
    raise private_engine_error(
        PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID,
        detail_code="package_hash_format_invalid",
    )


def compute_content_sha256_hex(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def deterministic_fake_signature(
    *,
    package_hash: str,
    subject_id: str,
    public_key: str = TEST_PUBLIC_KEY_FIXTURE,
) -> str:
    """Deterministic Fake signature material for fixtures (not production crypto)."""

    material = f"{public_key}|{subject_id}|{package_hash}".encode("utf-8")
    digest = hmac.new(b"storylens-fake-sig-fixture", material, hashlib.sha256).hexdigest()
    return f"fake-sig:{digest}"


@runtime_checkable
class SignatureVerifier(Protocol):
    def verify(
        self,
        *,
        subject_id: str,
        package_hash: str,
        signature: str | None,
        signature_algorithm: str | None,
        public_key: str | None = None,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class DeterministicFakeSignatureVerifier:
    """Test-only verifier. Must not be described as release-grade signing."""

    public_key: str = TEST_PUBLIC_KEY_FIXTURE
    fake_only: bool = True
    production_grade: bool = False

    def __post_init__(self) -> None:
        if self.production_grade or not self.fake_only:
            raise ValueError("DeterministicFakeSignatureVerifier is fake/test only")
        if "NOT_FOR_PRODUCTION" not in self.public_key:
            raise ValueError("test public key fixture must be marked NOT_FOR_PRODUCTION")

    def verify(
        self,
        *,
        subject_id: str,
        package_hash: str,
        signature: str | None,
        signature_algorithm: str | None,
        public_key: str | None = None,
    ) -> bool:
        if not signature or not signature.strip():
            return False
        algo = (signature_algorithm or "").strip().lower()
        if algo and algo not in {FAKE_SIGNATURE_ALGORITHM, "fake", "deterministic-fake"}:
            return False
        key = public_key or self.public_key
        expected = deterministic_fake_signature(
            package_hash=package_hash,
            subject_id=subject_id,
            public_key=key,
        )
        return hmac.compare_digest(signature.strip(), expected)


@dataclass
class PrivateEnginePackageVerifier:
    """Public verification surface for engine packages."""

    signature_verifier: SignatureVerifier | None = None
    app_version: str = "1.0.5"
    production: bool = False

    def __post_init__(self) -> None:
        if self.signature_verifier is None:
            self.signature_verifier = DeterministicFakeSignatureVerifier()

    def verify_manifest(
        self,
        manifest: PrivateWholeBookEngineManifest,
        *,
        signature: str | None = None,
        signature_valid: bool | None = None,
    ) -> None:
        validate_package_hash_format(
            manifest.package_hash,
            allow_fake_prefix=not self.production,
        )
        if self.production and (
            manifest.non_production
            or is_fake_or_test_engine_id(manifest.engine_id)
            or manifest.implementation_kind == EngineImplementationKind.MOCK
            or not manifest.private
        ):
            raise private_engine_error(
                PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
                detail_code="production_rejects_fake_or_mock",
            )
        if signature_valid is None:
            signature_valid = self.verify_signature(
                subject_id=manifest.engine_id,
                package_hash=manifest.package_hash,
                signature=signature,
                signature_algorithm=manifest.signature_algorithm,
                signed=manifest.signed,
            )
        validate_manifest_for_load(
            manifest,
            app_version=self.app_version,
            production=self.production,
            signature_valid=bool(signature_valid),
        )

    def verify_package_hash(
        self,
        *,
        expected_hash: str,
        actual_content: bytes | None = None,
        actual_hash: str | None = None,
        allow_fake_prefix: bool | None = None,
    ) -> None:
        allow_fake = (not self.production) if allow_fake_prefix is None else allow_fake_prefix
        validate_package_hash_format(expected_hash, allow_fake_prefix=allow_fake)
        if actual_hash is None:
            if actual_content is None:
                raise private_engine_error(
                    PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID,
                    detail_code="package_hash_missing_actual",
                )
            if expected_hash.startswith(("fake-", "mock-")) and allow_fake:
                # Fake fixtures may declare opaque hashes without byte payloads.
                return
            actual_hash = compute_content_sha256_hex(actual_content)
        validate_package_hash_format(actual_hash, allow_fake_prefix=allow_fake)
        if actual_hash != expected_hash:
            raise private_engine_error(
                PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID,
                detail_code="package_hash_mismatch",
            )

    def verify_signature(
        self,
        *,
        subject_id: str,
        package_hash: str,
        signature: str | None,
        signature_algorithm: str | None,
        signed: bool,
    ) -> bool:
        if self.production and signed is False:
            raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID)
        if not signed:
            return False
        assert self.signature_verifier is not None
        ok = self.signature_verifier.verify(
            subject_id=subject_id,
            package_hash=package_hash,
            signature=signature,
            signature_algorithm=signature_algorithm,
        )
        if not ok:
            raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID)
        return True

    def verify_compatibility(
        self,
        manifest: PrivateWholeBookEngineManifest,
        *,
        app_version: str | None = None,
        prompt_pack: PromptPackManifest | None = None,
    ) -> None:
        version = app_version or self.app_version
        if manifest.protocol_version != PRIVATE_ENGINE_PROTOCOL_ID:
            raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE)
        if not app_version_in_range(
            version,
            minimum_app_version=manifest.minimum_app_version,
            maximum_app_version=manifest.maximum_app_version,
        ):
            raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_APP_VERSION_INCOMPATIBLE)
        if prompt_pack is not None:
            if manifest.engine_version not in prompt_pack.supported_engine_versions:
                raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE)
            if self.production and (prompt_pack.non_production or not prompt_pack.signed):
                raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_SIGNATURE_INVALID)

    def verify_package(
        self,
        manifest: PrivateWholeBookEngineManifest,
        *,
        signature: str | None = None,
        package_bytes: bytes | None = None,
        prompt_pack: PromptPackManifest | None = None,
    ) -> PackageVerificationResult:
        try:
            if package_bytes is not None or not manifest.package_hash.startswith(("fake-", "mock-")):
                self.verify_package_hash(
                    expected_hash=manifest.package_hash,
                    actual_content=package_bytes if package_bytes is not None else b"",
                )
            else:
                validate_package_hash_format(
                    manifest.package_hash,
                    allow_fake_prefix=not self.production,
                )
            signature_valid = False
            if manifest.signed:
                signature_valid = self.verify_signature(
                    subject_id=manifest.engine_id,
                    package_hash=manifest.package_hash,
                    signature=signature,
                    signature_algorithm=manifest.signature_algorithm,
                    signed=True,
                )
            self.verify_compatibility(manifest, prompt_pack=prompt_pack)
            self.verify_manifest(manifest, signature=signature, signature_valid=signature_valid)
            return PackageVerificationResult(
                engine_id=manifest.engine_id,
                package_hash=manifest.package_hash,
                signature_valid=signature_valid if manifest.signed else False,
                protocol_compatible=True,
            )
        except Exception as exc:
            # Preserve stable PrivateEngineError codes; do not mock-fallback.
            raise exc


@dataclass
class PromptPackPackageVerifier:
    """Public verification surface for Prompt Pack packages (manifest/hash/signature only)."""

    signature_verifier: SignatureVerifier | None = None
    production: bool = False

    def __post_init__(self) -> None:
        if self.signature_verifier is None:
            self.signature_verifier = DeterministicFakeSignatureVerifier()

    def verify_manifest(self, manifest: PromptPackManifest, *, signature: str | None = None) -> None:
        if self.production and (manifest.non_production or not manifest.signed):
            raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_SIGNATURE_INVALID)
        try:
            validate_package_hash_format(
                manifest.package_hash,
                allow_fake_prefix=not self.production,
            )
        except PrivateEngineError as exc:
            if exc.code == PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID:
                raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_SIGNATURE_INVALID) from exc
            raise
        if manifest.signed:
            self.verify_signature(
                subject_id=manifest.prompt_pack_id,
                package_hash=manifest.package_hash,
                signature=signature,
                signature_algorithm=FAKE_SIGNATURE_ALGORITHM if manifest.signed else None,
                signed=True,
            )

    def verify_package_hash(
        self,
        *,
        expected_hash: str,
        actual_hash: str | None = None,
        actual_content: bytes | None = None,
    ) -> None:
        validate_package_hash_format(expected_hash, allow_fake_prefix=not self.production)
        if actual_hash is None and actual_content is not None:
            if expected_hash.startswith(("fake-", "mock-")) and not self.production:
                return
            actual_hash = compute_content_sha256_hex(actual_content)
        if actual_hash is not None and actual_hash != expected_hash:
            raise private_engine_error(
                PrivateEngineErrorCode.PROMPT_PACK_SIGNATURE_INVALID,
                detail_code="prompt_pack_hash_mismatch",
            )

    def verify_signature(
        self,
        *,
        subject_id: str,
        package_hash: str,
        signature: str | None,
        signature_algorithm: str | None,
        signed: bool,
    ) -> bool:
        if self.production and not signed:
            raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_SIGNATURE_INVALID)
        if not signed:
            return False
        assert self.signature_verifier is not None
        ok = self.signature_verifier.verify(
            subject_id=subject_id,
            package_hash=package_hash,
            signature=signature,
            signature_algorithm=signature_algorithm,
        )
        if not ok:
            raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_SIGNATURE_INVALID)
        return True

    def verify_compatibility(
        self,
        pack: PromptPackManifest,
        *,
        engine_version: str,
        module_keys: tuple[str, ...] | None = None,
        languages: tuple[str, ...] | None = None,
    ) -> None:
        if engine_version not in pack.supported_engine_versions:
            raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE)
        if module_keys:
            supported = {m.value if hasattr(m, "value") else str(m) for m in pack.supported_modules}
            for key in module_keys:
                token = key.value if hasattr(key, "value") else str(key)
                if token not in supported:
                    raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE)
        if languages:
            allowed = set(pack.supported_languages)
            for lang in languages:
                if lang not in allowed:
                    raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE)


def assert_no_private_key_material(payload: Mapping[str, object]) -> None:
    banned = ("private_key", "privateKey", "secret_key", "signing_key")
    for key in payload:
        lowered = str(key).lower()
        if any(token in lowered for token in ("private_key", "secret_key", "signing_key")):
            raise ValueError(f"private key material must not be persisted: {key}")
        _ = banned
