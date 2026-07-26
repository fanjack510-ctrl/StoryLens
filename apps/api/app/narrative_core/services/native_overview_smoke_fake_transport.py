"""Smoke-only Fake transport for Private native overview (Windows RC / offline).

Enabled only when ``STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE=1``.
Never the product default. Never used for Live Provider evidence.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any


_SMOKE_FAKE_ENV = "STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE"


def is_native_overview_smoke_fake_enabled() -> bool:
    raw = os.environ.get(_SMOKE_FAKE_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _extract_json_after_marker(prompt: str, marker: str) -> dict[str, Any]:
    idx = prompt.find(marker)
    if idx < 0:
        raise ValueError(f"marker not found: {marker!r}")
    blob = prompt[idx + len(marker) :]
    decoder = json.JSONDecoder()
    data, _ = decoder.raw_decode(blob.lstrip())
    if not isinstance(data, dict):
        raise ValueError("expected JSON object after marker")
    return data


def _window_json_from_prompt(prompt: str) -> str:
    body = _extract_json_after_marker(prompt, "Window analysis request (JSON):\n")
    paragraphs = list(body.get("paragraphs") or [])
    if not paragraphs:
        raise ValueError("window prompt must include paragraphs")
    first = paragraphs[0]
    pid = str(first["paragraph_id"])
    chapter_id = str(first["chapter_id"])
    text = str(first["text"])
    quote = text[: min(12, len(text))] or text
    payload = {
        "contract_version": "1.0",
        "run_id": str(body.get("run_id") or "0"),
        "window_id": str(body.get("window_id") or "w-0"),
        "input_hash": str(body.get("input_hash") or ""),
        "candidate_entities": [
            {
                "candidate_id": "ce-1",
                "entity_type": "character",
                "canonical_name": "主角",
                "aliases": [],
                "description": "",
                "confidence": 0.9,
                "evidence_refs": ["ev-1"],
            }
        ],
        "candidate_assets": [
            {
                "candidate_id": "ca-1",
                "asset_type": "goal",
                "title": "推进主线",
                "summary": "从窗口证据得出的目标候选",
                "subject_candidate_ids": ["ce-1"],
                "object_candidate_ids": [],
                "confidence": 0.7,
                "evidence_refs": ["ev-1"],
                "deduplication_key": f"goal:{pid}",
            }
        ],
        "candidate_evidence": [
            {
                "evidence_id": "ev-1",
                "paragraph_id": pid,
                "chapter_id": chapter_id,
                "quote": quote,
                "evidence_role": "support",
                "confidence": 0.95,
                "supports_candidate_ids": ["ce-1"],
            }
        ],
        "state_delta": {},
        "warnings": [],
        "quality": {
            "confidence": 0.8,
            "repair_attempted": False,
            "repair_succeeded": False,
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _projection_json_from_prompt(prompt: str) -> str:
    run_match = re.search(r'"run_id"\s*:\s*"([^"]+)"', prompt)
    run_id = run_match.group(1) if run_match else "0"
    insufficient = {
        "value": None,
        "confidence": 0.0,
        "evidence_refs": [],
        "status": "insufficient_evidence",
    }
    payload = {
        "contract_version": "1.0",
        "run_id": run_id,
        "novel_type": {
            "value": "adventure",
            "confidence": 0.55,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "narrative_features": {
            "value": ["window-derived"],
            "confidence": 0.5,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "core_setting": {
            "value": "derived setting",
            "confidence": 0.5,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "protagonist": {
            "value": "主角",
            "confidence": 0.6,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "protagonist_core_goal": {
            "value": "推进主线",
            "confidence": 0.55,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "primary_conflict": insufficient,
        "central_question": {
            "value": "故事如何收束？",
            "confidence": 0.5,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "key_turning_points": insufficient,
        "climax": insufficient,
        "resolved_problem": insufficient,
        "ending_state": insufficient,
        "logline": {
            "value": "一段由窗口证据支撑的概要。",
            "confidence": 0.55,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "synopsis": {
            "value": "基于窗口段落的离线概要合成。",
            "confidence": 0.55,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "warnings": [],
    }
    return json.dumps(payload, ensure_ascii=False)


class NativeOverviewSmokeFakeTransport:
    """Valid Private window/projection JSON for RC install-chain smoke only."""

    def __init__(self) -> None:
        self.call_log: list[dict[str, Any]] = []
        self._index = 0

    @property
    def call_count(self) -> int:
        return len(self.call_log)

    def request(
        self,
        prompt: str,
        model_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = dict(model_options or {})
        self.call_log.append(
            {
                "prompt": prompt,
                "model_options": options,
                "call_index": self._index,
            }
        )
        stage = str(options.get("stage") or "")
        if stage == "synthesize_overview" or "Synthesis" in prompt or "projection" in prompt.lower():
            text = _projection_json_from_prompt(prompt)
        else:
            text = _window_json_from_prompt(prompt)
        response = {"text": text, "ok": True}
        self.call_log[-1]["response"] = dict(response)
        self._index += 1
        return response


__all__ = [
    "NativeOverviewSmokeFakeTransport",
    "is_native_overview_smoke_fake_enabled",
]
