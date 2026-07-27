"""Private Engine Manifest Repository + Default Loader (Phase 2B Agent P).

Reads Manifest only — never loads real private binaries, never scans novel body,
never parses License / ORM / API keys / Prompt bodies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)
from app.narrative_core.private_engine_contract.loader import (
    FakeSignedEngineHandle,
    PackageVerificationResult,
)
from app.narrative_core.private_engine_contract.manifest import (
    PRIVATE_ENGINE_MANIFEST_SCHEMA,
    PRIVATE_ENGINE_MANIFEST_VERSION,
    PRIVATE_ENGINE_PROTOCOL_ID,
    EngineImplementationKind,
    PrivateWholeBookEngineManifest,
    app_version_in_range,
    validate_manifest_for_load,
)
from app.narrative_core.private_engine_contract.prompt_pack import (
    PromptPackManifest,
    fake_prompt_pack_manifest,
)
from app.narrative_core.private_engine_contract.protocol import PrivateEngineHealth
from app.narrative_core.services.private_engine_signature import (
    DeterministicFakeSignatureVerifier,
    PrivateEnginePackageVerifier,
    PromptPackPackageVerifier,
    deterministic_fake_signature,
    evaluate_dev_lab_signature,
    is_fake_or_test_engine_id,
    validate_package_hash_format,
)

_PATH_TRAVERSAL_RE = re.compile(r"(^|[\\/])\.\.([\\/]|$)")
_MANIFEST_NAME = "engine.manifest.json"
_PROMPT_MANIFEST_NAME = "prompt_pack.manifest.json"
_SIGNATURE_NAME = "engine.signature.txt"
_ALLOWED_LOAD_KINDS = frozenset(
    {
        EngineImplementationKind.LOCAL_PRIVATE_PACKAGE,
        EngineImplementationKind.MOCK,  # discoverable; load still gated
    }
)


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _safe_resolve_under_root(root: Path, relative: str | Path) -> Path:
    if _PATH_TRAVERSAL_RE.search(str(relative).replace("\\", "/")):
        raise private_engine_error(
            PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
            detail_code="path_traversal_rejected",
        )
    root_resolved = root.resolve()
    candidate = (root_resolved / relative).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise private_engine_error(
            PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
            detail_code="path_outside_root",
        ) from exc
    return candidate


def manifest_from_mapping(data: Mapping[str, Any]) -> PrivateWholeBookEngineManifest:
    schema = str(data.get("manifest_schema") or "")
    version = str(data.get("manifest_version") or "")
    if schema != PRIVATE_ENGINE_MANIFEST_SCHEMA:
        raise private_engine_error(
            PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE,
            detail_code="manifest_schema_invalid",
        )
    if version != PRIVATE_ENGINE_MANIFEST_VERSION:
        raise private_engine_error(
            PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE,
            detail_code="manifest_version_invalid",
        )
    kind_raw = str(data.get("implementation_kind") or "")
    try:
        kind = EngineImplementationKind(kind_raw)
    except ValueError as exc:
        raise private_engine_error(
            PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
            detail_code="unknown_implementation_kind",
        ) from exc

    modes = tuple(WholeBookAnalysisMode(m) for m in data.get("supported_modes") or ())
    modules = tuple(WholeBookModuleKey(m) for m in data.get("supported_modules") or ())
    return PrivateWholeBookEngineManifest(
        manifest_schema=schema,
        manifest_version=version,
        engine_id=str(data["engine_id"]),
        engine_version=str(data["engine_version"]),
        protocol_version=str(data.get("protocol_version") or ""),
        implementation_kind=kind,
        private=bool(data.get("private")),
        signed=bool(data.get("signed")),
        signature_algorithm=data.get("signature_algorithm"),
        package_hash=str(data.get("package_hash") or ""),
        supported_modes=modes,
        supported_modules=modules,
        supported_languages=tuple(str(x) for x in data.get("supported_languages") or ()),
        supported_provider_kinds=tuple(str(x) for x in data.get("supported_provider_kinds") or ()),
        minimum_app_version=str(data.get("minimum_app_version") or "0.0.0"),
        maximum_app_version=data.get("maximum_app_version"),
        checkpoint_versions=tuple(str(x) for x in data.get("checkpoint_versions") or ()),
        result_schema_versions=tuple(str(x) for x in data.get("result_schema_versions") or ()),
        evidence_schema_versions=tuple(str(x) for x in data.get("evidence_schema_versions") or ()),
        health_capabilities=tuple(str(x) for x in data.get("health_capabilities") or ()),
        build_id=str(data.get("build_id") or ""),
        created_at=_parse_datetime(data.get("created_at") or datetime(2026, 7, 23)),
        non_production=bool(data.get("non_production", False)),
    )


def manifest_to_mapping(manifest: PrivateWholeBookEngineManifest) -> dict[str, Any]:
    return {
        "manifest_schema": manifest.manifest_schema,
        "manifest_version": manifest.manifest_version,
        "engine_id": manifest.engine_id,
        "engine_version": manifest.engine_version,
        "protocol_version": manifest.protocol_version,
        "implementation_kind": manifest.implementation_kind.value,
        "private": manifest.private,
        "signed": manifest.signed,
        "signature_algorithm": manifest.signature_algorithm,
        "package_hash": manifest.package_hash,
        "supported_modes": [m.value for m in manifest.supported_modes],
        "supported_modules": [m.value for m in manifest.supported_modules],
        "supported_languages": list(manifest.supported_languages),
        "supported_provider_kinds": list(manifest.supported_provider_kinds),
        "minimum_app_version": manifest.minimum_app_version,
        "maximum_app_version": manifest.maximum_app_version,
        "checkpoint_versions": list(manifest.checkpoint_versions),
        "result_schema_versions": list(manifest.result_schema_versions),
        "evidence_schema_versions": list(manifest.evidence_schema_versions),
        "health_capabilities": list(manifest.health_capabilities),
        "build_id": manifest.build_id,
        "created_at": manifest.created_at.isoformat(),
        "non_production": manifest.non_production,
    }


def prompt_pack_from_mapping(data: Mapping[str, Any]) -> PromptPackManifest:
    # Reject treating Engine Manifest as Prompt Pack.
    if data.get("manifest_schema") == PRIVATE_ENGINE_MANIFEST_SCHEMA or "engine_id" in data:
        raise private_engine_error(
            PrivateEngineErrorCode.PROMPT_PACK_NOT_FOUND,
            detail_code="engine_manifest_not_prompt_pack",
        )
    modules = tuple(WholeBookModuleKey(m) for m in data.get("supported_modules") or ())
    return PromptPackManifest(
        prompt_pack_id=str(data["prompt_pack_id"]),
        prompt_pack_version=str(data["prompt_pack_version"]),
        private=bool(data.get("private")),
        signed=bool(data.get("signed")),
        package_hash=str(data.get("package_hash") or ""),
        supported_engine_versions=tuple(str(x) for x in data.get("supported_engine_versions") or ()),
        supported_modules=modules,
        supported_languages=tuple(str(x) for x in data.get("supported_languages") or ()),
        output_schema_versions=tuple(str(x) for x in data.get("output_schema_versions") or ()),
        instruction_ref=str(data.get("instruction_ref") or ""),
        template_refs={str(k): str(v) for k, v in dict(data.get("template_refs") or {}).items()},
        example_set_refs=tuple(str(x) for x in data.get("example_set_refs") or ()),
        evaluation_policy_ref=data.get("evaluation_policy_ref"),
        created_at=_parse_datetime(data.get("created_at") or datetime(2026, 7, 23)),
        prompt_hash=str(data.get("prompt_hash") or ""),
        non_production=bool(data.get("non_production", False)),
    )


def prompt_pack_to_mapping(manifest: PromptPackManifest) -> dict[str, Any]:
    return {
        "prompt_pack_id": manifest.prompt_pack_id,
        "prompt_pack_version": manifest.prompt_pack_version,
        "private": manifest.private,
        "signed": manifest.signed,
        "package_hash": manifest.package_hash,
        "supported_engine_versions": list(manifest.supported_engine_versions),
        "supported_modules": [m.value for m in manifest.supported_modules],
        "supported_languages": list(manifest.supported_languages),
        "output_schema_versions": list(manifest.output_schema_versions),
        "instruction_ref": manifest.instruction_ref,
        "template_refs": dict(manifest.template_refs),
        "example_set_refs": list(manifest.example_set_refs),
        "evaluation_policy_ref": manifest.evaluation_policy_ref,
        "created_at": manifest.created_at.isoformat(),
        "prompt_hash": manifest.prompt_hash,
        "non_production": manifest.non_production,
    }


@dataclass(frozen=True, slots=True)
class ManifestInspection:
    manifest: PrivateWholeBookEngineManifest
    package_ref: str
    signature: str | None
    relative_path: str


@dataclass
class PrivateEngineManifestRepository:
    """Filesystem Manifest repository. Never loads binaries or novel text."""

    root_dir: Path
    production: bool = False
    _index: dict[tuple[str, str], ManifestInspection] = field(default_factory=dict, init=False)
    _by_engine: dict[str, list[ManifestInspection]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.root_dir = Path(self.root_dir)
        if not self.root_dir.exists():
            raise private_engine_error(
                PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
                detail_code="manifest_root_missing",
            )

    def discover_manifests(self, *, refresh: bool = True) -> Sequence[PrivateWholeBookEngineManifest]:
        if refresh or not self._index:
            self._rebuild_index()
        return tuple(item.manifest for item in self._index.values())

    def list_manifests(self) -> Sequence[PrivateWholeBookEngineManifest]:
        return self.discover_manifests(refresh=False)

    def load_manifest(self, package_ref: str) -> PrivateWholeBookEngineManifest:
        return self.inspect_manifest(package_ref).manifest

    def inspect_manifest(self, package_ref: str) -> ManifestInspection:
        if not self._index:
            self._rebuild_index()
        # package_ref may be engine_id or relative package directory.
        for item in self._index.values():
            if item.package_ref == package_ref or item.manifest.engine_id == package_ref:
                return item
            if item.relative_path == package_ref or item.relative_path.rstrip("/\\") == package_ref:
                return item
        path = _safe_resolve_under_root(self.root_dir, package_ref)
        if path.is_dir():
            path = path / _MANIFEST_NAME
        if not path.exists():
            raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND)
        return self._read_manifest_file(path)

    def find_by_engine_id(self, engine_id: str) -> Sequence[PrivateWholeBookEngineManifest]:
        if not self._index:
            self._rebuild_index()
        items = self._by_engine.get(engine_id, [])
        return tuple(item.manifest for item in items)

    def find_compatible(
        self,
        *,
        mode: WholeBookAnalysisMode,
        app_version: str,
        production: bool | None = None,
        require_signed: bool | None = None,
    ) -> Sequence[PrivateWholeBookEngineManifest]:
        prod = self.production if production is None else production
        if not self._index:
            self._rebuild_index()
        matched: list[PrivateWholeBookEngineManifest] = []
        for item in self._index.values():
            manifest = item.manifest
            if mode not in manifest.supported_modes:
                continue
            if require_signed is True and not manifest.signed:
                continue
            try:
                validate_package_hash_format(
                    manifest.package_hash,
                    allow_fake_prefix=not prod,
                )
                signature_valid = bool(item.signature) if manifest.signed else False
                if manifest.signed and item.signature:
                    verifier = DeterministicFakeSignatureVerifier()
                    signature_valid = verifier.verify(
                        subject_id=manifest.engine_id,
                        package_hash=manifest.package_hash,
                        signature=item.signature,
                        signature_algorithm=manifest.signature_algorithm,
                    )
                validate_manifest_for_load(
                    manifest,
                    app_version=app_version,
                    production=prod,
                    signature_valid=signature_valid,
                )
            except Exception:
                continue
            matched.append(manifest)
        return tuple(self._sort_compatible(matched))

    def _rebuild_index(self) -> None:
        self._index.clear()
        self._by_engine.clear()
        root = self.root_dir.resolve()
        for path in sorted(root.rglob(_MANIFEST_NAME)):
            try:
                resolved = path.resolve()
                resolved.relative_to(root)
            except ValueError:
                continue
            try:
                inspection = self._read_manifest_file(resolved)
            except Exception:
                # Skip unreadable entries; load()/inspect still raise for explicit refs.
                continue
            key = (inspection.manifest.engine_id, inspection.manifest.engine_version)
            if key in self._index:
                raise private_engine_error(
                    PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
                    detail_code="duplicate_engine_id_version",
                )
            if self.production and (
                inspection.manifest.non_production
                or is_fake_or_test_engine_id(inspection.manifest.engine_id)
                or inspection.manifest.implementation_kind == EngineImplementationKind.MOCK
            ):
                continue
            self._index[key] = inspection
            self._by_engine.setdefault(inspection.manifest.engine_id, []).append(inspection)

    def _read_manifest_file(self, path: Path) -> ManifestInspection:
        root = self.root_dir.resolve()
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise private_engine_error(
                PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
                detail_code="path_outside_root",
            ) from exc
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise private_engine_error(
                PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE,
                detail_code="manifest_schema_invalid",
            )
        # Package paths must not escape root via relative package_path fields.
        for key in ("package_path", "binary_path", "package_ref"):
            if key in raw:
                _safe_resolve_under_root(root, str(raw[key]))
        manifest = manifest_from_mapping(raw)
        validate_package_hash_format(
            manifest.package_hash,
            allow_fake_prefix=not self.production,
        )
        sig_path = path.parent / _SIGNATURE_NAME
        signature = sig_path.read_text(encoding="utf-8").strip() if sig_path.exists() else None
        rel = str(path.parent.relative_to(root)).replace("\\", "/")
        return ManifestInspection(
            manifest=manifest,
            package_ref=manifest.engine_id,
            signature=signature,
            relative_path=rel,
        )

    @staticmethod
    def _sort_compatible(
        manifests: Sequence[PrivateWholeBookEngineManifest],
    ) -> list[PrivateWholeBookEngineManifest]:
        # Explicit strategy: signed first, then higher version, then engine_id.
        def key(m: PrivateWholeBookEngineManifest) -> tuple[int, tuple[int, ...], str]:
            parts: list[int] = []
            for piece in m.engine_version.split("."):
                digits = "".join(ch for ch in piece if ch.isdigit())
                parts.append(int(digits) if digits else 0)
            return (1 if m.signed else 0, tuple(parts), m.engine_id)

        return sorted(manifests, key=key, reverse=True)


@dataclass
class PromptPackManifestRepository:
    """Prompt Pack Manifest only — no formal prompt bodies in business resources."""

    root_dir: Path
    production: bool = False
    _index: dict[str, PromptPackManifest] = field(default_factory=dict, init=False)
    _signatures: dict[str, str | None] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.root_dir = Path(self.root_dir)

    def discover(self, *, refresh: bool = True) -> Sequence[PromptPackManifest]:
        if refresh or not self._index:
            self._rebuild()
        return tuple(self._index.values())

    def load_manifest(self, package_ref: str) -> PromptPackManifest:
        if not self._index:
            self._rebuild()
        if package_ref in self._index:
            return self._index[package_ref]
        path = _safe_resolve_under_root(self.root_dir, package_ref)
        if path.is_dir():
            path = path / _PROMPT_MANIFEST_NAME
        if not path.exists():
            raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_NOT_FOUND)
        manifest = self._read(path)
        return manifest

    def find_by_id(self, prompt_pack_id: str) -> PromptPackManifest | None:
        if not self._index:
            self._rebuild()
        return self._index.get(prompt_pack_id)

    def _rebuild(self) -> None:
        self._index.clear()
        self._signatures.clear()
        if not self.root_dir.exists():
            return
        root = self.root_dir.resolve()
        for path in sorted(root.rglob(_PROMPT_MANIFEST_NAME)):
            try:
                path.resolve().relative_to(root)
            except ValueError:
                continue
            try:
                manifest = self._read(path)
            except Exception:
                continue
            if self.production and (manifest.non_production or not manifest.signed):
                continue
            self._index[manifest.prompt_pack_id] = manifest

    def _read(self, path: Path) -> PromptPackManifest:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_NOT_FOUND)
        # Prompt body fields must not appear in Manifest resources.
        for banned in ("prompt_body", "system_prompt", "user_prompt", "messages", "instruction_text"):
            if banned in raw:
                raise private_engine_error(
                    PrivateEngineErrorCode.PROMPT_PACK_NOT_FOUND,
                    detail_code="prompt_body_forbidden",
                )
        manifest = prompt_pack_from_mapping(raw)
        validate_package_hash_format(
            manifest.package_hash,
            allow_fake_prefix=not self.production,
        )
        sig_path = path.parent / "prompt_pack.signature.txt"
        self._signatures[manifest.prompt_pack_id] = (
            sig_path.read_text(encoding="utf-8").strip() if sig_path.exists() else None
        )
        return manifest


@dataclass
class PromptPackCompatibilityValidator:
    verifier: PromptPackPackageVerifier = field(default_factory=PromptPackPackageVerifier)

    def assert_compatible(
        self,
        pack: PromptPackManifest,
        *,
        engine_version: str,
        module_keys: Sequence[WholeBookModuleKey] | Sequence[str] | None = None,
        languages: Sequence[str] | None = None,
        for_resume: bool = False,
        checkpoint_prompt_pack_id: str | None = None,
        checkpoint_prompt_pack_version: str | None = None,
    ) -> None:
        self.verifier.verify_compatibility(
            pack,
            engine_version=engine_version,
            module_keys=tuple(str(getattr(k, "value", k)) for k in module_keys or ()),
            languages=tuple(languages or ()),
        )
        if for_resume:
            if checkpoint_prompt_pack_id is None or checkpoint_prompt_pack_version is None:
                raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE)
            if (
                pack.prompt_pack_id != checkpoint_prompt_pack_id
                or pack.prompt_pack_version != checkpoint_prompt_pack_version
            ):
                raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE)


def try_import_private_engine_entry() -> Any | None:
    """Dev/Lab hook: import private package entry if installed.

    Public App never vendors private sources; discovery stays Manifest-driven.
    """
    try:
        from storylens_private_engine.runtime.entry import (  # type: ignore[import-not-found]
            create_private_engine_entry,
        )
    except Exception:
        return None
    try:
        return create_private_engine_entry()
    except Exception:
        return None


@dataclass
class DefaultPrivateWholeBookEngineLoader:
    """Default loader: Fake Signed packages; Lab/dev may load private package entry."""

    repository: PrivateEngineManifestRepository
    verifier: PrivateEnginePackageVerifier | None = None
    app_version: str = "1.0.5"
    production: bool = False
    lab_dev_private_package_load: bool = False
    _loaded: dict[str, FakeSignedEngineHandle] = field(default_factory=dict, init=False)
    _engines: dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.verifier is None:
            self.verifier = PrivateEnginePackageVerifier(
                app_version=self.app_version,
                production=self.production,
            )
        if self.production and self.lab_dev_private_package_load:
            raise ValueError("production loader must not enable lab private package load")

    def discover(self) -> Sequence[PrivateWholeBookEngineManifest]:
        return self.repository.discover_manifests()

    def inspect_manifest(self, package_ref: str) -> PrivateWholeBookEngineManifest:
        return self.repository.inspect_manifest(package_ref).manifest

    def verify_package(self, package_ref: str) -> PackageVerificationResult:
        inspection = self.repository.inspect_manifest(package_ref)
        assert self.verifier is not None
        return self.verifier.verify_package(
            inspection.manifest,
            signature=inspection.signature,
        )

    def load(self, engine_id: str) -> FakeSignedEngineHandle:
        inspection = self.repository.inspect_manifest(engine_id)
        manifest = inspection.manifest
        if manifest.implementation_kind not in _ALLOWED_LOAD_KINDS:
            raise private_engine_error(
                PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
                detail_code="unknown_implementation_kind",
            )
        if self.production:
            # Production: never Fake/Mock; never unsigned; no silent mock fallback.
            raise private_engine_error(
                PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
                detail_code="production_no_default_private_engine",
            )
        if not is_fake_or_test_engine_id(manifest.engine_id) and not manifest.non_production:
            raise private_engine_error(
                PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
                detail_code="real_binary_load_forbidden",
            )
        if manifest.implementation_kind == EngineImplementationKind.MOCK:
            # Mock remains a separate implementation; this loader does not load Mock as private.
            raise private_engine_error(
                PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
                detail_code="no_mock_fallback",
            )
        assert self.verifier is not None
        if (
            not manifest.signed
            and self.lab_dev_private_package_load
            and evaluate_dev_lab_signature(
                signed=manifest.signed,
                non_production=manifest.non_production,
                lab_authorized=True,
                production=False,
            )
        ):
            # Lab/dev unsigned non_production package: skip fake signature verify.
            validate_package_hash_format(
                manifest.package_hash,
                allow_fake_prefix=True,
            )
        else:
            self.verifier.verify_package(manifest, signature=inspection.signature)

        # Lab/dev: prefer installed private package entry when authorized.
        if self.lab_dev_private_package_load:
            private_entry = try_import_private_engine_entry()
            if private_entry is not None:
                self._engines[engine_id] = private_entry
                # Opaque handle stays FakeSignedEngineHandle-compatible (no real binary).
                handle = FakeSignedEngineHandle(
                    engine_id=manifest.engine_id,
                    engine_version=manifest.engine_version,
                    fake=True,
                    real_binary=False,
                    loaded=True,
                )
                self._loaded[engine_id] = handle
                return handle

        # Lazily construct Fake engine instance (no real DLL/EXE/wheel).
        from app.narrative_core.services.fake_private_whole_book_engine import (
            FakePrivateWholeBookEngine,
        )

        engine = FakePrivateWholeBookEngine(manifest=manifest)
        self._engines[engine_id] = engine
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
        self._engines.pop(engine_id, None)

    def health_check(self, engine_id: str) -> PrivateEngineHealth:
        manifests = self.repository.find_by_engine_id(engine_id)
        if not manifests and engine_id not in self._loaded:
            # Try inspect by id/ref.
            try:
                manifest = self.inspect_manifest(engine_id)
            except Exception as exc:
                raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND) from exc
        else:
            manifest = manifests[0] if manifests else self.inspect_manifest(engine_id)
        loaded = engine_id in self._loaded
        engine = self._engines.get(engine_id)
        details = ["fake", "no_real_binary", "no_novel_analysis"]
        if engine is not None:
            health = engine.health_check()
            return health
        return PrivateEngineHealth(
            engine_id=engine_id,
            healthy=True,
            status="ok" if loaded else "discovered",
            protocol_version=manifest.protocol_version,
            details=tuple(details),
        )

    def resolve_compatible_engine(
        self,
        *,
        mode: WholeBookAnalysisMode,
        app_version: str,
        production: bool,
    ) -> PrivateWholeBookEngineManifest | None:
        if production:
            # No production default private engine; never degrade to Mock.
            return None
        matched = self.repository.find_compatible(
            mode=mode,
            app_version=app_version,
            production=False,
            require_signed=True,
        )
        # Exclude Mock from private loader resolution.
        private_only = [
            m
            for m in matched
            if m.implementation_kind != EngineImplementationKind.MOCK
            and is_fake_or_test_engine_id(m.engine_id)
        ]
        if not private_only:
            return None
        return private_only[0]

    def list_available_engines(self) -> Sequence[str]:
        return tuple(sorted({m.engine_id for m in self.discover()}))

    def get_loaded_engine(self, engine_id: str) -> Any | None:
        return self._engines.get(engine_id)


def write_fake_engine_package(
    root: Path,
    manifest: PrivateWholeBookEngineManifest,
    *,
    package_dirname: str | None = None,
    include_signature: bool = True,
) -> Path:
    """Test helper: write Manifest (+ optional Fake signature) under a temp root."""

    dirname = package_dirname or manifest.engine_id.replace(".", "_")
    package_dir = root / dirname
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / _MANIFEST_NAME).write_text(
        json.dumps(manifest_to_mapping(manifest), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if include_signature and manifest.signed:
        sig = deterministic_fake_signature(
            package_hash=manifest.package_hash,
            subject_id=manifest.engine_id,
        )
        (package_dir / _SIGNATURE_NAME).write_text(sig, encoding="utf-8")
    return package_dir


def write_fake_prompt_pack(
    root: Path,
    manifest: PromptPackManifest | None = None,
    *,
    include_signature: bool = False,
) -> Path:
    pack = manifest or fake_prompt_pack_manifest().manifest
    dirname = pack.prompt_pack_id.replace(".", "_")
    package_dir = root / dirname
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / _PROMPT_MANIFEST_NAME).write_text(
        json.dumps(prompt_pack_to_mapping(pack), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if include_signature and pack.signed:
        sig = deterministic_fake_signature(
            package_hash=pack.package_hash,
            subject_id=pack.prompt_pack_id,
        )
        (package_dir / "prompt_pack.signature.txt").write_text(sig, encoding="utf-8")
    return package_dir


# Compatibility aliases used by docs / tests.
PrivateWholeBookEngineLoaderImpl = DefaultPrivateWholeBookEngineLoader
