from pathlib import Path
import json
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

from app.narrative_core.material_lab.structured_farming_corpus import (
    parse_structured_farming_directory,
)
from app.narrative_core.material_lab.service import _legacy_material_dict


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _paragraph(text: str, style: str = "") -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>'


def _write_docx(path: Path) -> None:
    paragraphs = [
        _paragraph("古代种田文写作素材库", "Title"),
        _paragraph("第一册｜农家人物 · 村庄结构"),
        _paragraph("01 农家人物", "Heading1"),
        _paragraph("01 当家主妇", "Heading3"),
        _paragraph("适用：宋—清｜通用"),
        _paragraph("生活依据：管理钥匙、粮瓮和人情支出，最清楚家中实际余粮。"),
        _paragraph("可直接写：客人登门时，她先摸粮瓮再决定是否留饭。"),
        _paragraph("避坑：不能把她写成只做饭带娃。"),
        _paragraph("依据方向：地方志"),
        _paragraph("25 种田剧情事件库", "Heading1"),
        _paragraph("01 暴雨冲田", "Heading3"),
        _paragraph("适用：通用"),
        _paragraph("生活依据：这是一个剧情事件模板，不作为纯知识。"),
        _paragraph("可直接写：人物在暴雨中抢收。"),
        _paragraph("避坑：不能只写结果。"),
        _paragraph("依据方向：写作案例"),
    ]
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>{"".join(paragraphs)}</w:body></w:document>'
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document)


def test_structured_farming_docx_is_validated_and_plot_templates_are_skipped(
    tmp_path: Path,
) -> None:
    _write_docx(tmp_path / "第一册.docx")

    corpus = parse_structured_farming_directory(tmp_path)

    assert corpus.source_count == 1
    assert corpus.excluded_count == 1
    assert len(corpus.entries) == 1
    item = corpus.entries[0]
    assert item.title == "当家主妇"
    assert item.category_key == "daily"
    assert item.subcategory_key == "household"
    assert item.evidence_prefix.startswith("D-")


def test_structured_farming_card_is_presented_as_reference_not_novel() -> None:
    row = SimpleNamespace(
        source_pattern_id="corpus:structured-farming:S01:abc",
        source_evidence_ids_json=json.dumps({
            "pipeline_version": "structured-farming-docx-v1",
            "evidence": [{
                "evidence_id": "D-1234567890-S01-I01-BASIS",
                "chapter_index": 1,
                "chapter_title": "农家人物",
                "paragraph_index": 20,
                "text": "生活依据：当家人掌握家庭余粮。",
            }],
        }, ensure_ascii=False),
        source_material_id="m1",
        source_book_title="古代种田文写作素材库·第一册",
        genre_slug="zhongtian",
        material_type="knowledge",
        category_key="daily",
        category_label="日常细节",
        subcategory_key="household",
        subcategory_label="家庭分工",
        title="当家主妇",
        concise_example="掌握家庭余粮。",
        core_pattern="",
        mechanism="",
        suspense_question="",
        applicable_stage="全书",
        applicable_scene="农家人物",
        emotion="种田",
        tags_json="[]",
        quality_score=96,
        confidence=0.96,
        is_primary_variant=1,
    )

    card = _legacy_material_dict(row)

    assert card["source_material_kind"] == "reference"
    assert card["knowledge_role"] == "domain_reference"
    assert card["knowledge_role_label"] == "种田资料知识"
    assert card["verification_label"] == "本地写作资料 · 农家人物 · 三段资料依据已核对"
