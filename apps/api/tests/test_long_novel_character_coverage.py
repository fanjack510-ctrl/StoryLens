"""人物档案的身份与结局：抽取层一直在产出原料，此前一路被丢掉。"""
from app.narrative_core.long_novel.adapter import build_characters_section


def _entity(name: str, centrality: int = 10) -> dict:
    return {
        "entity_key": f"E-{name}",
        "display_surface_norm": name,
        "aliases": [],
        "centrality": centrality,
        "evidence_ids": ["EVD-1"],
    }


def test_identity_comes_from_role_hint_and_ending_from_the_last_state_change():
    facts = {
        "路星辞": {
            "key_events": [(3, "打球")],
            "goals": [],
            "choices": [],
            "to_lead": [],
            "evidence": ["EVD-1"],
            "roles": ["十班班长", "班长", "十班班长"],
            "states": [(5, "冷淡", "开始在意"), (60, "开始在意", "公开在一起")],
        },
    }
    section = build_characters_section(
        entities=[_entity("路星辞")], character_facts=facts,
    )
    row = section["major_characters"][0]
    # 多数票：同一个人在不同块里被写成「班长」和「十班班长」，取写得最完整的那个。
    assert row["identity"] == "十班班长"
    # 结局＝最后一次状态变化的落点，按章排序，不是抽取顺序。
    assert row["ending"] == "公开在一起"


def test_a_person_the_book_never_describes_keeps_both_fields_empty():
    """没写明就留空——这两栏此前是写死的空字符串，现在是「真的没有」。"""
    facts = {
        "黑皮": {
            "key_events": [], "goals": [], "choices": [], "to_lead": [],
            "evidence": [], "roles": [], "states": [],
        },
    }
    section = build_characters_section(entities=[_entity("黑皮")], character_facts=facts)
    row = section["major_characters"][0]
    assert row["identity"] == ""
    assert row["ending"] == ""


def test_facts_without_the_new_keys_do_not_break_an_older_asset():
    """旧的块资产里没有 roles / states 两把钥匙，不能因此炸掉整张人物页。"""
    facts = {"某人": {"key_events": [], "goals": [], "choices": [], "to_lead": [], "evidence": []}}
    section = build_characters_section(entities=[_entity("某人")], character_facts=facts)
    assert section["major_characters"][0]["identity"] == ""


def test_the_function_column_answers_a_question_a_supporting_character_can_answer():
    """目标、抉择、结局是主角才有的；「担什么」配角答得上来。"""
    facts = {
        "宋意": {
            "key_events": [(3, "戳破秘密")], "goals": [], "choices": [], "to_lead": [],
            "evidence": [], "roles": ["同班同学"], "states": [],
        },
    }
    section = build_characters_section(
        entities=[_entity("宋意")],
        character_facts=facts,
        cast_functions=[{"name": "宋意", "function": "把主角瞒着的事说破，逼他面对"}],
    )
    row = section["major_characters"][0]
    assert row["function"] == "把主角瞒着的事说破，逼他面对"
    # 目标一栏仍然空着——书里没写就是没写，这一栏不去替它编一个。
    assert row["initial_goal"] == ""


def test_a_name_not_in_the_cast_table_gets_no_function_rather_than_a_wrong_one():
    facts = {"路人": {"key_events": [], "goals": [], "choices": [], "to_lead": [],
                     "evidence": [], "roles": [], "states": []}}
    section = build_characters_section(
        entities=[_entity("路人")],
        character_facts=facts,
        cast_functions=[{"name": "另一个人", "function": "推动高潮"}],
    )
    assert section["major_characters"][0]["function"] == ""


def test_an_older_document_without_the_column_still_validates():
    """function 有默认值，这次改动之前存下来的文档不该因此校验失败。"""
    from app.narrative_core.whole_book_v2.contracts import MajorCharacter

    row = MajorCharacter(
        character_id="E-1", name="甲", aliases=[], importance=0.5, identity="", role="supporting",
        initial_goal="", final_goal="", character_arc="", key_events=[],
        relationship_to_protagonist="", relationship_changes=[], major_choice="",
        cost_paid=[], gain_received=[], ending="", evidence=[],
    )
    assert row.function == ""
