# -*- coding: utf-8 -*-
"""Phase 1D-B1 certification chapter text fixtures (offline, no copyright downloads)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CertChapterSpec:
    fixture_id: str
    book_key: str
    book_title: str
    chapter_title: str
    length_band: str  # short|medium|long|near_limit
    narrative_tags: tuple[str, ...]
    structure_tags: tuple[str, ...]
    text: str


def _paras(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def _repeat_block(seed: str, times: int) -> list[str]:
    out: list[str] = []
    for i in range(1, times + 1):
        out.append(f"{seed}（第{i}段）风穿过巷口，石板反光，远处鼓点忽然密了一拍。")
        out.append(f"{seed}（对白{i}）「你听见了吗？」她压低声音，「灯灭之前，门后有人呼吸。」")
        out.append(f"{seed}（动作{i}）他抬脚跨过门槛，掌心按住刀柄，目光扫过梁上尘土。")
    return out


def build_cert_chapter_specs() -> list[CertChapterSpec]:
    """3 books × 4 chapters = 12 fixtures covering length/narrative/structure matrix."""
    specs: list[CertChapterSpec] = []

    # Book A: 戏影（悬疑/对话）
    specs.append(
        CertChapterSpec(
            "A1-short-dialogue",
            "book_a",
            "戏影",
            "第1章 门缝",
            "short",
            ("dialogue_dense", "suspense_reveal"),
            ("few_scenes", "has_hook_no_payoff", "evidence_sparse"),
            _paras(
                "雨停了。",
                "「别开。」她说。",
                "门缝里有一只眼睛。",
                "他后退半步。",
                "灯灭了。",
                "天亮后，门板上只剩一道湿痕。",
                "她蹲下，用指尖刮下黑色粉末。",
                "「这不是雨水。」她说。",
                "他们下到巷口茶摊。",
                "老板指着对街：「昨夜有人在那站了很久。」",
                "他握紧伞柄，没有回答。",
            ),
        )
    )
    specs.append(
        CertChapterSpec(
            "A2-medium-action",
            "book_a",
            "戏影",
            "第2章 追巷",
            "medium",
            ("action_dense", "emotion_push"),
            ("has_question_chain", "has_payoff", "evidence_rich"),
            _paras(
                "巷口忽然挤满脚步。",
                "他撞开摊车，水果滚进水沟。",
                "「站住！」身后有人喊。",
                "她拉住他的袖口，把他拽进更窄的侧门。",
                "侧门后是一截黑楼梯，木板在脚下呻吟。",
                "他听见自己的心跳盖过雨声。",
                "「上面有路。」她喘着说。",
                "屋顶瓦片滑落，碎响惊起一群麻雀。",
                "他们翻过屋脊，看见河对岸的红灯一闪一闪。",
                "红灯灭时，追兵的脚步也停了。",
                "「他们在等什么？」他问。",
                "她没有回答，只把一张湿纸塞进他掌心。",
            ),
        )
    )
    long_a = _repeat_block("戏影长章", 28)
    specs.append(
        CertChapterSpec(
            "A3-long-suspense",
            "book_a",
            "戏影",
            "第3章 灯塔回声——这是一个故意写得很长的章节标题用于认证模板不因标题分叉",
            "long",
            ("suspense_reveal", "hook_dense", "description_dense"),
            ("many_scenes", "many_phases", "long_title", "long_phase_titles"),
            _paras(*long_a),
        )
    )
    near_a = _repeat_block("戏影近上限", 55)
    specs.append(
        CertChapterSpec(
            "A4-near-limit-info",
            "book_a",
            "戏影",
            "第4章 档案柜",
            "near_limit",
            ("info_explain_dense", "description_dense"),
            ("many_scenes", "no_question_chain", "evidence_rich"),
            _paras(*near_a),
        )
    )

    # Book B: 镜河（描写/情绪）
    specs.append(
        CertChapterSpec(
            "B1-short-emotion",
            "book_b",
            "镜河",
            "序章 裂",
            "short",
            ("emotion_push",),
            ("few_scenes", "few_phases", "no_question_chain"),
            _paras(
                "河面像一面碎掉的镜子。",
                "她蹲下，手指碰到冰凉的水。",
                "水纹散开，又合上。",
            ),
        )
    )
    specs.append(
        CertChapterSpec(
            "B2-medium-description",
            "book_b",
            "镜河",
            "第1章 芦苇",
            "medium",
            ("description_dense", "emotion_push"),
            ("has_question_chain", "has_hook_no_payoff", "evidence_sparse"),
            _paras(
                "芦苇高过肩头，风一过就沙沙作响。",
                "远处有人唱歌，词听不清。",
                "她沿着泥径走，靴底吸住软泥。",
                "天色忽然低下来，像有人把灯罩压紧。",
                "「你还记得那晚吗？」身后传来熟悉的声音。",
                "她没有回头，只把斗笠压得更低。",
                "芦苇丛里闪过一件白衣，很快又不见了。",
                "河对岸的灯火一盏一盏亮起，像在排队。",
            ),
        )
    )
    long_b = _repeat_block("镜河长章", 30)
    specs.append(
        CertChapterSpec(
            "B3-long-payoff",
            "book_b",
            "镜河",
            "第2章 旧桥",
            "long",
            ("payoff_dense", "dialogue_dense"),
            ("many_phases", "has_payoff", "evidence_rich"),
            _paras(*long_b),
        )
    )
    specs.append(
        CertChapterSpec(
            "B4-medium-hook",
            "book_b",
            "镜河",
            "第3章 夜航",
            "medium",
            ("hook_dense", "action_dense"),
            ("has_hook_no_payoff", "few_phases"),
            _paras(
                "船缆松开时，河面忽然亮起一串浮灯。",
                "「谁放的？」船夫低声问。",
                "没有人回答。",
                "浮灯排成一条指向下游的箭头。",
                "她握紧符袋，掌心出汗。",
                "船身一震，船底蹭到了什么东西。",
                "「别停。」她说。",
                "船夫点头，却把篙插得更深。",
                "下游的雾里，有人影站着，像在等船。",
            ),
        )
    )

    # Book C: 城轨（信息/动作）
    specs.append(
        CertChapterSpec(
            "C1-short-info",
            "book_c",
            "城轨",
            "第1章 时刻表",
            "short",
            ("info_explain_dense",),
            ("few_scenes", "evidence_sparse"),
            _paras(
                "末班车延误十二分钟。",
                "广播重复了三遍同一句。",
                "他核对纸质时刻表，发现第7行被改过。",
                "改动处用铅笔描了新的到站时间。",
                "「谁改的？」值班员问。",
                "没有人承认。",
                "列车进站后，车门只开了一半。",
                "他挤进去，看见座椅上压着一张折叠时刻表。",
                "背面写着：别在第三站下车。",
            ),
        )
    )
    specs.append(
        CertChapterSpec(
            "C2-medium-dialogue",
            "book_c",
            "城轨",
            "第2章 换乘",
            "medium",
            ("dialogue_dense", "info_explain_dense"),
            ("has_question_chain", "has_payoff"),
            _paras(
                "「你确定是二号线？」她问。",
                "「时刻表写的是二号线，但站台灯是绿的。」",
                "绿灯表示临时绕行，他解释。",
                "她皱眉：「谁有权限改纸质表？」",
                "他们挤进车厢，门缝夹住一张折叠地图。",
                "地图背面写着：别在第三站下车。",
                "第三站到了，广播却报了另一站名。",
                "她拉住他：「我们按纸走，还是按广播走？」",
            ),
        )
    )
    long_c = _repeat_block("城轨长章", 32)
    specs.append(
        CertChapterSpec(
            "C3-long-action",
            "book_c",
            "城轨",
            "第3章 封站",
            "long",
            ("action_dense", "suspense_reveal"),
            ("many_scenes", "many_phases", "evidence_rich"),
            _paras(*long_c),
        )
    )
    near_c = _repeat_block("城轨近上限", 52)
    specs.append(
        CertChapterSpec(
            "C4-near-limit-mixed",
            "book_c",
            "城轨",
            "第4章 环形线",
            "near_limit",
            ("description_dense", "hook_dense", "payoff_dense"),
            ("many_scenes", "long_phase_titles", "evidence_rich"),
            _paras(*near_c),
        )
    )

    assert len(specs) == 12
    assert len({s.book_key for s in specs}) == 3
    return specs
