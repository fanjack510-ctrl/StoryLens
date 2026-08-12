"""``UsageRecorder`` and ``TokenCalibrator`` — billing durability and token estimation.

**Why the recorder owns its own session.** A provider call is billed the moment the request
leaves, and nothing local can un-bill it. If the invocation row lived in the run's
transaction, any later failure in that transaction would roll the row back and the money
would vanish from the ledger while still being charged. The row is therefore written and
committed in a *separate* session, before the caller does anything else with the result, so
a process killed immediately afterwards still leaves evidence that the call happened and
what it cost (G3, G4).

**Why calibration has tiers.** Token estimates come from a chars-per-token ratio, and that
ratio differs by script and by model. Starting from a global default and narrowing as
observations accumulate means early runs are merely conservative rather than wrong, and a
model with three observations does not get treated as if it had three hundred.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.narrative_core.long_novel.contracts.enums import UnitKind

__all__ = ["ScriptClass", "CalibrationTier", "UsageRecorder", "TokenCalibrator", "CalibrationResult"]


class ScriptClass(StrEnum):
    """Text classes with materially different chars-per-token behaviour."""

    CJK = "cjk"
    LATIN = "latin"
    JSON_MIXED = "json_mixed"
    MIXED = "mixed"


class CalibrationTier(StrEnum):
    """Which evidence a ratio rests on. Narrower is better, but only with enough data."""

    MODEL_SCRIPT = "model_script"
    MODEL = "model"
    FAMILY = "family"
    DEFAULT = "default"


#: Conservative starting ratios (EMPIRICAL STARTING DEFAULT). Low ratios over-estimate token
#: counts, which is the safe direction: an over-estimate wastes some budget, an
#: under-estimate produces a request that will not fit after it has been assembled.
DEFAULT_CHARS_PER_TOKEN: dict[ScriptClass, float] = {
    ScriptClass.CJK: 1.325,
    ScriptClass.LATIN: 3.6,
    ScriptClass.JSON_MIXED: 3.0,
    ScriptClass.MIXED: 2.0,
}

#: Below this many observations a narrower tier is not trusted — three samples of one model
#: say almost nothing, and acting on them would be worse than the default.
MIN_OBSERVATIONS_FOR_TIER = 30


@dataclass(frozen=True)
class CalibrationResult:
    chars_per_token: float
    tier: CalibrationTier
    observation_count: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UsageRecorder:
    """Records every provider invocation durably, outside the caller's transaction.

    ``session_factory`` is injected so tests can supply a throwaway database and so the
    recorder never reaches for a global — the point of this class is transaction isolation,
    and a shared session would silently defeat it.
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def record(
        self,
        *,
        run_id: int,
        unit_kind: UnitKind,
        unit_key: str,
        provider_name: str,
        model_name: str,
        attempt_no: int,
        request_payload: object,
        raw_response_text: str,
        status: str,
        latency_ms: int,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        finish_reason: str | None = None,
        http_status_code: int | None = None,
        provider_input_fingerprint: str | None = None,
        is_cloud: bool = True,
    ) -> int:
        """Write one ``model_invocations`` row and commit it immediately.

        Returns the row id so the caller can link a ``long_novel_unit_attempts`` row to it.
        The commit happens here, in its own session, and is not deferred to the caller: a
        deferred commit is exactly the case where a crash loses a call that was paid for.
        """
        request_json = json.dumps(request_payload, sort_keys=True, ensure_ascii=False)
        request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        session = self._session_factory()
        try:
            result = session.execute(
                text(
                    """
                    INSERT INTO model_invocations (
                        run_id, task_type, provider_name, model_name, prompt_version,
                        schema_version, attempt_no, invocation_kind, request_hash,
                        input_snapshot_json, raw_response_text, status, latency_ms,
                        http_status_code, finish_reason, input_tokens, output_tokens,
                        unit_key, thinking_enabled, is_cloud, sends_content_to_cloud,
                        raw_logging_enabled, http_request_sent, audit_type, created_at
                    ) VALUES (
                        :run_id, :task_type, :provider_name, :model_name, :prompt_version,
                        :schema_version, :attempt_no, :invocation_kind, :request_hash,
                        :input_snapshot_json, :raw_response_text, :status, :latency_ms,
                        :http_status_code, :finish_reason, :input_tokens, :output_tokens,
                        :unit_key, :thinking_enabled, :is_cloud, :sends_content_to_cloud,
                        :raw_logging_enabled, :http_request_sent, :audit_type, :created_at
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "task_type": f"long_novel.{unit_kind.value}",
                    "provider_name": provider_name,
                    "model_name": model_name,
                    "prompt_version": "lne.v1",
                    "schema_version": "lne.v1",
                    "attempt_no": attempt_no,
                    "invocation_kind": "repair" if unit_kind is UnitKind.REPAIR else "initial",
                    "request_hash": provider_input_fingerprint or request_hash,
                    "input_snapshot_json": request_json,
                    "raw_response_text": raw_response_text,
                    "status": status,
                    "latency_ms": latency_ms,
                    "http_status_code": http_status_code,
                    "finish_reason": finish_reason,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "unit_key": unit_key,
                    # NOT NULL columns whose defaults are declared Python-side on the ORM
                    # model. A raw INSERT does not get them, so they are supplied here
                    # rather than discovered as an IntegrityError at the first real call.
                    "thinking_enabled": False,
                    "is_cloud": is_cloud,
                    "sends_content_to_cloud": is_cloud,
                    "raw_logging_enabled": False,
                    "http_request_sent": True,
                    "audit_type": "provider_invocation",
                    "created_at": _utc_now(),
                },
            )
            session.commit()
            row_id = result.lastrowid
            return int(row_id) if row_id is not None else 0
        finally:
            session.close()


class TokenCalibrator:
    """Chars-per-token ratios, narrowed by evidence.

    Four tiers, tried narrowest first: (model, script) → model → provider family → default.
    A tier is only used once it has enough observations to mean something; otherwise the
    search falls through. That is what keeps a handful of early samples from swinging the
    planner around.
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def resolve(
        self, *, provider_name: str, model_name: str, script_class: ScriptClass
    ) -> CalibrationResult:
        session = self._session_factory()
        try:
            row = session.execute(
                text(
                    """
                    SELECT median_chars_per_token, observation_count
                      FROM long_novel_token_calibrations
                     WHERE provider_name = :p AND model_name = :m AND script_class = :s
                    """
                ),
                {"p": provider_name, "m": model_name, "s": script_class.value},
            ).first()
            if row and row[1] >= MIN_OBSERVATIONS_FOR_TIER:
                return CalibrationResult(float(row[0]), CalibrationTier.MODEL_SCRIPT, int(row[1]))

            row = session.execute(
                text(
                    """
                    SELECT AVG(median_chars_per_token), SUM(observation_count)
                      FROM long_novel_token_calibrations
                     WHERE provider_name = :p AND model_name = :m
                    """
                ),
                {"p": provider_name, "m": model_name},
            ).first()
            if row and row[0] is not None and (row[1] or 0) >= MIN_OBSERVATIONS_FOR_TIER:
                return CalibrationResult(float(row[0]), CalibrationTier.MODEL, int(row[1]))

            row = session.execute(
                text(
                    """
                    SELECT AVG(median_chars_per_token), SUM(observation_count)
                      FROM long_novel_token_calibrations
                     WHERE provider_name = :p AND script_class = :s
                    """
                ),
                {"p": provider_name, "s": script_class.value},
            ).first()
            if row and row[0] is not None and (row[1] or 0) >= MIN_OBSERVATIONS_FOR_TIER:
                return CalibrationResult(float(row[0]), CalibrationTier.FAMILY, int(row[1]))

            return CalibrationResult(DEFAULT_CHARS_PER_TOKEN[script_class], CalibrationTier.DEFAULT, 0)
        finally:
            session.close()

    def observe(
        self,
        *,
        provider_name: str,
        model_name: str,
        script_class: ScriptClass,
        chars: int,
        tokens: int,
    ) -> None:
        """Fold one measurement into the stored ratio.

        Uses a running mean rather than storing every sample: the planner needs a central
        tendency, and an unbounded observation table would grow with every call made.
        A zero or negative token count is discarded rather than averaged in — it is a
        provider reporting gap, not a measurement of a very efficient tokenizer.
        """
        if tokens <= 0 or chars <= 0:
            return
        ratio = chars / tokens
        session = self._session_factory()
        try:
            row = session.execute(
                text(
                    """
                    SELECT id, observation_count, median_chars_per_token
                      FROM long_novel_token_calibrations
                     WHERE provider_name = :p AND model_name = :m AND script_class = :s
                    """
                ),
                {"p": provider_name, "m": model_name, "s": script_class.value},
            ).first()
            now = _utc_now()
            if row is None:
                session.execute(
                    text(
                        """
                        INSERT INTO long_novel_token_calibrations (
                            provider_name, model_name, script_class, observation_count,
                            median_chars_per_token, last_observed_at, updated_at
                        ) VALUES (:p, :m, :s, 1, :r, :now, :now)
                        """
                    ),
                    {"p": provider_name, "m": model_name, "s": script_class.value, "r": ratio, "now": now},
                )
            else:
                row_id, count, current = int(row[0]), int(row[1]), float(row[2])
                blended = (current * count + ratio) / (count + 1)
                session.execute(
                    text(
                        """
                        UPDATE long_novel_token_calibrations
                           SET observation_count = :c,
                               median_chars_per_token = :r,
                               last_observed_at = :now,
                               updated_at = :now
                         WHERE id = :id
                        """
                    ),
                    {"c": count + 1, "r": blended, "now": now, "id": row_id},
                )
            session.commit()
        finally:
            session.close()

    @staticmethod
    def classify(text_value: str) -> ScriptClass:
        """Pick the script class a piece of text should be estimated with."""
        if not text_value:
            return ScriptClass.MIXED
        cjk = sum(1 for ch in text_value if "一" <= ch <= "鿿")
        ratio = cjk / len(text_value)
        if ratio > 0.5:
            return ScriptClass.CJK
        if ratio < 0.05:
            return ScriptClass.LATIN
        return ScriptClass.MIXED

    def estimate_tokens(
        self, text_value: str, *, provider_name: str, model_name: str
    ) -> tuple[int, CalibrationResult]:
        script_class = self.classify(text_value)
        calibration = self.resolve(
            provider_name=provider_name, model_name=model_name, script_class=script_class
        )
        # Round up: a fractional token still occupies a whole one, and rounding down would
        # under-estimate in the direction that makes a request not fit.
        estimated = -(-len(text_value) * 100 // int(calibration.chars_per_token * 100))
        return estimated, calibration
