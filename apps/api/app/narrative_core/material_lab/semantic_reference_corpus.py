"""Model-backed curation for the external fiction reference corpus.

The deterministic scanner answers *which books may be used*.  This module
answers the much harder question: *what reusable writing knowledge is actually
present in a small, cited set of passages*.  It deliberately keeps candidate
discovery separate from semantic synthesis so that every accepted statement can
be traced back to a stable source paragraph id.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Iterable, Literal

from pydantic import BaseModel, Field, model_validator

from .genre_templates import TEMPLATES


PIPELINE_VERSION = "semantic-reference-v1"
SUSPENSE_CATEGORY_KEYS = (
    "opening_anomaly",
    "clue_object",
    "clue_behavior",
    "person_doubt",
    "env_anomaly",
    "time_memory",
)
FARMING_CATEGORY_KEYS = (
    "skill",
    "business",
    "daily",
    "weather_season",
    "crop_cultivation",
    "soil_water",
    "livestock_processing",
)
ANCIENT_ROMANCE_CATEGORY_KEYS = (
    "status",
    "clan",
    "marriage",
    "court",
    "palace",
    "household_strife",
)
URBAN_KNOWLEDGE_CATEGORY_KEYS = (
    "workplace_knowledge",
    "business_knowledge",
    "finance_knowledge",
    "legal_knowledge",
    "media_knowledge",
    "urban_life",
)
SCIENCE_FICTION_CATEGORY_KEYS = (
    "premise",
    "tech_rule",
    "society",
    "institution",
    "ethics",
    "cost",
    "disaster",
    "consequence",
)
DISASTER_FICTION_CATEGORY_KEYS = (
    "cataclysm",
    "resource",
    "survival_practice",
    "base",
    "logistics",
    "health",
    "ecology",
    "ability",
    "order",
    "threat_rule",
)
FANTASY_KNOWLEDGE_CATEGORY_KEYS = (
    "worldview",
    "power_system",
    "rank_system",
    "bloodline",
    "resource",
    "craft_economy",
    "faction",
    "society_rule",
    "map",
    "cost_rule",
)
XIANXIA_KNOWLEDGE_CATEGORY_KEYS = (
    "dao_path",
    "power_system",
    "sect",
    "resource",
    "alchemy_craft",
    "secret_realm",
    "exchange_economy",
    "karma",
    "spiritual_ecology",
    "restriction_cost",
)
CONTEMPORARY_LIFE_CATEGORY_KEYS = (
    "family_system",
    "marriage_life",
    "era_life",
    "livelihood",
    "work_social",
    "public_service",
)
INFINITE_FLOW_CATEGORY_KEYS = (
    "instance",
    "rule",
    "info_clue",
    "task",
    "death_condition",
    "solution",
    "team",
    "reward",
    "resource_exchange",
    "transition",
)
SEMANTIC_CATEGORY_KEYS: dict[str, tuple[str, ...]] = {
    "xuanyi": SUSPENSE_CATEGORY_KEYS,
    "zhongtian": FARMING_CATEGORY_KEYS,
    "guyan": ANCIENT_ROMANCE_CATEGORY_KEYS,
    "dushi": URBAN_KNOWLEDGE_CATEGORY_KEYS,
    "kehuan": SCIENCE_FICTION_CATEGORY_KEYS,
    "moshi": DISASTER_FICTION_CATEGORY_KEYS,
    "xuanhuan": FANTASY_KNOWLEDGE_CATEGORY_KEYS,
    "xianxia": XIANXIA_KNOWLEDGE_CATEGORY_KEYS,
    "xianyan": CONTEMPORARY_LIFE_CATEGORY_KEYS,
    "wuxianliu": INFINITE_FLOW_CATEGORY_KEYS,
}
_BANNED_EMPTY_PHRASES = (
    "处境随之改变",
    "限制了后续可以发生什么",
    "限制了接下来可以发生什么",
    "在现场被明确下来",
    "出现一处人的定义",
    "改变了接下来能做的事",
    "某种异常",
    "某个事情",
)
_FARMING_OFF_TOPIC_PHRASES = (
    "抓人抵债",
    "拒收谢银",
    "拒收银",
    "袭击现场",
    "枭首",
    "疫情暴发",
    "救治更多病人",
)
_ANCIENT_OFF_TOPIC_PHRASES = (
    "争宠靠家族",
    "捡剩饭",
    "向正妃表忠",
    "唯命是从",
    "揣摩主母心思",
)
_URBAN_OFF_TOPIC_PHRASES = (
    "打脸",
    "震惊众人",
    "隐藏身份",
    "抱得美人归",
    "追求女主",
    "富二代欺负",
    "靠关系摆平",
    "地下商界",
    "监商",
    "金卡可作应急贷款",
    "合同一旦签字即生效",
    "律师休假",
    "分一杯羹",
    "五倍加班费",
    "慈善晚会每五年",
    "工作与家庭平衡",
    "高级会所保密",
    "警方调查与血液检验",
    "股东身份与媒体公关",
)
_SCIFI_OFF_TOPIC_PHRASES = (
    "主角击败",
    "敌人来袭",
    "获得机甲",
    "身份暴露",
    "比赛获胜",
    "实力提升",
    "遭到追杀",
    "战争爆发推动剧情",
    "人物陷入危机",
    "高空无人机遭遇",
    "全服通报",
    "任务期间传送阵",
    "收到外星样本后震惊",
    "万生丑果",
    "三千米高树",
    "系统无医疗能力",
    "本我宇宙",
    "S级评定",
    "皮尔斯符号",
)
_DISASTER_OFF_TOPIC_PHRASES = (
    "主角击杀",
    "击败尸群",
    "获得异能",
    "实力提升",
    "系统奖励",
    "英雄救美",
    "队友背叛",
    "人物陷入危机",
    "成功逃脱",
    "报仇雪恨",
    "等级配给差异",
    "夜间外出猎杀",
    "晶石消耗",
    "强行征用或抢夺",
    "三个仓库的罐头",
    "研究丧尸的弱点",
    "被击飞的丧尸",
    "枪托不如板砖",
)
_FANTASY_OFF_TOPIC_PHRASES = (
    "越级击败",
    "震惊全场",
    "当众打脸",
    "获得奇遇",
    "主角突破",
    "复仇雪耻",
    "敌人追杀",
    "美女倾心",
    "战斗胜利",
    "月光血脉的月夜增幅",
    "瞬气丹的昂贵与战略价值",
    "龙凰血脉作为调和物",
    "炼器火源三法",
    "生命之泉分配困境",
)
_XIANXIA_OFF_TOPIC_PHRASES = (
    "主角筑基",
    "越阶杀敌",
    "夺得宝物",
    "师兄嫉妒",
    "宗门大比获胜",
    "仇家追杀",
    "奇遇突破",
    "美人相救",
    "道心立誓与外物取舍",
    "降伏道法为主",
    "因果混乱难驱逐",
)
_CONTEMPORARY_OFF_TOPIC_PHRASES = (
    "霸总强吻",
    "追妻火葬场",
    "女配被打脸",
    "男主吃醋",
    "误会分手",
    "重生复仇",
    "婆婆刁难",
    "全家震惊",
    "抱得美人归",
    "年画宣传组",
    "家庭存折暗格",
    "单位内部派系斗争",
    "不扣子女工资被视为难得",
    "粮油关系转移证明",
    "存折被抢",
    "偷户口本登记结婚",
    "知青未领证",
    "动迁款争夺",
)
_INFINITE_FLOW_OFF_TOPIC_PHRASES = (
    "单纯升级",
    "战斗力提升",
    "抽到神装",
    "击杀Boss",
    "队友背叛",
    "主角碾压",
    "奖励丰厚",
    "进入新世界冒险",
    "普通战利品分配",
    "普通魔法能力限制",
)


class EvidenceCandidate(BaseModel):
    evidence_id: str = Field(min_length=12, max_length=96)
    source_title: str = Field(min_length=1, max_length=255)
    chapter_index: int = Field(ge=1)
    chapter_title: str = Field(default="", max_length=500)
    paragraph_index: int = Field(ge=1)
    position: Literal["opening", "early", "middle", "late"]
    suggested_category: str
    text: str = Field(min_length=20, max_length=650)


class SemanticMaterialDraft(BaseModel):
    draft_id: str = Field(min_length=1, max_length=48)
    evidence_ids: list[str] = Field(min_length=1, max_length=3)
    category_key: str
    subcategory_key: str
    title: str = Field(min_length=2, max_length=40)
    creative_material: str = Field(min_length=18, max_length=140)
    reusable_pattern: str = Field(min_length=8, max_length=120)
    mechanism: str = Field(min_length=6, max_length=100)
    suspense_question: str = Field(default="", max_length=140)
    applicable_stage: str = Field(default="全书", max_length=32)
    tags: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def reject_empty_templates(self) -> "SemanticMaterialDraft":
        joined = " ".join(
            (self.title, self.creative_material, self.reusable_pattern, self.mechanism)
        )
        for phrase in _BANNED_EMPTY_PHRASES:
            if phrase in joined:
                raise ValueError(f"empty template phrase: {phrase}")
        return self


class SemanticExtractionBatch(BaseModel):
    materials: list[SemanticMaterialDraft] = Field(default_factory=list, max_length=16)


class QualityScores(BaseModel):
    concreteness: int = Field(ge=1, le=5)
    reusability: int = Field(ge=1, le=5)
    information_gap: int = Field(ge=1, le=5)
    evidence_fidelity: int = Field(ge=1, le=5)
    expression_quality: int = Field(ge=1, le=5)


class ReviewedSemanticMaterial(SemanticMaterialDraft):
    scores: QualityScores


class SemanticReviewBatch(BaseModel):
    accepted: list[ReviewedSemanticMaterial] = Field(default_factory=list, max_length=48)
    rejected_draft_ids: list[str] = Field(default_factory=list)


class EvidenceAuditItem(BaseModel):
    draft_id: str = Field(min_length=1, max_length=48)
    evidence_ids: list[str] = Field(min_length=1, max_length=3)
    verdict: Literal["supported", "rewritten", "reject"]
    creative_material: str = Field(default="", max_length=140)
    unsupported_claims: list[str] = Field(default_factory=list, max_length=8)
    supporting_quotes: list[str] = Field(default_factory=list, max_length=8)


class EvidenceAuditBatch(BaseModel):
    items: list[EvidenceAuditItem] = Field(default_factory=list, max_length=48)


def _category_contract(genre_slug: str, keys: Iterable[str]) -> str:
    template = TEMPLATES[genre_slug]
    wanted = set(keys)
    rows: list[dict[str, object]] = []
    for category in template["categories"]:
        if category["key"] not in wanted:
            continue
        rows.append(
            {
                "category_key": category["key"],
                "category_label": category["label"],
                "stage": category["stage"],
                "subcategories": [
                    {"key": sub["key"], "label": sub["label"]}
                    for sub in category["subcategories"]
                ],
            }
        )
    return json.dumps(rows, ensure_ascii=False)


def build_extraction_prompt(
    *,
    source_title: str,
    candidates: list[EvidenceCandidate],
    genre_slug: str = "xuanyi",
    category_keys: tuple[str, ...] | None = None,
) -> str:
    evidence = [candidate.model_dump() for candidate in candidates]
    keys = category_keys or SEMANTIC_CATEGORY_KEYS[genre_slug]
    genre_label = TEMPLATES[genre_slug]["label"]
    if genre_slug == "zhongtian":
        target = "少量、可直接用于种田文创作的具体生产生活知识"
        standard = """- 像“连续阴雨后先疏沟排积水，再扶正倒伏秧苗，避免根部久泡腐烂”一样，包含对象、条件、做法和结果。
- 像“新收谷物必须摊薄晾透再入仓，带潮堆放会发热霉变”一样，脱离原书仍能用于安排可信的劳作情节。
- 这是小说创作参考，不是农业权威指南；不得把原文没有写出的温度、剂量、产量或科学因果补进去。
- 只收生产生活知识；纯债务冲突、拒收谢礼、刑侦还原、救治资源短缺等只有剧情功能的内容必须跳过。"""
        item_rule = "creative_material 必须是18—140字的完整知识卡，至少包含具体对象与做法、条件或结果；不得只概括角色做了农活。"
        fact_rule = "忠于证据中的生产关系，不得补造原文没有的温度、剂量、天数、产量、品种特性、科学原理或必然效果。"
        suspense_rule = "suspense_question 对种田知识可留空；mechanism 写清该知识在生产、经营或生活中的实际作用。"
        weak_strong = """- 弱：村民开始种地，日子慢慢变好。
- 强：稻种先浸水催芽，露白后再下秧田；干种直接撒入冷泥，出苗会慢且不齐。
- 弱：天气影响了庄稼。
- 强：谷物收割后遇连雨不能立刻入仓，要先摊开翻晾，否则内部返潮发热并生霉。"""
    elif genre_slug == "guyan":
        target = "少量、可直接用于古言创作的具体制度、礼俗与权力运行知识"
        standard = """- 像“主母交出库房钥匙和账册，才算正式移交中馈；只有口头吩咐不能调拨府中银米”一样，写清身份、凭据、权限与后果。
- 像“婚书由两家长辈落名后，退亲不再只是男女私事，还会牵动宗族名声与聘财返还”一样，脱离原书仍能支撑可信情节。
- 这是小说中的古代社会创作参考，不是历史法规考证；不得补造原文没有的朝代、品级、礼制步骤或法律效力。
- 只收制度、礼俗、资源、身份和权力规则；单纯争宠、吵架、爱恨或人物胜负必须跳过。"""
        item_rule = "creative_material 必须是18—140字的完整知识卡，至少写清身份/资源/凭据/程序中的两项及其实际后果；不得只概括谁陷害了谁。"
        fact_rule = "忠于证据中的社会关系，不得补造原文没有的品级、官职权限、婚俗步骤、宗族处罚、宫规或财产规则。"
        suspense_rule = "suspense_question 对制度礼俗知识可留空；mechanism 写清该规则如何约束身份、资源或行动。"
        weak_strong = """- 弱：嫡庶身份不同，人物受到压制。
- 强：庶女议亲须由嫡母出面，生母只能私下准备嫁妆，不能越过主母与媒人定下婚书。
- 弱：主母掌握家中权力。
- 强：主母以库房钥匙、账册和月例发放掌中馈；失去其中任何一项，都无法实际调动府中人财。"""
    elif genre_slug == "dushi":
        target = "少量、可直接用于都市文创作的具体职业与城市运行知识"
        standard = """- 像“经销商不是收到货才付款，而是按合同账期回款；账期拉长会让销量增长和现金短缺同时发生”一样，写清角色、流程、资源与后果。
- 像“艺人录完主打歌后还要排练舞台、拍摄物料并配合电视台打歌，发行不是把音源上传就结束”一样，脱离原书仍能支撑可信的职业情节。
- 这是小说中的都市职业创作参考，不是法律、医疗或投资建议；不得补造原文没有的法规条文、收益率、行业惯例或必然结果。
- 只收职业流程、商业交易、资金运作、法律程序、传媒生产和城市服务知识；纯恋爱、打脸、炫富、身份曝光或靠关系取胜必须跳过。"""
        item_rule = "creative_material 必须是18—140字的完整知识卡，至少写清角色/岗位、具体流程或凭据、资源变化或实际后果中的三项；不得只概括人物在公司里做了什么。"
        fact_rule = "忠于证据中的职业关系，不得补造原文没有的法律结论、财务比例、行业规则、合同效力、办事流程或专业术语。"
        suspense_rule = "suspense_question 对都市职业知识可留空；mechanism 写清流程、交易、岗位或资源规则在情节中的实际作用。"
        weak_strong = """- 弱：主角创业成功，公司越来越大。
- 强：新公司先用预付款覆盖首批生产成本，再以经销合同锁定区域渠道；客户回款前扩张越快，现金越紧张。
- 弱：偶像为新专辑努力训练。
- 强：新歌确定后，艺人先录音再练舞，宣传期还要连续参加打歌和采访；任何环节延期都会挤压正式发行排期。"""
    elif genre_slug == "kehuan":
        target = "少量、可直接用于科幻创作的具体设定规则与社会后果"
        standard = """- 像“机甲的护盾、导航和能量武器共用主电网；供电瘫痪后不是单项武器失灵，而是整套远程作战能力同时消失”一样，写清技术对象、运行条件、限制和后果。
- 像“天然食材短缺后，烹饪从家庭技能变成分级认证职业，考试与制服把稀缺知识转化为社会身份”一样，写清技术或资源变化如何进入制度和日常。
- 这是小说中的科幻设定参考，不是现实科学结论；不得补造原文没有的能源原理、性能参数、实验结果或技术必然性。
- 只收科学假设、技术规则、社会变化、制度机构、伦理问题、技术代价、灾难机制与连锁后果；纯战斗胜负、升级、追杀和角色危机必须跳过。"""
        item_rule = "creative_material 必须是18—140字的完整设定卡，至少写清技术/制度对象、触发条件或运行方式、限制或后果中的三项；不得只概括发生了战争或人物使用了高科技。"
        fact_rule = "忠于证据中的设定关系，不得补造原文没有的科学原理、能量来源、性能参数、制度权限、伦理结论或连锁后果。"
        suspense_rule = "suspense_question 对科幻知识可留空；mechanism 写清设定约束如何改变社会、行动边界或风险。"
        weak_strong = """- 弱：机甲断电后失去战斗力。
- 强：指挥机甲的护盾、卫星导航和激光武器共用供电系统；主电网瘫痪后只剩近身机械动作可用。
- 弱：未来人类吃营养剂。
- 强：新鲜食材短缺后，多数人依赖营养剂和预制餐；会处理天然食材的人须通过分级考试，烹饪因此成为稀缺职业。"""
    elif genre_slug == "moshi":
        target = "少量、可直接用于末世创作的具体生存规则与灾后运行知识"
        standard = """- 像“屋顶雨水先经过弃流段排掉最初污水，再进入有盖容器；饮用前仍需煮沸”一样，写清资源、操作条件、步骤和风险。
- 像“基地按人数登记口粮，外勤队出发时先领定额，返程后交回余量并更新库存”一样，写清末世环境中的后勤或秩序如何运行。
- 这是小说中的末世创作参考，不是现实灾害、医疗或公共安全指南；不得补造原文没有的剂量、有效期、感染概率或必然效果。
- 只收灾变机制、求生行动、物资后勤、医疗卫生、环境生态、据点设施、能力限制、威胁规律与新秩序；纯击杀、升级、系统奖励、逃跑成功和人物背叛必须跳过。"""
        item_rule = "creative_material 必须是18—140字的完整生存知识卡，至少写清对象/资源、操作或规则、适用条件、风险或后果中的三项；不得只概括人物搜物资或打丧尸。"
        fact_rule = "忠于证据中的生存关系，不得补造原文没有的医学结论、污染阈值、储存期限、感染概率、武器性能、资源数量或必然生存效果。"
        suspense_rule = "suspense_question 对末世知识可留空；mechanism 写清资源、环境、设施或秩序规则怎样约束生存。"
        weak_strong = """- 弱：幸存者找到物资，暂时安全下来。
- 强：仓库罐头按人数和天数盘点，先发临期品；开封后无法冷藏的食物必须当天分完，避免在营地腐坏。
- 弱：丧尸靠声音寻找人类。
- 强：感染体对持续金属撞击会集群靠近，短促单次声响只引起附近个体转向，因此诱导声源必须远离撤离路线。"""
    elif genre_slug == "xuanhuan":
        target = "少量、可直接用于玄幻创作的具体世界规则与资源制度"
        standard = """- 写清力量层级、修炼条件、血脉体质、资源炼制、组织准入、交易制度、秘境环境或使用代价怎样运转。
- 卡片必须包含规则对象、触发/获取方式、限制或后果；不能只是主角突破、越级胜利或得到奇遇。
- 这是小说设定参考，不是现实知识；不得补造原文没有的境界顺序、成功率、兑换比例、功法效果或必然因果。"""
        item_rule = "creative_material 必须是18—140字的完整玄幻规则卡，写清对象、条件/流程和限制/后果中的至少三项。"
        fact_rule = "不得把角色胜负、震惊反应、临时奇遇或升级结果包装成世界规则，也不得合并证据中无关的两套设定。"
        suspense_rule = "suspense_question 可留空；mechanism 写清该规则怎样约束资源、身份、修炼或行动。"
        weak_strong = """- 弱：主角服药后突破境界。
- 强：淬体药液只能在经脉承受范围内连续使用；超过次数会积累药毒，必须停用并等待排出后才能继续。
- 弱：宗门等级森严。
- 强：外门弟子以任务贡献兑换功法，达到定额并通过考核后才能进入内门，私下传授会同时处罚师徒。"""
    elif genre_slug == "xianxia":
        target = "少量、可直接用于仙侠创作的具体修行、宗门与灵物规则"
        standard = """- 写清境界道途、师承宗门、丹器符阵、坊市贡献、秘境灵脉、因果天劫和术法代价的运行条件。
- 每条要能脱离原书支撑新情节，不能只是夺宝、杀敌、宗门大比或一次突破。
- 这是小说设定参考；不得补造原文没有的丹方、火候、境界顺序、寿元数字、法宝能力或因果结论。"""
        item_rule = "creative_material 必须是18—140字的完整仙侠规则卡，至少写清修行对象、使用/获取条件和限制/代价。"
        fact_rule = "不得用常见修仙常识补齐原文，也不得把人物感悟、战斗获胜或获得宝物直接当知识卡。"
        suspense_rule = "suspense_question 可留空；mechanism 写清规则如何约束修行、师承、资源或因果。"
        weak_strong = """- 弱：修士服丹后法力大增。
- 强：补气丹只恢复法力，不修复受损经脉；连续服用会让药力淤积，疗伤仍须另用温养功法。
- 弱：宗门用贡献换资源。
- 强：弟子完成执事堂任务后登记贡献，丹药与洞府时限分别计价；未交接任务凭证不能兑换。"""
    elif genre_slug == "xianyan":
        target = "少量、可直接用于现言创作的具体家庭、婚姻与日常生活知识"
        standard = """- 写清家庭分工、共同财务、居住安排、年代票证与单位制度、住房生计、工作流动或公共办事的角色、凭据、流程和后果。
- 只收能支撑可信生活情节的具体关系与流程；强吻、吃醋、误会分手、婆媳吵架和重生复仇必须跳过。
- 这是小说生活素材，不是法律、医疗或公共政策指南；不得补造原文没有的法定效力、医疗结论、办事材料或年代制度。"""
        item_rule = "creative_material 必须是18—140字的完整生活知识卡，至少包含家庭/单位角色、资源或凭据、处理方式和实际后果中的三项。"
        fact_rule = "不得把情感输赢包装成生活知识，不得补造婚姻、户籍、随军、住房、教育或医疗程序。"
        suspense_rule = "suspense_question 可留空；mechanism 写清生活规则怎样约束家庭资源、居住、工作或公共服务。"
        weak_strong = """- 弱：婆婆不喜欢儿媳，家庭矛盾加深。
- 强：夫妻工资统一存入家庭存折，日常开支由记账者领取；未共同署名的一方无法直接支取大额存款。
- 弱：军属可以随军生活。
- 强：家属办理随军后迁入家属院，住房与津贴随军人岗位调整；未办手续前只能按探亲期限暂住。"""
    elif genre_slug == "wuxianliu":
        target = "少量、可直接用于无限流创作的具体副本规则、线索与结算机制"
        standard = """- 写清副本入口、明暗规则、任务目标、死亡条件、验证线索、队伍信息、积分道具和返回结算怎样互相约束。
- 规则必须能由证据直接核对，不能把普通系统升级、打怪爆装或进入新世界冒险冒充无限流机制。
- 不得补造原文没有的隐藏规则、死亡条件、积分价格、时间限制或通关结论。"""
        item_rule = "creative_material 必须是18—140字的完整副本规则卡，至少写清规则载体/任务、触发条件、验证方式或失败后果中的三项。"
        fact_rule = "普通升级奖励、战斗胜负、队友背叛和单次冒险不构成副本知识；证据不足时必须不返回。"
        suspense_rule = "suspense_question 可写玩家尚未确认的规则问题；mechanism 写清信息、任务、资源或死亡条件的约束关系。"
        weak_strong = """- 弱：玩家进入副本并完成任务。
- 强：入住须知禁止午夜后开门，但走廊广播要求十二点接受查房；玩家必须从房卡背面的入住日期判断哪条指令属于本轮。
- 弱：通关后获得积分。
- 强：副本按存活人数结算基础积分，未使用的绑定道具不可带出；额外线索只有提交原件才计入奖励。"""
    else:
        target = "少量、可直接用于创作的悬疑素材"
        standard = """- 像“死者口袋里装着一把不属于他的家门钥匙”一样，一句话就包含具体载体、异常关系和信息缺口。
- 像“报失踪者调档后发现，被找的人二十年前正是由他本人报的死亡”一样，脱离原书仍能成为新故事的开篇种子。
- 这是创作知识，不是剧情摘要、原文摘抄、人物小传或空泛评论。"""
        item_rule = "creative_material 必须是18—140字的完整创作种子，包含具体的人/物/场所与异常事实；不得只说“发生异常”“处境改变”。"
        fact_rule = "忠于证据中的事实关系，不得补造证据没有的尸体、凶手、血迹、身份或因果。"
        suspense_rule = "suspense_question 写出读者会追问什么；opening_anomaly 只能使用 position=opening 的证据。"
        weak_strong = """- 弱：现场出现了一个异常物件，人物处境发生变化。
- 强：寄给失踪者的空包裹连续送到其旧居，寄件人与签收人却都登记为失踪者本人。
- 弱：两份证词存在矛盾。
- 强：两名目击者对案发过程的描述完全一致，唯独都说出了警方从未公开的伤口位置。"""
    return f"""你是中文小说创作资料库的资深编辑。请从给定原文证据中提炼{target}。

目标标准：
{standard}

硬性要求：
1. {item_rule}
2. {fact_rule}
3. 把原书专名泛化成角色或职业（如“调查员”“死者家属”），使素材能迁移到新作品；但不要把关键事实泛化掉。
4. 每条只表达一个核心机制；不同条目不得套用同一句式。
5. evidence_ids 只能引用下方真实编号，引用1—3条；{suspense_rule}
6. title 是短而具体的内容名，不得简单重复“分类·子分类”。
7. 从明显可用的证据中返回6—10条；单条证据不合格可以跳过，但不得因为需要泛化就返回空数组。

表达标尺（只学结构，不得照抄）：
{weak_strong}

题材：{genre_label}
允许分类：{_category_contract(genre_slug, keys)}

来源书名仅用于核对：{source_title}
候选证据：
{json.dumps(evidence, ensure_ascii=False)}

严格按下面字段返回 JSON，不得改名、缺字段或另加顶层键：
{{
  "materials": [
    {{
      "draft_id": "d1",
      "evidence_ids": ["真实证据编号"],
      "category_key": "允许分类中的key",
      "subcategory_key": "该分类下的key",
      "title": "具体短标题",
      "creative_material": "具体创作种子",
      "reusable_pattern": "可复用的事实关系",
      "mechanism": "为什么产生悬念",
      "suspense_question": "读者会追问什么",
      "applicable_stage": "开篇/前段/中段/后段/全书",
      "tags": ["标签"]
    }}
  ]
}}
不得使用 creative_materials 等其他字段名。"""


def build_review_prompt(
    *,
    drafts: list[SemanticMaterialDraft],
    evidence_by_id: dict[str, EvidenceCandidate],
    genre_slug: str = "xuanyi",
) -> str:
    evidence_ids = {eid for draft in drafts for eid in draft.evidence_ids}
    evidence = [
        evidence_by_id[eid].model_dump()
        for eid in sorted(evidence_ids)
        if eid in evidence_by_id
    ]
    genre_label = TEMPLATES[genre_slug]["label"]
    score_label = (
        "信息完整度"
        if genre_slug in {
            "zhongtian", "guyan", "dushi", "kehuan", "moshi",
            "xuanhuan", "xianxia", "xianyan", "wuxianliu",
        }
        else "信息缺口"
    )
    if genre_slug == "zhongtian":
        genre_rule = "种田知识必须写清对象、做法/条件与结果，不得把小说描述冒充已经外部核验的农业结论；"
    elif genre_slug == "guyan":
        genre_rule = "古言知识必须写清身份、凭据、程序、资源或后果，不得把争宠吵架和人物输赢包装成制度；"
    elif genre_slug == "dushi":
        genre_rule = "都市知识必须写清岗位、流程、凭据、资源或后果，不得把打脸、炫富、恋爱和靠关系取胜包装成行业知识；"
    elif genre_slug == "kehuan":
        genre_rule = "科幻知识必须写清设定对象、触发条件、运行方式、限制或后果，不得把战斗胜负、升级追杀和角色危机包装成科技规则；"
    elif genre_slug == "moshi":
        genre_rule = "末世知识必须写清生存对象、操作/规则、适用条件、资源风险或后果，不得把击杀升级、系统奖励、逃跑和背叛包装成求生知识；"
    elif genre_slug == "xuanhuan":
        genre_rule = "玄幻知识必须写清世界、力量、资源、组织或代价规则，不得把突破、奇遇、打脸、追杀和战斗胜负包装成设定；"
    elif genre_slug == "xianxia":
        genre_rule = "仙侠知识必须写清修行、师承、丹器、交易、灵脉或术法限制，不得把夺宝、杀敌、宗门比赛和一次突破包装成规则；"
    elif genre_slug == "xianyan":
        genre_rule = "现言知识必须写清家庭角色、凭据、流程、资源或生活后果，不得把强吻、吃醋、误会分手和重生复仇包装成生活知识；"
    elif genre_slug == "wuxianliu":
        genre_rule = "无限流知识必须写清副本载体、触发条件、验证方式、资源或失败后果，普通系统升级、打怪爆装和单次冒险不得入库；"
    else:
        genre_rule = "悬疑素材必须保留清晰的异常关系或信息缺口；"
    return f"""你是中文{genre_label}创作资料库的终审编辑。下面是候选素材与其原文证据。

逐条审查五项：具体性、可复用性、{score_label}、证据忠实度、表达质量。每项1—5分；只有五项全部不低于4分才能 accepted。JSON 字段仍使用 information_gap 表示第三项。

你可以在不改变证据事实的前提下重写 accepted 条目的 title、creative_material、reusable_pattern、mechanism 和 suspense_question。终稿必须：
- 是一个具体、清晰、脱离原书也成立的创作种子；
- 不是原文摘抄，不保留原书人名地名；
- 不用“处境随之改变”“限制后续发生什么”“某种异常”等空话；
- 不重复句式或同一机制；相近候选只保留最好的一条；
- {genre_rule}
- evidence_ids、category_key、subcategory_key 必须来自原候选，不得编造编号或改换证据。

候选：{json.dumps([d.model_dump() for d in drafts], ensure_ascii=False)}
证据：{json.dumps(evidence, ensure_ascii=False)}

严格按下面字段返回 JSON，不得改名、缺字段或另加顶层键：
{{
  "accepted": [
    {{
      "draft_id": "沿用候选编号",
      "evidence_ids": ["沿用候选证据编号"],
      "category_key": "沿用候选分类",
      "subcategory_key": "沿用候选子分类",
      "title": "终稿短标题",
      "creative_material": "终稿创作种子",
      "reusable_pattern": "终稿可复用关系",
      "mechanism": "终稿悬念机制",
      "suspense_question": "读者追问",
      "applicable_stage": "沿用或校正阶段",
      "tags": ["标签"],
      "scores": {{
        "concreteness": 1,
        "reusability": 1,
        "information_gap": 1,
        "evidence_fidelity": 1,
        "expression_quality": 1
      }}
    }}
  ],
  "rejected_draft_ids": ["未通过编号"]
}}
不得接受任何补造原文没有的细节；发现补造必须放入 rejected_draft_ids。"""


def build_evidence_audit_prompt(
    *,
    items: list[ReviewedSemanticMaterial],
    evidence_by_id: dict[str, EvidenceCandidate],
    genre_slug: str = "xuanyi",
) -> str:
    rows = []
    for item in items:
        rows.append({
            "draft_id": item.draft_id,
            "evidence_ids": item.evidence_ids,
            "creative_material": item.creative_material,
            "evidence": [
                evidence_by_id[eid].text
                for eid in item.evidence_ids
                if eid in evidence_by_id
            ],
        })
    rewrite_target = (
        "可复用知识"
        if genre_slug in {
            "zhongtian", "guyan", "dushi", "kehuan", "moshi",
            "xuanhuan", "xianxia", "xianyan", "wuxianliu",
        }
        else "有价值的悬疑素材"
    )
    forbidden_examples = (
        """- 原文只写“稻叶变黄并发现虫害”，不能增加害虫品种、配药剂量或保证治愈。
- 原文只写“谷物摊开晾晒”，不能增加具体含水率、温度或保存年限。
- 原文没有直接写出增产、灭菌、防病或营养效果，就不能把这些写成已证实结论。"""
        if genre_slug == "zhongtian"
        else (
            """- 原文只写“嫡母出面议亲”，不能增加特定朝代的法定流程或聘财比例。
- 原文只写“交出钥匙和账册”，不能增加原文没有的官印、地契或法律效力。
- 原文没有说明品级、继承顺序、宗族惩罚或宫规，就不能把常识猜测写成书中事实。"""
            if genre_slug == "guyan"
            else (
                """- 原文只写“双方商谈合作”，不能增加合同已经签订、股权比例或付款期限。
- 原文只写“律师查看材料”，不能增加已经立案、证据被法院采纳或必然胜诉。
- 原文只写“艺人进入录音室”，不能增加专辑发行流程、榜单成绩或行业惯例。"""
                if genre_slug == "dushi"
                else (
                    """- 原文只写“装置失去信号”，不能增加能源耗尽、量子干扰或敌方屏蔽。
- 原文只写“基因改造个体被送入研究所”，不能增加改造步骤、遗传稳定性或实验结论。
- 原文没有说明技术影响了阶层、法律或日常生活，就不能把社会后果写成已成立设定。"""
                    if genre_slug == "kehuan"
                    else (
                        """- 原文只写“人物喝了水后没有生病”，不能增加水源已经无污染、煮沸时间或长期安全结论。
- 原文只写“基地加固围墙”，不能增加墙体材料、承压等级或必然挡住尸群。
- 原文没有直接说明感染规律、配给制度、药品效果或变异弱点，就不能把求生常识猜测写成书中规则。"""
                        if genre_slug == "moshi"
                        else """- 原文只写“坠入雪地并生还”，不能增加“旧人形坑”“曾有人同样坠落”。
- 原文只写“钥匙能插进盒锁”，不能增加“钥匙只能锁不能开”。
- 原文只写“无信号处打开手机”，不能增加“未发送短信”。
- 原文没有说凶手、尸体成因、记忆篡改、超自然力量，就不能把它们写成已发生事实。"""
                    )
                )
            )
        )
    )
    if genre_slug == "xuanhuan":
        forbidden_examples = """- 原文只写“服药后突破”，不能增加药物适用境界、药毒或冷却时间。
- 原文只写“参加宗门考核”，不能增加录取名额、贡献门槛或处罚制度。
- 原文没有说明资源价格、血脉效果、秘境规则或力量代价，就不能用类型常识补齐。"""
    elif genre_slug == "xianxia":
        forbidden_examples = """- 原文只写“开炉炼丹”，不能增加丹方、火候、成丹率或药效。
- 原文只写“进入洞府”，不能增加灵气浓度、阵法权限或修炼收益。
- 原文没有说明师承程序、贡献兑换、术法限制或因果后果，就不能补成宗门规则。"""
    elif genre_slug == "xianyan":
        forbidden_examples = """- 原文只写“准备结婚”，不能增加领证材料、彩礼归属或法律效力。
- 原文只写“去医院检查”，不能增加诊断、治疗方案或必然康复。
- 原文没有说明户籍、随军、票证、住房或单位程序，就不能用年代常识补齐。"""
    elif genre_slug == "wuxianliu":
        forbidden_examples = """- 原文只写“进入世界”，不能增加副本入口、倒计时或返回条件。
- 原文只写“完成任务得到奖励”，不能增加积分价格、绑定规则或死亡惩罚。
- 原文没有直接呈现明暗规则、验证线索或失败条件，就不能补成通关机制。"""
    return f"""你是事实核验员，只做“主卡内容是否被原文证据支持”的逐事实审计，不评价文采。

把 creative_material 拆成最小事实，核对其中每个主体、物件、地点、数字、动作、状态和因果是否由 evidence 直接陈述或必然推出。

判定规则：
- supported：所有具体事实都被证据支持，creative_material 原样返回。
- rewritten：存在补造，但删除补造后仍能形成{rewrite_target}；返回只含被支持事实的完整重写句，并在 unsupported_claims 列出删除内容。
- reject：删除补造后已经没有明确异常或信息缺口。
- supporting_quotes 必须逐字摘自 evidence（可忽略空格差异），覆盖终稿中的每个关键事实；不能用无关句子为推断背书。

必须严格识别这类补造：
{forbidden_examples}

待审条目：{json.dumps(rows, ensure_ascii=False)}

严格返回下面的 JSON 对象：
{{"items":[{{"draft_id":"原编号","evidence_ids":["原编号"],"verdict":"supported或rewritten或reject","creative_material":"支持后的主卡句；reject可留空","unsupported_claims":["被删除的无证据事实"],"supporting_quotes":["逐字原文短句"]}}]}}
不得漏掉任何待审 draft_id，不得改变 evidence_ids。"""


def parse_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if "```" in raw:
        for part in raw.split("```"):
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                raw = candidate
                break
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model response does not contain a JSON object")
    value = json.loads(raw[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model response root is not an object")
    return value


def validate_drafts(
    batch: SemanticExtractionBatch,
    *,
    evidence_by_id: dict[str, EvidenceCandidate],
    genre_slug: str = "xuanyi",
    category_keys: tuple[str, ...] | None = None,
) -> tuple[list[SemanticMaterialDraft], list[str]]:
    """Business/evidence validation after Pydantic structural validation."""
    keys = category_keys or SEMANTIC_CATEGORY_KEYS[genre_slug]
    category_map = {
        category["key"]: category
        for category in TEMPLATES[genre_slug]["categories"]
        if category["key"] in keys
    }
    accepted: list[SemanticMaterialDraft] = []
    rejected: list[str] = []
    seen_text: set[str] = set()
    for draft in batch.materials:
        category = category_map.get(draft.category_key)
        subkeys = {
            sub["key"] for sub in category["subcategories"]
        } if category else set()
        if not category or draft.subcategory_key not in subkeys:
            rejected.append(f"{draft.draft_id}:invalid_category")
            continue
        if any(eid not in evidence_by_id for eid in draft.evidence_ids):
            rejected.append(f"{draft.draft_id}:missing_evidence")
            continue
        if draft.category_key == "opening_anomaly" and any(
            evidence_by_id[eid].position != "opening" for eid in draft.evidence_ids
        ):
            rejected.append(f"{draft.draft_id}:opening_evidence_out_of_scope")
            continue
        normalized = re.sub(r"[\W_]+", "", draft.creative_material)
        if len(normalized) < 16 or normalized in seen_text:
            rejected.append(f"{draft.draft_id}:thin_or_duplicate")
            continue
        evidence_text = "".join(evidence_by_id[eid].text for eid in draft.evidence_ids)
        evidence_normalized = re.sub(r"[\W_]+", "", evidence_text)
        # A knowledge card must synthesize; copying one complete evidence block is
        # a search result, not reusable knowledge.
        if len(normalized) >= 32 and normalized in evidence_normalized:
            rejected.append(f"{draft.draft_id}:verbatim_excerpt")
            continue
        seen_text.add(normalized)
        accepted.append(draft)
    return accepted, rejected


def validate_review(
    review: SemanticReviewBatch,
    *,
    source_drafts: list[SemanticMaterialDraft],
    evidence_by_id: dict[str, EvidenceCandidate],
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    by_id = {draft.draft_id: draft for draft in source_drafts}
    accepted: list[ReviewedSemanticMaterial] = []
    rejected = list(review.rejected_draft_ids)
    seen_text: set[str] = set()
    for item in review.accepted:
        original = by_id.get(item.draft_id)
        if original is None:
            rejected.append(f"{item.draft_id}:unknown_draft")
            continue
        if (
            item.evidence_ids != original.evidence_ids
            or item.category_key != original.category_key
            or item.subcategory_key != original.subcategory_key
        ):
            rejected.append(f"{item.draft_id}:lineage_changed")
            continue
        if min(item.scores.model_dump().values()) < 4:
            rejected.append(f"{item.draft_id}:quality_below_four")
            continue
        normalized = re.sub(r"[\W_]+", "", item.creative_material)
        if normalized in seen_text:
            rejected.append(f"{item.draft_id}:duplicate_final")
            continue
        evidence_text = "".join(evidence_by_id[eid].text for eid in item.evidence_ids)
        if len(normalized) >= 32 and normalized in re.sub(r"[\W_]+", "", evidence_text):
            rejected.append(f"{item.draft_id}:verbatim_final")
            continue
        seen_text.add(normalized)
        accepted.append(item)
    return accepted, rejected


def filter_farming_domain_knowledge(
    items: list[ReviewedSemanticMaterial],
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    """Remove evidence-backed cards that are still merely unrelated plot beats.

    The farming corpus is intentionally a practical reference shelf. Debt
    conflict, crime reconstruction, gift etiquette, and medical triage may be
    valid story events, but they do not become farming knowledge merely because
    a broad template cue matched nearby text.
    """
    accepted: list[ReviewedSemanticMaterial] = []
    rejected: list[str] = []
    for item in items:
        joined = " ".join((item.title, item.creative_material, item.reusable_pattern))
        if any(phrase in joined for phrase in _FARMING_OFF_TOPIC_PHRASES):
            rejected.append(f"{item.draft_id}:off_topic_farming_plot")
            continue
        accepted.append(item)
    return accepted, rejected


def filter_ancient_domain_knowledge(
    items: list[ReviewedSemanticMaterial],
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    """Keep the ancient shelf focused on institutions, customs, and resources."""
    accepted: list[ReviewedSemanticMaterial] = []
    rejected: list[str] = []
    for item in items:
        joined = " ".join((item.title, item.creative_material, item.reusable_pattern))
        if any(phrase in joined for phrase in _ANCIENT_OFF_TOPIC_PHRASES):
            rejected.append(f"{item.draft_id}:off_topic_ancient_plot")
            continue
        accepted.append(item)
    return accepted, rejected


def filter_urban_domain_knowledge(
    items: list[ReviewedSemanticMaterial],
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    """Keep the urban shelf focused on practical professional knowledge."""
    accepted: list[ReviewedSemanticMaterial] = []
    rejected: list[str] = []
    for item in items:
        joined = " ".join((item.title, item.creative_material, item.reusable_pattern))
        if any(phrase in joined for phrase in _URBAN_OFF_TOPIC_PHRASES):
            rejected.append(f"{item.draft_id}:off_topic_urban_plot")
            continue
        accepted.append(item)
    return accepted, rejected


def filter_scifi_domain_knowledge(
    items: list[ReviewedSemanticMaterial],
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    """Keep science-fiction cards focused on explicit rules and consequences."""
    accepted: list[ReviewedSemanticMaterial] = []
    rejected: list[str] = []
    for item in items:
        joined = " ".join((item.title, item.creative_material, item.reusable_pattern))
        if any(phrase in joined for phrase in _SCIFI_OFF_TOPIC_PHRASES):
            rejected.append(f"{item.draft_id}:off_topic_scifi_plot")
            continue
        accepted.append(item)
    return accepted, rejected


def filter_disaster_domain_knowledge(
    items: list[ReviewedSemanticMaterial],
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    """Keep disaster-fiction cards focused on explicit survival knowledge."""
    accepted: list[ReviewedSemanticMaterial] = []
    rejected: list[str] = []
    for item in items:
        joined = " ".join((item.title, item.creative_material, item.reusable_pattern))
        if any(phrase in joined for phrase in _DISASTER_OFF_TOPIC_PHRASES):
            rejected.append(f"{item.draft_id}:off_topic_disaster_plot")
            continue
        accepted.append(item)
    return accepted, rejected


def _filter_off_topic(
    items: list[ReviewedSemanticMaterial],
    *,
    phrases: tuple[str, ...],
    rejection_code: str,
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    accepted: list[ReviewedSemanticMaterial] = []
    rejected: list[str] = []
    for item in items:
        joined = " ".join((item.title, item.creative_material, item.reusable_pattern))
        if any(phrase in joined for phrase in phrases):
            rejected.append(f"{item.draft_id}:{rejection_code}")
            continue
        accepted.append(item)
    return accepted, rejected


def filter_fantasy_domain_knowledge(
    items: list[ReviewedSemanticMaterial],
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    return _filter_off_topic(
        items,
        phrases=_FANTASY_OFF_TOPIC_PHRASES,
        rejection_code="off_topic_fantasy_plot",
    )


def filter_xianxia_domain_knowledge(
    items: list[ReviewedSemanticMaterial],
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    return _filter_off_topic(
        items,
        phrases=_XIANXIA_OFF_TOPIC_PHRASES,
        rejection_code="off_topic_xianxia_plot",
    )


def filter_contemporary_domain_knowledge(
    items: list[ReviewedSemanticMaterial],
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    return _filter_off_topic(
        items,
        phrases=_CONTEMPORARY_OFF_TOPIC_PHRASES,
        rejection_code="off_topic_contemporary_plot",
    )


def filter_infinite_flow_domain_knowledge(
    items: list[ReviewedSemanticMaterial],
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    return _filter_off_topic(
        items,
        phrases=_INFINITE_FLOW_OFF_TOPIC_PHRASES,
        rejection_code="off_topic_infinite_flow_plot",
    )


def apply_evidence_audit(
    audit: EvidenceAuditBatch,
    *,
    reviewed: list[ReviewedSemanticMaterial],
    evidence_by_id: dict[str, EvidenceCandidate],
) -> tuple[list[ReviewedSemanticMaterial], list[str]]:
    by_id = {item.draft_id: item for item in reviewed}
    audit_by_id = {item.draft_id: item for item in audit.items}
    accepted: list[ReviewedSemanticMaterial] = []
    rejected: list[str] = []
    for draft_id, original in by_id.items():
        item = audit_by_id.get(draft_id)
        if item is None:
            rejected.append(f"{draft_id}:audit_missing")
            continue
        if item.evidence_ids != original.evidence_ids:
            rejected.append(f"{draft_id}:audit_lineage_changed")
            continue
        if item.verdict == "reject":
            rejected.append(f"{draft_id}:audit_rejected")
            continue
        if item.verdict == "supported" and item.unsupported_claims:
            rejected.append(f"{draft_id}:audit_inconsistent")
            continue
        text = item.creative_material.strip()
        if not 18 <= len(text) <= 140 or any(p in text for p in _BANNED_EMPTY_PHRASES):
            rejected.append(f"{draft_id}:audit_text_invalid")
            continue
        evidence_text = "".join(evidence_by_id[eid].text for eid in item.evidence_ids)
        compact_evidence = re.sub(r"\s+", "", evidence_text)
        if not item.supporting_quotes or any(
            re.sub(r"\s+", "", quote) not in compact_evidence
            for quote in item.supporting_quotes
        ):
            rejected.append(f"{draft_id}:audit_quote_mismatch")
            continue
        normalized = re.sub(r"[\W_]+", "", text)
        if len(normalized) >= 32 and normalized in re.sub(r"[\W_]+", "", evidence_text):
            rejected.append(f"{draft_id}:audit_verbatim")
            continue
        accepted.append(original.model_copy(update={"creative_material": text}))
    return accepted, rejected


def group_evidence_round_robin(
    candidates: list[EvidenceCandidate],
    *,
    limit: int,
    category_keys: tuple[str, ...] = SUSPENSE_CATEGORY_KEYS,
) -> list[EvidenceCandidate]:
    """Keep category coverage instead of letting a frequent cue dominate input."""
    grouped: dict[str, list[EvidenceCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.suggested_category].append(candidate)
    selected: list[EvidenceCandidate] = []
    keys = [key for key in category_keys if grouped.get(key)]
    while keys and len(selected) < limit:
        next_keys: list[str] = []
        for key in keys:
            if grouped[key] and len(selected) < limit:
                selected.append(grouped[key].pop(0))
            if grouped[key]:
                next_keys.append(key)
        keys = next_keys
    return selected
