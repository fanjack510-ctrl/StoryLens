# -*- coding: utf-8 -*-
"""material_lab 桥接层的自包含冒烟测试。

引擎与源项目 novel-material-lab 的等价性已在迁入时用两本真书验证过
（字节级哈希一致 + 同输入逐字段一致 + 全书分布仅差章节边界）；
这里守住的是迁入后的行为不被无意改动：纯逻辑、零数据库、可从仓库根直接跑。
"""
from __future__ import annotations

from app.narrative_core.material_lab import (
    chapter_text_from_paragraphs,
    extract_book_materials,
    extract_chapter_materials,
    guess_genre,
)

# 刻意堆入悬疑信号词 + 物件 + 地点 + 时间线索的合成章节
_XUANYI_CHAPTER = (
    "陈默推开档案室的门，昨天的卷宗还摊在桌上。\n"
    "他发现一枚戒指压在案件记录下面，来历不明，档案里没有登记。\n"
    "死者的邻居说三天前听到过争吵，可笔录上写的是当晚无人在家。\n"
    "刑警队里没人能解释这枚戒指为什么会出现在这里，线索对不上。\n"
    "陈默决定调查下去，嫌疑人交代的时间和监控完全不符，真相还埋着。\n"
) * 6  # 撑过 80 字的场景下限，并给词频统计足够密度


class _P:
    def __init__(self, text):
        self.normalized_text = text
        self.raw_text = text


def test_chapter_text_from_paragraphs_joins_with_newline():
    paras = [_P("第一段。"), _P("第二段。")]
    assert chapter_text_from_paragraphs(paras) == "第一段。\n第二段。"


def test_guess_genre_detects_xuanyi():
    slug, conf = guess_genre(_XUANYI_CHAPTER * 5)
    assert slug == "xuanyi"
    assert conf > 0.3


def test_extract_chapter_materials_produces_full_drafts():
    scenes, skipped = extract_chapter_materials(
        _XUANYI_CHAPTER, genre_slug="xuanyi", chapter_seq=1, total_chapters=10)
    assert skipped == 0
    assert scenes, "合成章节应切出至少一个场景"
    drafts = [d for sc in scenes for d in sc.drafts]
    assert drafts, "悬疑信号词应产出资料"
    for d in drafts:
        # 每条资料五件套齐全，且示例不是原文拼接（不含源文本的人名）
        assert d.title and d.concise_example and d.core_pattern
        assert d.mechanism and d.suspense_question
        assert "陈默" not in d.concise_example
        assert "陈默" not in d.core_pattern
    # 开篇章节的 stage_hint
    assert all(d.applicable_stage == "开篇" for d in drafts)


def test_short_scene_is_skipped_not_analyzed():
    scenes, skipped = extract_chapter_materials(
        "太短。", genre_slug="xuanyi", chapter_seq=1, total_chapters=1)
    assert scenes == []
    assert skipped >= 0  # <80 字的块要么切不出场景要么被跳过，绝不产出资料


def test_book_level_skips_duplicate_chapters():
    chapters = [("第一章", _XUANYI_CHAPTER),
                ("第二章", _XUANYI_CHAPTER),  # 正文与第一章完全相同
                ("第三章", _XUANYI_CHAPTER.replace("戒指", "怀表"))]
    result = extract_book_materials(chapters, genre_slug="xuanyi")
    assert result.duplicate_chapters == 1
    analyzed_seqs = {sc.chapter_seq for sc in result.scenes}
    assert 2 not in analyzed_seqs
    assert {1, 3} <= analyzed_seqs


def test_book_level_guesses_genre_when_absent():
    result = extract_book_materials([("第一章", _XUANYI_CHAPTER * 5)])
    assert result.genre_slug == "xuanyi"
    assert result.drafts


def test_chapter_end_hook_only_on_last_scene():
    # 3 个场景以上的长章：钩子类资料只允许出现在最后一个场景
    long_chapter = _XUANYI_CHAPTER * 4
    scenes, _ = extract_chapter_materials(
        long_chapter, genre_slug="xuanyi", chapter_seq=1, total_chapters=1)
    assert len(scenes) >= 2
    for sc in scenes[:-1]:
        assert all(d.material_type != "钩子" for d in sc.drafts)
