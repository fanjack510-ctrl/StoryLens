"""Build a reusable, originality-safe writing skill from a completed whole-book report.

The skill is deliberately deterministic: it reorganises an already validated
``WholeBookAnalysisV2`` result and never calls a model.  This keeps the generated file
traceable to the selected analysis run and avoids turning a book's prose into a style clone.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.narrative_core.whole_book_v2.contracts import WholeBookAnalysisV2


class BookSkillArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["storylens-book-skill/1.0"] = "storylens-book-skill/1.0"
    filename: str
    skill_name: str
    book_id: int
    source_run_id: int
    source_title: str
    content: str
    sections: list[str] = Field(default_factory=list)


def _slug(book_id: int) -> str:
    return f"storylens-book-{int(book_id)}"


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _known_names(result: WholeBookAnalysisV2) -> list[str]:
    names = [result.book_metadata.title, result.overview.protagonist]
    for character in result.characters.major_characters:
        names.extend([character.name, *character.aliases])
    return sorted({_clean(name) for name in names if _clean(name)}, key=len, reverse=True)


def _transfer_text(value: object, *, names: list[str]) -> str:
    """Remove source-specific names while preserving the analysed mechanism."""
    text = _clean(value)
    for name in names:
        text = text.replace(name, "参考角色")
    return text


def _bullets(values: Iterable[object], *, names: list[str], limit: int = 6) -> list[str]:
    items: list[str] = []
    for value in values:
        text = _transfer_text(value, names=names)
        if text and text not in items:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def _append_list(lines: list[str], values: Iterable[str], empty: str = "以新故事目标为准") -> None:
    material = list(values)
    if not material:
        lines.append(f"- {empty}")
        return
    lines.extend(f"- {item}" for item in material)


def build_book_skill(result: WholeBookAnalysisV2, *, source_run_id: int) -> BookSkillArtifact:
    """Convert one complete report into a downloadable ``SKILL.md`` artifact."""
    names = _known_names(result)
    title = _clean(result.book_metadata.title) or f"书籍 {result.book_metadata.book_id}"
    skill_name = _slug(result.book_metadata.book_id)
    profile = result.type_profile
    sections: list[str] = []
    lines = [
        "---",
        f"name: {skill_name}",
        "description: 根据一部已完成全文拆解的小说，迁移其结构、人物功能、悬念与节奏机制，创作全新故事；禁止复制原文、专有设定和人物。",
        "---",
        "",
        f"# 《{title}》作品机制迁移 Skill",
        "",
        f"> 来源：StoryLens 全书拆解任务 #{int(source_run_id)}。本文件只使用分析结论，不包含原文摘录。",
        "",
        "## 使用边界",
        "",
        "- 学习的是结构机制，不是作者句式、标志性措辞或可识别桥段。",
        "- 必须更换人物身份、关系组合、世界规则、关键道具、事件因果与结局答案。",
        "- 不复刻原书专有名词，不续写原作，不把分析结论冒充普遍写作定律。",
        "- 先生成新故事前提，再按下列机制逐项适配；不允许直接替换原作人名后复用剧情。",
    ]
    sections.append("使用边界")

    lines.extend(["", "## 作品机制画像", ""])
    sections.append("作品机制画像")
    lines.append(f"- 主类型：{_transfer_text(profile.primary_genre, names=names) or '未标明'}")
    _append_list(
        lines,
        [f"叙事驱动：{value}" for value in _bullets(profile.narrative_drivers, names=names, limit=5)],
    )
    _append_list(
        lines,
        [f"分析重点：{value}" for value in _bullets(profile.analysis_focus, names=names, limit=5)],
    )
    skeleton = _bullets(result.overview.story_skeleton, names=names, limit=8)
    _append_list(lines, [f"全书骨架：{value}" for value in skeleton])

    lines.extend(["", "## 结构迁移模板", ""])
    sections.append("结构迁移模板")
    for index, stage in enumerate(result.story.structure_stages[:9], start=1):
        goal = _transfer_text(stage.stage_goal, names=names)
        conflict = _transfer_text(stage.core_conflict, names=names)
        choice = _transfer_text(stage.major_choice, names=names)
        costs = "、".join(_bullets(stage.cost_paid, names=names, limit=3)) or "产生不可逆代价"
        gains = "、".join(_bullets(stage.gain_received, names=names, limit=3)) or "获得进入下一阶段的条件"
        question = _transfer_text(stage.next_question, names=names) or "下一阶段如何兑现选择？"
        lines.extend([
            f"### 阶段 {index}（参考跨度：第 {stage.chapter_start}—{stage.chapter_end} 章）",
            f"- 目标：{goal or '推进阶段目标'}",
            f"- 冲突：{conflict or '目标与阻力正面碰撞'}",
            f"- 关键选择：{choice or '让角色主动承担后果'}",
            f"- 代价 / 收获：{costs} / {gains}",
            f"- 章末承诺：{question}",
            "- 迁移要求：保留这一步承担的功能，重新设计事件、人物和答案。",
            "",
        ])

    lines.extend(["## 人物功能系统", ""])
    sections.append("人物功能系统")
    functions = []
    for character in result.characters.major_characters[:10]:
        function = _transfer_text(character.function or character.role, names=names)
        relation = _transfer_text(character.relationship_to_protagonist, names=names)
        if function or relation:
            functions.append(f"{function or '关键角色'}；与主角的结构关系：{relation or '推动选择'}")
    _append_list(lines, functions, "先列出每个角色不可替代的叙事功能，再决定身份与姓名")
    lines.extend([
        "- 主角必须在至少三个阶段发生目标、能力、关系或信念上的可验证变化。",
        "- 配角不按人数配额生成；只有承担独立功能、制造选择或承接后果的人才保留。",
    ])

    lines.extend(["", "## 悬念与信息释放", ""])
    sections.append("悬念与信息释放")
    lifecycles = sorted(result.suspense.lifecycles, key=lambda item: item.importance, reverse=True)
    for index, lifecycle in enumerate(lifecycles[:6], start=1):
        question = _transfer_text(lifecycle.question, names=names)
        effect = _transfer_text(lifecycle.storyline_effect, names=names)
        payoff = _transfer_text(lifecycle.payoff or lifecycle.twist, names=names)
        lines.append(
            f"- 悬念链 {index}：先提出“{question or '未解释的异常'}”，"
            f"通过新线索改变理解，最终以“{payoff or '答案改变角色选择'}”回收；"
            f"它必须{effect or '推动主线进入下一状态'}。"
        )
    if not lifecycles:
        lines.append("- 每条主要悬念都要记录：问题 → 线索 → 局部揭示 → 认知修正 → 回收。")

    lines.extend(["", "## 节奏与章节职责", ""])
    sections.append("节奏与章节职责")
    primary_functions = Counter(
        _transfer_text(item.primary_function, names=names)
        for item in result.chapters.functions
        if _transfer_text(item.primary_function, names=names)
    )
    _append_list(
        lines,
        [f"常用章节职责：{name}（参考报告中 {count} 章）" for name, count in primary_functions.most_common(6)],
        "每章只确定一个首要职责，并用次要职责补充",
    )
    for region in result.pacing.pacing_regions[:6]:
        lines.append(
            f"- 第 {region.chapter_start}—{region.chapter_end} 章的节奏功能："
            f"{_transfer_text(region.reason, names=names) or region.type}；"
            f"迁移时检查：{_transfer_text(region.diagnosis, names=names) or '强弱变化是否服务结构节点'}。"
        )

    techniques = result.story_breakdown.reusable_techniques
    if techniques:
        lines.extend(["", "## 可迁移技法", ""])
        sections.append("可迁移技法")
        for technique in techniques[:10]:
            lines.extend([
                f"### {_transfer_text(technique.name, names=names) or '未命名技法'}",
                f"- 做什么：{_transfer_text(technique.what_it_is, names=names)}",
                f"- 为什么有效：{_transfer_text(technique.why_it_works, names=names)}",
                f"- 如何迁移：{_transfer_text(technique.transfers_to, names=names)}",
                "",
            ])

    lines.extend([
        "## 执行流程",
        "",
        "1. 写出与参考作品完全不同的一句话故事、主角身份和核心冲突。",
        "2. 按“结构迁移模板”分阶段，但允许根据新故事长度合并或拆分阶段。",
        "3. 为每个阶段填写目标、阻力、主动选择、真实代价、阶段收获和下一问题。",
        "4. 建立人物功能表；删除没有独立功能、只负责递信息的角色。",
        "5. 建立悬念生命周期表，确保每个承诺有证据推进和明确回收位置。",
        "6. 给每章标一个首要职责；连续三章职责相同时必须说明其递进差异。",
        "7. 完稿后执行下方原创性与结构检查。",
        "",
        "## 交付前检查",
        "",
        "- [ ] 新故事不存在参考作品的人名、地名、组织、道具组合和关键答案。",
        "- [ ] 每个阶段都发生了状态变化，而不是只增加事件数量。",
        "- [ ] 主角的重要获得都对应已发生的代价或选择。",
        "- [ ] 主要悬念都能定位到提出、推进、修正和回收节点。",
        "- [ ] 每个核心配角都能回答“删掉他，故事会缺什么”。",
        "- [ ] 章节职责有变化，过渡章也产生新条件或新问题。",
        "- [ ] 最终文本没有复写参考作品的句式、场面调度或可识别桥段。",
        "",
        "## 来源与可核对性",
        "",
        f"- StoryLens 书籍 ID：{result.book_metadata.book_id}",
        f"- 全书分析任务：{int(source_run_id)}",
        f"- 分析覆盖：{result.book_metadata.chapter_count} 章",
        f"- 证据索引：{len(result.evidence_index)} 条（本 Skill 不携带原文摘录）",
    ])
    sections.extend(["执行流程", "交付前检查", "来源与可核对性"])

    return BookSkillArtifact(
        filename=f"{skill_name}-SKILL.md",
        skill_name=skill_name,
        book_id=int(result.book_metadata.book_id),
        source_run_id=int(source_run_id),
        source_title=title,
        content="\n".join(lines).strip() + "\n",
        sections=sections,
    )
