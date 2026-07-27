"""CWD-independent Reader Journey V2 config loading and validation (CHG-20260727-013).

Never treat missing/invalid role targets as an empty table that silently
widens pacing bands to [0, 100].
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.schemas.reader_journey_v2 import SCENE_ROLE_TARGETS_VERSION

logger = logging.getLogger(__name__)

SCENE_ROLE_TARGETS_FILENAME = "scene_role_targets.json"
FORMULAS_V2_FILENAME = "reader_journey_formulas_v2.json"

REQUIRED_SCENE_ROLES = frozenset(
    {
        "setup",
        "escalation",
        "investigation",
        "reveal",
        "climax",
        "aftermath",
        "transition",
        "open_end",
        "closed_end",
    }
)

LoadStatus = Literal["loaded", "missing", "invalid"]
ConfigSource = Literal["env", "user", "bundled", "explicit", "unknown"]

REASON_TARGETS_MISSING = "scene_role_targets_unavailable"
REASON_TARGETS_INVALID = "scene_role_targets_invalid"
REASON_ROLE_NOT_FOUND = "scene_role_not_found"
REASON_BAND_MISSING = "scene_role_band_missing"
REASON_FORMULAS_MISSING = "formulas_v2_unavailable"
REASON_FORMULAS_INVALID = "formulas_v2_invalid"


@dataclass(frozen=True)
class ConfigProvenance:
    config_name: str
    status: LoadStatus
    source: ConfigSource
    version: str | None
    content_hash: str | None
    resolved_path: str | None
    error: str | None = None
    quality_flags: tuple[str, ...] = ()

    def to_public_dict(self) -> dict[str, Any]:
        """UI-safe provenance (no absolute filesystem paths)."""
        return {
            "config_name": self.config_name,
            "status": self.status,
            "source": self.source,
            "version": self.version,
            "content_hash": self.content_hash,
            "error": self.error,
            "quality_flags": list(self.quality_flags),
        }

    def to_log_dict(self) -> dict[str, Any]:
        payload = self.to_public_dict()
        payload["resolved_path"] = self.resolved_path
        return payload


@dataclass
class RoleTargetsBundle:
    provenance: ConfigProvenance
    config: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.provenance.status == "loaded" and isinstance(self.config, dict)

    @property
    def roles(self) -> dict[str, Any]:
        if not self.config:
            return {}
        raw = self.config.get("roles")
        return raw if isinstance(raw, dict) else {}


@dataclass
class FormulaV2Bundle:
    provenance: ConfigProvenance
    config: dict[str, Any]
    used_embedded_defaults: bool = False


@dataclass
class FitComputation:
    value: float | None
    status: Literal["ok", "unavailable"]
    reason_code: str | None = None
    quality_flags: tuple[str, ...] = ()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_reader_journey_v2_config_path(
    filename: str,
    *,
    explicit: Path | None = None,
) -> tuple[Path | None, ConfigSource, str | None]:
    """Resolve a V2 config file without depending on process CWD.

    Priority (aligned with scene_evidence_validation):
    1. explicit path when provided and present
    2. STORYLENS_CONFIG_DIR / filename
    3. user_data_layout()['config'] / filename
    4. resource_root() / config / filename
    """
    from app.core.paths import resource_root, user_data_layout

    if explicit is not None:
        try:
            if explicit.is_file():
                return explicit.resolve(), "explicit", None
        except OSError as exc:
            return None, "explicit", f"explicit path unreadable: {exc}"

    config_dir = (os.environ.get("STORYLENS_CONFIG_DIR") or "").strip()
    if config_dir:
        candidate = Path(config_dir).expanduser() / filename
        try:
            if candidate.is_file():
                return candidate.resolve(), "env", None
        except OSError as exc:
            return None, "env", f"STORYLENS_CONFIG_DIR unreadable: {exc}"

    try:
        user_cfg = user_data_layout()["config"] / filename
        if user_cfg.is_file():
            return user_cfg.resolve(), "user", None
    except Exception as exc:  # noqa: BLE001 — layout may be unavailable in unit isolation
        logger.debug("user_data_layout unavailable while resolving %s: %s", filename, exc)

    bundled = resource_root() / "config" / filename
    try:
        if bundled.is_file():
            return bundled.resolve(), "bundled", None
    except OSError as exc:
        return None, "bundled", f"bundled path unreadable: {exc}"

    return None, "unknown", f"missing {filename}"


def _validate_band(band: Any, *, field_name: str) -> tuple[float, float]:
    if not isinstance(band, (list, tuple)) or len(band) != 2:
        raise ValueError(f"{field_name} must be a length-2 list")
    low_raw, high_raw = band[0], band[1]
    if not isinstance(low_raw, (int, float)) or isinstance(low_raw, bool):
        raise ValueError(f"{field_name}[0] must be numeric")
    if not isinstance(high_raw, (int, float)) or isinstance(high_raw, bool):
        raise ValueError(f"{field_name}[1] must be numeric")
    low, high = float(low_raw), float(high_raw)
    if low > high:
        raise ValueError(f"{field_name} min must be <= max")
    if low < 0 or high > 100:
        raise ValueError(f"{field_name} must be within 0..100")
    return low, high


def validate_scene_role_targets(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("root must be an object")
    roles = config.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise ValueError("roles must be a non-empty object")
    missing = REQUIRED_SCENE_ROLES - set(roles)
    if missing:
        raise ValueError(f"roles missing required keys: {sorted(missing)}")
    for role_name, role_cfg in roles.items():
        if not isinstance(role_cfg, dict):
            raise ValueError(f"role {role_name} must be an object")
        for band_key in ("pacing_speed", "hook", "payoff"):
            if band_key not in role_cfg:
                raise ValueError(f"role {role_name} missing {band_key}")
            _validate_band(role_cfg[band_key], field_name=f"{role_name}.{band_key}")
        for weight_key in ("hook_weight", "payoff_weight"):
            weight = role_cfg.get(weight_key)
            if weight is None:
                continue
            if not isinstance(weight, (int, float)) or isinstance(weight, bool):
                raise ValueError(f"{role_name}.{weight_key} must be numeric")
            if float(weight) < 0 or float(weight) > 1:
                raise ValueError(f"{role_name}.{weight_key} must be within 0..1")
    return config


def validate_formulas_v2(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("root must be an object")
    level_map = config.get("level_to_mapped_score")
    if not isinstance(level_map, dict) or not level_map:
        raise ValueError("level_to_mapped_score must be a non-empty object")
    for key, value in level_map.items():
        try:
            level = int(key)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"level_to_mapped_score key invalid: {key}") from exc
        if level < 0 or level > 5:
            raise ValueError(f"level_to_mapped_score key out of range: {key}")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"level_to_mapped_score[{key}] must be numeric")
        if float(value) < 0 or float(value) > 100:
            raise ValueError(f"level_to_mapped_score[{key}] must be within 0..100")
    fit_cfg = config.get("fit_to_band")
    if fit_cfg is not None:
        if not isinstance(fit_cfg, dict):
            raise ValueError("fit_to_band must be an object")
        for key in ("in_band_score", "per_point_penalty"):
            if key not in fit_cfg:
                continue
            raw = fit_cfg[key]
            if not isinstance(raw, (int, float)) or isinstance(raw, bool):
                raise ValueError(f"fit_to_band.{key} must be numeric")
    return config


def load_scene_role_targets_bundle(
    *,
    explicit: Path | None = None,
    log_context: dict[str, Any] | None = None,
) -> RoleTargetsBundle:
    path, source, resolve_error = resolve_reader_journey_v2_config_path(
        SCENE_ROLE_TARGETS_FILENAME, explicit=explicit
    )
    ctx = dict(log_context or {})
    if path is None:
        provenance = ConfigProvenance(
            config_name=SCENE_ROLE_TARGETS_FILENAME,
            status="missing",
            source=source,
            version=None,
            content_hash=None,
            resolved_path=None,
            error=resolve_error or "file not found",
            quality_flags=("scene_role_targets_missing", "pacing_fit_unavailable"),
        )
        logger.error(
            "reader_journey_v2_config_load_failed %s",
            {**provenance.to_log_dict(), "affected_derivation": "pacing_fit", **ctx},
        )
        return RoleTargetsBundle(provenance=provenance, config=None)

    try:
        text = path.read_text(encoding="utf-8")
        raw = json.loads(text)
        validated = validate_scene_role_targets(raw)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        provenance = ConfigProvenance(
            config_name=SCENE_ROLE_TARGETS_FILENAME,
            status="invalid",
            source=source,
            version=None,
            content_hash=None,
            resolved_path=str(path),
            error=str(exc),
            quality_flags=("scene_role_targets_invalid", "pacing_fit_unavailable"),
        )
        logger.error(
            "reader_journey_v2_config_invalid %s",
            {**provenance.to_log_dict(), "affected_derivation": "pacing_fit", **ctx},
        )
        return RoleTargetsBundle(provenance=provenance, config=None)

    version = str(validated.get("version") or SCENE_ROLE_TARGETS_VERSION)
    provenance = ConfigProvenance(
        config_name=SCENE_ROLE_TARGETS_FILENAME,
        status="loaded",
        source=source,
        version=version,
        content_hash=_sha256_text(text),
        resolved_path=str(path),
        error=None,
        quality_flags=("scene_role_targets_loaded",),
    )
    logger.info(
        "reader_journey_v2_config_loaded %s",
        {**provenance.to_log_dict(), "affected_derivation": "pacing_fit", **ctx},
    )
    return RoleTargetsBundle(provenance=provenance, config=validated)


def embedded_formula_v2_defaults() -> dict[str, Any]:
    """Hardcoded fallback identical to production level map / fit_to_band defaults."""
    return {
        "version": "2.0",
        "contract_version": "2.0",
        "level_to_mapped_score": {
            "0": 10,
            "1": 30,
            "2": 50,
            "3": 65,
            "4": 80,
            "5": 95,
        },
        "no_evidence_mapped_score_cap": 40,
        "fit_to_band": {"in_band_score": 90, "per_point_penalty": 2},
        "weights": {
            "plot_progress": {
                "goal_progress": 0.25,
                "conflict_change": 0.20,
                "state_change": 0.20,
                "information_gain": 0.15,
                "character_agency": 0.10,
                "causal_coherence": 0.10,
            },
            "reading_tension": {
                "curiosity": 0.40,
                "tension": 0.35,
                "emotional_investment": 0.25,
            },
            "reading_momentum": {
                "plot_progress": 0.30,
                "reading_tension": 0.25,
                "pacing_fit": 0.20,
                "hook_payoff_fit": 0.25,
            },
        },
        "penalties": {
            "clarity_below": 60,
            "clarity_factor": 0.25,
            "cognitive_load_above": 60,
            "cognitive_load_factor": 0.15,
            "redundancy_above": 50,
            "redundancy_factor": 0.10,
        },
        "dropoff_risk": {
            "consecutive_decline_bonus": 8,
            "consecutive_low_momentum_threshold": 45,
            "consecutive_low_momentum_count": 3,
            "consecutive_low_momentum_bonus": 15,
            "unpaid_hook_threshold": 75,
            "unpaid_hook_bonus": 10,
            "reasonable_payoff_span_scenes": 3,
        },
    }


def load_formula_v2_bundle(
    *,
    explicit: Path | None = None,
    log_context: dict[str, Any] | None = None,
    allow_embedded_defaults: bool = True,
) -> FormulaV2Bundle:
    path, source, resolve_error = resolve_reader_journey_v2_config_path(
        FORMULAS_V2_FILENAME, explicit=explicit
    )
    ctx = dict(log_context or {})
    if path is None:
        if not allow_embedded_defaults:
            raise FileNotFoundError(resolve_error or FORMULAS_V2_FILENAME)
        defaults = embedded_formula_v2_defaults()
        provenance = ConfigProvenance(
            config_name=FORMULAS_V2_FILENAME,
            status="missing",
            source=source,
            version=str(defaults.get("version")),
            content_hash=_sha256_text(json.dumps(defaults, sort_keys=True)),
            resolved_path=None,
            error=resolve_error or "file not found; using embedded defaults",
            quality_flags=("formulas_v2_missing", "formulas_v2_defaults_embedded"),
        )
        logger.error(
            "reader_journey_v2_formulas_missing_using_defaults %s",
            {**provenance.to_log_dict(), "affected_derivation": "mapping+momentum", **ctx},
        )
        return FormulaV2Bundle(
            provenance=provenance, config=defaults, used_embedded_defaults=True
        )

    try:
        text = path.read_text(encoding="utf-8")
        raw = json.loads(text)
        validated = validate_formulas_v2(raw)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        if not allow_embedded_defaults:
            raise
        defaults = embedded_formula_v2_defaults()
        provenance = ConfigProvenance(
            config_name=FORMULAS_V2_FILENAME,
            status="invalid",
            source=source,
            version=str(defaults.get("version")),
            content_hash=None,
            resolved_path=str(path),
            error=f"{exc}; using embedded defaults",
            quality_flags=("formulas_v2_invalid", "formulas_v2_defaults_embedded"),
        )
        logger.error(
            "reader_journey_v2_formulas_invalid_using_defaults %s",
            {**provenance.to_log_dict(), "affected_derivation": "mapping+momentum", **ctx},
        )
        return FormulaV2Bundle(
            provenance=provenance, config=defaults, used_embedded_defaults=True
        )

    provenance = ConfigProvenance(
        config_name=FORMULAS_V2_FILENAME,
        status="loaded",
        source=source,
        version=str(validated.get("version") or "2.0"),
        content_hash=_sha256_text(text),
        resolved_path=str(path),
        error=None,
        quality_flags=("formulas_v2_loaded",),
    )
    logger.info(
        "reader_journey_v2_formulas_loaded %s",
        {**provenance.to_log_dict(), "affected_derivation": "mapping+momentum", **ctx},
    )
    return FormulaV2Bundle(provenance=provenance, config=validated, used_embedded_defaults=False)


def role_metric_band(
    role_targets: dict[str, Any],
    scene_role: str | None,
    metric: str,
) -> FitComputation | tuple[float, float]:
    """Return (low, high) for a role metric band, or unavailable FitComputation."""
    roles = role_targets.get("roles") if isinstance(role_targets, dict) else None
    if not isinstance(roles, dict) or not roles:
        return FitComputation(
            value=None,
            status="unavailable",
            reason_code=REASON_TARGETS_MISSING,
            quality_flags=("scene_role_targets_missing", "pacing_fit_unavailable"),
        )
    if not scene_role or scene_role not in roles:
        return FitComputation(
            value=None,
            status="unavailable",
            reason_code=REASON_ROLE_NOT_FOUND,
            quality_flags=("scene_role_not_found", "pacing_fit_unavailable"),
        )
    role_cfg = roles.get(scene_role)
    if not isinstance(role_cfg, dict) or metric not in role_cfg:
        return FitComputation(
            value=None,
            status="unavailable",
            reason_code=REASON_BAND_MISSING,
            quality_flags=("scene_role_band_missing", "pacing_fit_unavailable"),
        )
    try:
        return _validate_band(role_cfg[metric], field_name=f"{scene_role}.{metric}")
    except ValueError:
        return FitComputation(
            value=None,
            status="unavailable",
            reason_code=REASON_TARGETS_INVALID,
            quality_flags=("scene_role_targets_invalid", "pacing_fit_unavailable"),
        )


def role_pacing_band(
    role_targets: dict[str, Any],
    scene_role: str | None,
) -> FitComputation | tuple[float, float]:
    return role_metric_band(role_targets, scene_role, "pacing_speed")
