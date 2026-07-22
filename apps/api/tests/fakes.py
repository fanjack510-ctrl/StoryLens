import json
import re

from app.model_gateway.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ProviderHealth,
)


class FakeProvider(ModelProvider):
    name = "fake"
    default_model = "fake-scene-model"

    def __init__(self, responses: list[object] | None = None, healthy: bool = True) -> None:
        self.responses = responses or []
        self.healthy = healthy
        self.calls = 0
        self.requests: list[ModelRequest] = []

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(max_context_tokens=32000, default_timeout_seconds=1)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_name=self.name,
            status="healthy" if self.healthy else "unhealthy",
            detail=None if self.healthy else "fixture failure",
        )

    def _scene_profile_item(
        self,
        scene_id: int,
        scene_ordinal: int,
        paragraph_ids: list[str],
    ) -> dict[str, object]:
        first = paragraph_ids[0] if paragraph_ids else "B0001-C0001-P0001"
        last = paragraph_ids[-1] if paragraph_ids else first

        def carried_q(text: str) -> dict[str, object]:
            return {"question": text, "source": "carried_from_previous", "confidence": 0.7}

        def created_q(text: str) -> dict[str, object]:
            return {
                "question": text,
                "trigger_summary": f"Scene{scene_ordinal}通过异常细节引出{text[:20]}",
                "strength": 55,
                "evidence_paragraph_ids": [first],
            }

        if scene_ordinal == 1:
            q_in: list[dict] = []
            q_created = [
                created_q(f"Scene{scene_ordinal}开篇的异常细节意味着什么"),
            ]
            q_out = [
                {
                    "question": f"Scene{scene_ordinal}之后身份与动机是否一致",
                    "origin": "created_here",
                    "hook_type": "identity",
                    "strength": 45 + (scene_ordinal % 5) * 8,
                    "evidence_paragraph_ids": [last],
                }
            ]
            answered = []
        else:
            q_in = [carried_q(f"Scene{scene_ordinal - 1}之后身份与动机是否一致")]
            q_created = []
            q_out = [
                {
                    "question": f"Scene{scene_ordinal}的新线索能否闭合前一疑问",
                    "origin": "carried",
                    "hook_type": "information",
                    "strength": 45 + (scene_ordinal % 5) * 8,
                    "evidence_paragraph_ids": [last],
                }
            ]
            answered = [
                {
                    "question": f"Scene{scene_ordinal - 1}之后身份与动机是否一致",
                    "answer_summary": f"Scene{scene_ordinal}给出部分线索",
                    "answer_degree": "partial",
                    "evidence_paragraph_ids": [first],
                }
            ]

        return {
            "scene_id": scene_id,
            "scene_ordinal": scene_ordinal,
            "scene_value_summary": f"Scene{scene_ordinal}通过异常细节建立阅读牵引，而非单纯推进动作",
            "reader_question_in": q_in,
            "reader_question_created": q_created,
            "reader_question_answered": answered,
            "reader_question_out": q_out,
            "dominant_emotion": "好奇",
            "emotional_valence_start": -10,
            "emotional_valence_end": 15,
            "arousal_start": 30,
            "arousal_end": 55,
            "curiosity_score": 50 + scene_ordinal,
            "tension_score": 40 + (scene_ordinal % 7) * 5,
            "payoff_score": 35 + (scene_ordinal % 6) * 4,
            "hook_score": 40 + (scene_ordinal % 4) * 10,
            "information_gain_score": 45,
            "emotional_resonance_score": 38,
            "cognitive_load_score": 25 + (scene_ordinal % 3) * 5,
            "dropoff_risk_score": 20 + (scene_ordinal % 4) * 6,
            "payoffs": [
                {
                    "type": "information",
                    "summary": f"Scene{scene_ordinal}提供可验证的新信息",
                    "strength": 50,
                    "evidence_paragraph_ids": [last],
                }
            ],
            "hooks": [
                {
                    "type": "information",
                    "summary": f"Scene{scene_ordinal}留下未闭合的身份疑问",
                    "strength": 48,
                    "evidence_paragraph_ids": [last],
                }
            ],
            "techniques": [
                {
                    "code": "contrast_reveal",
                    "name": "反差揭示",
                    "mechanism": "先给出日常表象再露出异常细节",
                    "reader_effect": "让读者主动比对前后信息",
                    "transfer_formula": "日常动作+一处不合常理的细节",
                    "risk": "细节过弱则像笔误",
                    "evidence_paragraph_ids": [first],
                }
            ],
            "risk_points": [
                {
                    "type": "weak_hook",
                    "summary": "若后续Scene不承接疑问，牵引会衰减",
                    "severity": 30,
                    "evidence_paragraph_ids": [last],
                }
            ],
            "emotion_beats": [
                {"label": "疑惑", "valence": -5, "arousal": 40, "evidence_paragraph_ids": [first]}
            ],
            "information_changes": [
                {
                    "type": "new_information",
                    "summary": f"Scene{scene_ordinal}引入新的可观察事实",
                    "certainty": "fact",
                    "evidence_paragraph_ids": [first],
                }
            ],
            "character_effects": [
                {
                    "character_name": "主角",
                    "trait_or_change": "行动选择与此前印象形成对照",
                    "method": "action",
                    "evidence_paragraph_ids": [first],
                }
            ],
            "writing_takeaways": [
                {
                    "summary": "用可验证细节承载悬念",
                    "applicable_when": "悬疑开场",
                    "avoid_when": "需要快速交代世界观时",
                }
            ],
            "confidence": 0.75,
            "evidence_paragraph_ids": list(dict.fromkeys([first, last])),
        }

    def _reader_journey_scene_payload(self, combined: str) -> dict[str, object]:
        profiles = []
        for match in re.finditer(
            r'"scene_id":\s*(\d+).*?"scene_ordinal":\s*(\d+).*?"paragraphs":\s*(\[[^\]]*\])',
            combined,
            re.DOTALL,
        ):
            scene_id = int(match.group(1))
            ordinal = int(match.group(2))
            paragraphs_blob = match.group(3)
            try:
                paragraphs = json.loads(paragraphs_blob)
                paragraph_ids = [
                    item["id"] for item in paragraphs if isinstance(item, dict) and item.get("id")
                ]
            except json.JSONDecodeError:
                paragraph_ids = re.findall(r"B\d{4}-C\d{4}-P\d{4}", paragraphs_blob)
            if not paragraph_ids:
                paragraph_ids = re.findall(r"B\d{4}-C\d{4}-P\d{4}", combined)
            profiles.append(self._scene_profile_item(scene_id, ordinal, paragraph_ids))
        if not profiles:
            scene_ids = [int(item) for item in re.findall(r'"scene_id":\s*(\d+)', combined)]
            ordinals = [int(item) for item in re.findall(r'"scene_ordinal":\s*(\d+)', combined)]
            paragraph_ids = list(dict.fromkeys(re.findall(r"B\d{4}-C\d{4}-P\d{4}", combined)))
            for index, scene_id in enumerate(scene_ids):
                ordinal = ordinals[index] if index < len(ordinals) else index + 1
                chunk = paragraph_ids[:2] or ["B0001-C0001-P0001"]
                profiles.append(self._scene_profile_item(scene_id, ordinal, chunk))
        return {"contract_version": "1.2", "profiles": profiles}

    def _reader_journey_chapter_payload(self, combined: str) -> dict[str, object]:
        ordinals = sorted({int(item) for item in re.findall(r'"scene_ordinal":\s*(\d+)', combined)})
        if not ordinals:
            ordinals = list(range(1, 15))
        total = max(ordinals)
        # Production validate_chapter_synthesis: 1..min(6, scene_count) contiguous covering phases.
        if total >= 12:
            phase_count = 5
        elif total >= 8:
            phase_count = 4
        elif total >= 3:
            phase_count = min(3, total)
        else:
            phase_count = max(1, total)
        phase_count = min(phase_count, total, 6)
        base = total // phase_count
        rem = total % phase_count
        boundaries: list[tuple[int, int]] = []
        start = 1
        for i in range(phase_count):
            span = base + (1 if i < rem else 0)
            end = min(total, start + span - 1)
            boundaries.append((start, end))
            start = end + 1
        phases = []
        for index, (start, end) in enumerate(boundaries, 1):
            phases.append(
                {
                    "ordinal": index,
                    "title": f"阶段{index}",
                    "start_scene_ordinal": start,
                    "end_scene_ordinal": end,
                    "primary_reader_question": f"阶段{index}核心读者问题",
                    "dominant_emotion": "好奇与紧张",
                    "reading_payoff": f"阶段{index}建立阅读回报",
                    "continuation_motivation": "身份与风险尚未闭合",
                    "summary": f"阶段{index}承担节奏功能",
                    "confidence": 0.7,
                }
            )
        return {
            "contract_version": "1.2",
            "phases": phases,
            "chapter_reader_question_chain": [f"问题{i}" for i in range(1, 4)],
            "pacing_diagnosis": ["前段悬念建立有效", "中段信息密度适中"],
            "chapter_strengths": ["钩子分布较均衡"],
            "chapter_risks": ["个别Scene回报偏弱"],
            "one_sentence_diagnosis": "章节以身份悬念驱动阅读，中段需保持问题链闭合",
        }

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        self.requests.append(request)
        if self.responses:
            value = self.responses.pop(0)
            if isinstance(value, Exception):
                raise value
            if isinstance(value, ModelResponse):
                return value
            if isinstance(value, (dict, list)):
                return ModelResponse(
                    text=json.dumps(value, ensure_ascii=False),
                    model=self.default_model,
                    http_status_code=200,
                )
            return ModelResponse(text=str(value), model=self.default_model, http_status_code=200)
        combined = "\n".join(item["content"] for item in request.messages)
        paragraph_ids = list(dict.fromkeys(re.findall(r"B\d{4}-C\d{4}-P\d{4}", combined)))
        scene_ids = re.findall(r"B\d{4}-C\d{4}(?:-R\d{4})?-S\d{4}", combined)
        if not scene_ids:
            scene_ids = re.findall(r"B\d{4}-C\d{4}-S\d{4}", combined)
        journeyish = (
            "reader_journey_chapter" in combined
            or "reader_journey_scene" in combined
            or "章节阅读旅程" in combined
            or "读者阅读旅程" in combined
            or "JOURNEY_SCENE" in combined
            or "scene_profiles" in combined
            or "reading_momentum" in combined
        )
        if "reader_journey_chapter" in combined or "章节阅读旅程合成" in combined:
            payload = self._reader_journey_chapter_payload(combined)
        elif journeyish:
            payload = self._reader_journey_scene_payload(combined)
            # V2 prompts may omit regex-friendly scene blocks — synthesize from ordinals.
            if not payload.get("profiles"):
                ordinals = sorted(
                    {int(item) for item in re.findall(r'"scene_ordinal"\s*:\s*(\d+)', combined)}
                )
                if not ordinals:
                    ordinals = sorted(
                        {int(item) for item in re.findall(r"Scene\s*(\d+)", combined, re.I)}
                    )
                if not ordinals:
                    # Fall back to expected scene count hints in the prompt.
                    count_match = re.search(r"(?:scenes?|场景)\s*[:=]?\s*(\d+)", combined, re.I)
                    n = int(count_match.group(1)) if count_match else 2
                    ordinals = list(range(1, n + 1))
                paragraph_ids = paragraph_ids or ["B0001-C0001-P0001", "B0001-C0001-P0002"]
                profiles = []
                for ordinal in ordinals:
                    chunk = paragraph_ids[:2]
                    profiles.append(self._scene_profile_item(ordinal, ordinal, chunk))
                payload = {"contract_version": "1.2", "profiles": profiles}
        elif "场景边界识别器" in combined or "boundary_candidate" in combined:
            payload = {
                "chapter_id": paragraph_ids[0].rsplit("-P", 1)[0] if paragraph_ids else "B0001-C0001",
                "boundaries": [],
                "overall_confidence": 0.9,
            }
            if len(paragraph_ids) >= 4:
                payload["boundaries"] = [
                    {
                        "after_paragraph_id": paragraph_ids[1],
                        "reasons": ["地点发生变化"],
                        "confidence": 0.9,
                    }
                ]
        else:
            first, last = paragraph_ids[0], paragraph_ids[-1]

            def field(summary: str, ids: list[str]) -> dict[str, object]:
                return {"summary": summary, "evidence_paragraph_ids": ids}

            payload = {
                "scene_id": scene_ids[0] if scene_ids else "B0001-C0001-S0001",
                "entry_state": field("进入场景", [first]),
                "goal": field("完成当前行动", [first]),
                "obstacle": field("", []),
                "key_actions": [{"summary": "推进情节", "evidence_paragraph_ids": [first]}],
                "turning_point": field("", []),
                "outcome": field("状态发生变化", [last]),
                "unresolved_question": field("", []),
                "function_tags": ["事件推进"],
                "confidence": 0.8,
            }
        return ModelResponse(text=json.dumps(payload, ensure_ascii=False), model=self.default_model)
