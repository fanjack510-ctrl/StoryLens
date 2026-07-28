"""Schema export helpers for whole_book_contract_v1."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from . import models as models_mod
from .constants import (
    PUBLIC_ONLY_MODEL_NAMES_V1,
    WHOLE_BOOK_CONTRACT_VERSION,
    WHOLE_BOOK_SCHEMA_NAME,
    WIRE_MODEL_NAMES_V1,
)
from .enums import ENUM_NAMES_V1


def _model_schema(name: str) -> dict[str, Any]:
    cls = getattr(models_mod, name)
    return cls.model_json_schema(mode="serialization")


def build_wire_contract_schema() -> dict[str, Any]:
    """Deterministic wire contract schema document (Public/Private identity)."""
    models: dict[str, Any] = {}
    for name in WIRE_MODEL_NAMES_V1:
        models[name] = _model_schema(name)
    enums: dict[str, list[str]] = {}
    import importlib

    enums_mod = importlib.import_module(__package__ + ".enums")
    for enum_name in ENUM_NAMES_V1:
        enum_cls = getattr(enums_mod, enum_name)
        enums[enum_name] = [m.value for m in enum_cls]
    doc = {
        "contract_version": WHOLE_BOOK_CONTRACT_VERSION,
        "schema_name": WHOLE_BOOK_SCHEMA_NAME,
        "wire_models": models,
        "enums": enums,
        "wire_model_names": list(WIRE_MODEL_NAMES_V1),
        "enum_names": list(ENUM_NAMES_V1),
    }
    return doc


def build_public_only_schema() -> dict[str, Any]:
    models: dict[str, Any] = {}
    for name in PUBLIC_ONLY_MODEL_NAMES_V1:
        models[name] = _model_schema(name)
    return {
        "contract_version": WHOLE_BOOK_CONTRACT_VERSION,
        "public_only_models": models,
        "public_only_model_names": list(PUBLIC_ONLY_MODEL_NAMES_V1),
    }


def canonical_json_bytes(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def schema_sha256(doc: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(doc)).hexdigest()
