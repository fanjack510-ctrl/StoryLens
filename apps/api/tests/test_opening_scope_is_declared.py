"""开篇拆解不能把「只读了开篇」说成「书就这么长」。

扫榜要的是一次只读前几章的便宜拆解。做法是给运行加 `chapter_limit`，让 `load_chapters`
在发给模型之前就把后面的章节挡掉——省下的是用户付给模型服务商的真钱（实测：《余罪》整本
¥5.03 / 90 分钟，前 5 章 ¥0.204 / 98 秒）。

但第一版实测出来的文档说：这本书共 5 章，已分析 5 章，缺失 0 章。书有 542 章。

这和之前那次「丢了的章节让书自己变短」是同一个错误：分子分母一起缩水，覆盖率于是永远
100%。区别只在于这次章节不是丢的，是有意不读的——而这恰恰要求文档说得更清楚，不是更含糊：
读者要能一眼分出「引擎出错了」和「引擎按我要求只读了开篇」，因为这两件事该做的处理正好相反。

所以这里钉三件事：书的长度按书算、有意跳过的章不算作丢失、文档自己声明这是一次开篇阅读。
"""

from __future__ import annotations

import pytest

from app.narrative_core.whole_book_v2.contracts import WholeBookAnalysisV2

from tests.test_long_novel_document_sections import (  # noqa: F401 — 复用同一套假供应商装置
    COSTS,
    PARAGRAPHS,
    _assessment,
    _FakeProvider,
    _final,
    _stage,
    _topic,
)

#: 只读前 6 章，而「书」有 60 章——比例接近真实的开篇拆解（5/542）。
READ = 6
BOOK = 60


@pytest.fixture(scope="module")
def opening_document() -> dict:
    from app.narrative_core.long_novel.budget import joint_resolve
    from app.narrative_core.long_novel.contracts.density import profile
    from app.narrative_core.long_novel.extractor import (
        BlockExtractor,
        SourceChapter,
        SourceParagraph,
    )
    from app.narrative_core.long_novel.orchestrator import RunCoordinator
    from app.narrative_core.long_novel.planner import BlockPlanner, PlannedChapter
    from app.narrative_core.long_novel.prompts import prompt_template_hash

    resolution = joint_resolve(
        context_window=128_000,
        provider_max_output_tokens=32_768,
        provider_max_output_tokens_source="probed",
        costs=COSTS,
        mean_chapter_tokens=4_041,
        mean_paragraphs_per_chapter=PARAGRAPHS,
    )
    prof = profile(resolution.density_profile)
    # 计划里只有读到的那几章——这正是真实路径：limit 在 load_chapters 就生效，
    # 后面的章节从来没进过计划。
    plan = BlockPlanner(
        profile=prof,
        output_budget=resolution.output_budget,
        context_window=128_000,
        costs=COSTS,
    ).plan([PlannedChapter(i, 10_000 + i, "h%d" % i, 4_041, PARAGRAPHS) for i in range(1, READ + 1)])
    sources = {
        i: SourceChapter(
            chapter_order=i,
            source_chapter_id=10_000 + i,
            content_hash="h%d" % i,
            snapshot_chapter_id=10_000 + i,
            paragraphs=[
                SourceParagraph(j, "第%d章第%d段，老王走进房间。" % (i, j), "c%dp%d" % (i, j))
                for j in range(1, PARAGRAPHS + 1)
            ],
        )
        for i in range(1, READ + 1)
    }
    coordinator = RunCoordinator(
        extractor=BlockExtractor(
            provider=_FakeProvider(),
            profile=prof,
            output_budget=resolution.output_budget,
            prompt_template_hash=prompt_template_hash(prof),
        ),
        profile=prof,
        stage_interpreter=_stage,
        topic_synthesizer=_topic,
        assessor=_assessment,
        finaliser=_final,
    )
    report = coordinator.run(
        plan=plan,
        chapters_by_order=sources,
        character_count=1_000_000,
        book_id=1,
        snapshot_id=1,
        revision_hash="rev",
        title="测试书",
        run_id=1,
        provider_name="fake",
        model_name="fake",
        book_chapters_total=BOOK,
    )
    assert not report.blocks_failed, report.blocks_failed
    return report.document


def test_the_document_still_satisfies_the_product_contract(opening_document):
    WholeBookAnalysisV2.model_validate(opening_document)


def test_the_book_keeps_its_real_length(opening_document):
    """书是 60 章。只读了 6 章，不会让另外 54 章不存在。"""
    assert opening_document["book_metadata"]["chapter_count"] == BOOK
    assert opening_document["analysis_metadata"]["coverage"]["chapters_total"] == BOOK


def test_skipped_chapters_are_not_reported_as_lost(opening_document):
    """有意没读的章不是「丢了的章」。

    把它们塞进 chapters_missing，一次完全正常的开篇拆解就会显示丢失 54 章——
    用户会去重跑一次已经成功的分析。
    """
    assert opening_document["analysis_metadata"]["coverage"]["chapters_missing"] == []


def test_the_document_says_it_only_read_the_opening(opening_document):
    """文档自己声明范围。

    没有这句声明，界面只能拿 6/60 去算，然后把一次成功的开篇拆解显示成 10% 覆盖率的残缺结果。
    """
    cov = opening_document["analysis_metadata"]["coverage"]
    assert cov["scope_kind"] == "opening"
    assert cov["scope_chapters"] == READ
    assert cov["chapters_analysed"] == READ


def test_a_full_run_is_not_labelled_an_opening_run():
    """整本运行必须仍然报 full——否则每一份全书报告都会挂上「只读了开篇」的告示。"""
    from app.narrative_core.whole_book_v2.contracts import CoverageReport

    cov = CoverageReport()
    assert cov.scope_kind == "full"
