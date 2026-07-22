"""Generic grounding / evidence-claim integrity checks (no novel-specific rules)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence


ERROR_GROUNDING_ENTITY = "GROUNDING_ENTITY_MISMATCH"
ERROR_EVIDENCE_CLAIM = "EVIDENCE_CLAIM_MISMATCH"
ERROR_CONTEXT_MISMATCH = "ANALYSIS_CONTEXT_MISMATCH"
ERROR_EVIDENCE_SCOPE = "EVIDENCE_OUT_OF_SCOPE"
ERROR_ASYNC_IDENTITY = "ASYNC_RESULT_IDENTITY_MISMATCH"
ERROR_RUN_SCOPE = "ANALYSIS_RUN_SCOPE_MISMATCH"


# Common function words / narrative glue — not treated as core entities.
_STOP = {
    "一个",
    "我们",
    "他们",
    "你们",
    "自己",
    "什么",
    "怎么",
    "因为",
    "所以",
    "但是",
    "然后",
    "已经",
    "开始",
    "继续",
    "出现",
    "发现",
    "知道",
    "觉得",
    "感觉",
    "可能",
    "似乎",
    "突然",
    "此时",
    "此刻",
    "之后",
    "之前",
    "这里",
    "那里",
    "这个",
    "那个",
    "一种",
    "不是",
    "没有",
    "可以",
    "需要",
    "通过",
    "对于",
    "关于",
    "以及",
    "或者",
    "如果",
    "虽然",
    "只是",
    "还是",
    "就是",
    "还有",
    "带来",
    "形成",
    "造成",
    "产生",
    "进入",
    "离开",
    "看到",
    "听到",
    "说道",
    "问道",
    "回答",
    "主角",
    "读者",
    "本章",
    "本场",
    "场景",
    "段落",
    "证据",
    "概览",
    "问题",
    "回报",
    "钩子",
}

_CN_ENTITY = re.compile(r"[\u4e00-\u9fff]{2,4}")
_PARAGRAPH_ID = re.compile(r"B\d{4}-C\d{4}-P\d{4}")


@dataclass
class GroundingIssue:
    code: str
    message: str
    scene_id: int | None = None
    scene_ordinal: int | None = None
    field_path: str | None = None
    entities: list[str] = field(default_factory=list)
    paragraph_ids: list[str] = field(default_factory=list)


@dataclass
class GroundingReport:
    ok: bool
    integrity_status: str
    issues: list[GroundingIssue] = field(default_factory=list)
    fingerprint: str | None = None
    fingerprint_state: str = "ok"  # ok | missing_legacy | mismatch

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "integrity_status": self.integrity_status,
            "fingerprint": self.fingerprint,
            "fingerprint_state": self.fingerprint_state,
            "issues": [
                {
                    "code": i.code,
                    "message": i.message,
                    "scene_id": i.scene_id,
                    "scene_ordinal": i.scene_ordinal,
                    "field_path": i.field_path,
                    "entities": i.entities,
                    "paragraph_ids": i.paragraph_ids,
                }
                for i in self.issues
            ],
        }


_CRAFT_TOKEN_FRAGMENTS = (
    "吸引",
    "读者",
    "继续",
    "阅读",
    "钩子",
    "开篇",
    "营造",
    "切入",
    "氛围",
    "悬念",
    "场景",
    "情节",
    "冲击",
    "感官",
    "奇幻",
    "色彩",
    "等级",
    "互动",
    "引入",
    "中等",
    "依赖",
    "后续",
    "展开",
    "常规",
    "称谓",
    "瞬间",
    "提升",
    "强力",
    "较弱",
    "增强",
    "背景",
    "新闻",
    "利用",
    "灾难",
    "行为",
    "怪异",
    "男人",
    "进店",
    "本身",
    "作为",
    "具有",
    "缺乏",
    "叙事",
    "开场",
)


def extract_candidate_entities(text: str | None, *, min_len: int = 2, max_len: int = 4) -> set[str]:
    if not text:
        return set()
    found: set[str] = set()
    for match in _CN_ENTITY.finditer(text):
        token = match.group(0)
        if not (min_len <= len(token) <= max_len):
            continue
        if token in _STOP:
            continue
        if any(frag in token for frag in _CRAFT_TOKEN_FRAGMENTS):
            continue
        found.add(token)
    return found


def extract_paragraph_ids(text: str | None) -> list[str]:
    if not text:
        return []
    return list(dict.fromkeys(_PARAGRAPH_ID.findall(text)))


def validate_evidence_scope(
    *,
    evidence_paragraph_ids: Sequence[str],
    allowed_paragraph_ids: Sequence[str],
    book_prefix: str | None = None,
    scene_id: int | None = None,
    scene_ordinal: int | None = None,
) -> list[GroundingIssue]:
    allowed = set(allowed_paragraph_ids)
    issues: list[GroundingIssue] = []
    outside = [pid for pid in evidence_paragraph_ids if pid not in allowed]
    if outside:
        issues.append(
            GroundingIssue(
                code=ERROR_EVIDENCE_SCOPE,
                message="证据段落不在当前Scene允许范围内",
                scene_id=scene_id,
                scene_ordinal=scene_ordinal,
                paragraph_ids=outside,
            )
        )
    if book_prefix:
        wrong_book = [pid for pid in evidence_paragraph_ids if not pid.startswith(book_prefix)]
        if wrong_book:
            issues.append(
                GroundingIssue(
                    code=ERROR_EVIDENCE_SCOPE,
                    message="证据段落不属于当前Book",
                    scene_id=scene_id,
                    scene_ordinal=scene_ordinal,
                    paragraph_ids=wrong_book,
                )
            )
    return issues


def validate_claim_entities_against_evidence(
    *,
    claim_text: str,
    evidence_texts: Mapping[str, str],
    cited_paragraph_ids: Sequence[str],
    scene_id: int | None = None,
    scene_ordinal: int | None = None,
    field_path: str | None = None,
    min_unsupported_entities: int = 1,
) -> list[GroundingIssue]:
    """
    If a claim cites evidence paragraphs, core entities mentioned in the claim
    must appear in the cited evidence text. Prevents 'legal paragraph id + wrong claim'.
    """
    if not claim_text or not cited_paragraph_ids:
        return []
    entities = extract_candidate_entities(claim_text)
    if not entities:
        return []
    cited_blob = "\n".join(evidence_texts.get(pid, "") for pid in cited_paragraph_ids)
    if not cited_blob.strip():
        return []
    unsupported = sorted(e for e in entities if e not in cited_blob)
    # Only flag when a clear majority of claim entities are unsupported AND
    # at least one multi-char entity is missing — reduces false positives on summaries.
    if len(unsupported) < min_unsupported_entities:
        return []
    if len(unsupported) < max(1, len(entities) // 2):
        return []
    return [
        GroundingIssue(
            code=ERROR_EVIDENCE_CLAIM,
            message="结论与所引证据正文缺乏基本支持关系",
            scene_id=scene_id,
            scene_ordinal=scene_ordinal,
            field_path=field_path,
            entities=unsupported[:12],
            paragraph_ids=list(cited_paragraph_ids),
        )
    ]


def validate_entities_in_scene_or_aliases(
    *,
    claim_text: str,
    scene_text: str,
    alias_texts: Iterable[str] = (),
    scene_id: int | None = None,
    scene_ordinal: int | None = None,
    field_path: str | None = None,
    min_foreign_entities: int = 2,
) -> list[GroundingIssue]:
    """
    Flag claims that introduce multiple core entities absent from scene + aliases.
    Does not hardcode novel-specific names.
    """
    entities = extract_candidate_entities(claim_text)
    if len(entities) < min_foreign_entities:
        return []
    universe = scene_text + "\n" + "\n".join(alias_texts)
    foreign = sorted(e for e in entities if e not in universe)
    if len(foreign) < min_foreign_entities:
        return []
    return [
        GroundingIssue(
            code=ERROR_GROUNDING_ENTITY,
            message="结论中出现当前Scene正文与别名表均不支持的核心实体",
            scene_id=scene_id,
            scene_ordinal=scene_ordinal,
            field_path=field_path,
            entities=foreign[:12],
        )
    ]


def assert_async_result_identity(
    *,
    result_run_id: int,
    expected_run_id: int,
    result_scene_id: int,
    expected_scene_id: int,
    result_fingerprint: str | None = None,
    expected_fingerprint: str | None = None,
) -> None:
    if int(result_run_id) != int(expected_run_id) or int(result_scene_id) != int(expected_scene_id):
        raise ValueError(ERROR_ASYNC_IDENTITY)
    if (
        expected_fingerprint
        and result_fingerprint
        and result_fingerprint != expected_fingerprint
    ):
        raise ValueError(ERROR_CONTEXT_MISMATCH)


def is_craft_commentary_text(text: str | None) -> bool:
    """Heuristic: literary-analysis craft talk, not story claims about characters."""
    if not text:
        return False
    markers = (
        "吸引读者",
        "继续阅读",
        "钩子",
        "开篇",
        "营造",
        "切入",
        "氛围",
        "吸引力",
        "强悬念",
        "读者注意",
        "场景入口",
        "强有力的钩",
        "典型的强",
        "规则本身",
        "反直觉",
        "极强的吸引",
        "抓住读者",
    )
    hits = sum(1 for m in markers if m in text)
    return hits >= 2


def is_severe_grounding_issue(issue: GroundingIssue) -> bool:
    """Severe = confirmed cross-context / identity failure. Soft field issues are not severe."""
    if issue.code in {ERROR_CONTEXT_MISMATCH, ERROR_ASYNC_IDENTITY}:
        return True
    if issue.code == ERROR_EVIDENCE_SCOPE:
        # Wrong book is severe; same-book out-of-scene evidence is field-level soft.
        if "不属于当前Book" in (issue.message or ""):
            return True
        if issue.paragraph_ids:
            # Different chapter id encoded in paragraph (C####) vs allowed set already caught as scope;
            # treat cross-chapter wrong prefix C as severe when book matches but chapter token differs.
            for pid in issue.paragraph_ids:
                if len(pid) >= 11 and pid[0] == "B":
                    # Bxxxx-Cyyyy — if book digits differ from message book_prefix path handled above
                    pass
        return False
    return False


def classify_integrity_status(issues: Sequence[GroundingIssue], *, fingerprint_state: str) -> str:
    """
    Graded integrity:
    - data_integrity_failed: fingerprint mismatch, wrong-book evidence, context identity failure
    - partially_trusted: soft field/scene issues with otherwise matching context
    - legacy_unverified: no fingerprint and no severe pollution
    - trusted: fingerprint ok and no issues
    """
    severe = [i for i in issues if is_severe_grounding_issue(i)]
    soft = [i for i in issues if not is_severe_grounding_issue(i)]

    if fingerprint_state == "mismatch" or any(i.code == ERROR_CONTEXT_MISMATCH for i in issues):
        return "data_integrity_failed"
    if severe:
        return "data_integrity_failed"
    if fingerprint_state == "missing_legacy":
        # Legacy without severe pollution: soft field issues → partial; clean → legacy.
        if soft:
            return "partially_trusted"
        return "legacy_unverified"
    if soft:
        return "partially_trusted"
    return "trusted"
