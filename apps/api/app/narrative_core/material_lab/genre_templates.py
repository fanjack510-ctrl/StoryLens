"""GenreTemplate registry.

Each genre declares *what is worth extracting* from it. A template is a list of
categories; each category has subcategories, trigger lexicons and an
extraction strategy. Nothing here is shared blindly across genres.
"""
from __future__ import annotations

from typing import Any

# strategy values used by materials.py
#   object_anomaly  - concrete object + ownership/placement anomaly
#   behavior        - character action / reaction anomaly
#   person_doubt    - identity / relationship / background inconsistency
#   env_anomaly     - space / routine / physical trace anomaly
#   time_memory     - time dislocation, memory gap, repetition
#   event           - a plot event of the declared kind
#   state           - a described state (setting, power level, status)
#   relation        - relationship configuration / change
#   hook            - end-of-unit suspense line
#   structure       - stage / arc level observation


def _c(key, label, strategy, subs, cues=None, stage="", sort=100) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "strategy": strategy,
        "stage": stage,
        "cues": cues or [],
        "sort": sort,
        "subcategories": [{"key": k, "label": v, "cues": c} for k, v, c in subs],
    }


XUANYI = [
    _c("opening_anomaly", "开篇异常", "env_anomaly", [
        ("first_anomaly", "首个异常", ["不对劲", "反常", "异常", "诡异", "奇怪", "居然", "竟然"]),
        ("cold_open", "冷开场事件", ["尸体", "死", "报警", "失踪", "起火"]),
    ], stage="开篇", sort=10),
    _c("core_mystery", "核心谜题", "person_doubt", [
        ("identity", "身份之谜", ["身份", "来历", "究竟是谁", "冒名", "假名"]),
        ("disappearance", "失踪之谜", ["失踪", "下落不明", "不知去向", "人间蒸发"]),
        ("hidden_truth", "被掩盖的真相", ["真相", "隐瞒", "掩盖", "封存", "销毁"]),
    ], stage="全书", sort=20),
    _c("case", "案件", "event", [
        ("homicide", "命案", ["命案", "凶案", "谋杀", "被杀", "遇害"]),
        ("serial", "连环案", ["连环", "第二起", "又一起", "同样的手法"]),
        ("cold_case", "积案旧案", ["积案", "旧案", "陈年", "多年前的案子", "当年那起"]),
    ], stage="主线", sort=30),
    _c("investigation", "调查行动", "behavior", [
        ("field", "现场勘查", ["勘查", "现场", "搜查", "取证", "提取"]),
        ("interview", "询问走访", ["询问", "走访", "问讯", "审讯", "笔录", "口供"]),
        ("forensic", "技术鉴定", ["法医", "验尸", "解剖", "鉴定", "比对", "检验"]),
    ], stage="中段", sort=40),
    _c("clue_object", "实物线索", "object_anomaly", [
        ("leftover", "遗留物", ["遗留", "落下", "掉在", "留在"]),
        ("note", "纸条文书", ["纸条", "信", "字条", "便条", "遗书"]),
        ("accessory", "饰品", ["戒指", "项链", "耳钉", "手镯", "发簪"]),
        ("personal_item", "私人物件", ["钥匙", "钱包", "手机", "证件", "病历"]),
        ("suspicious", "可疑物证", ["指纹", "血迹", "脚印", "毛发", "烟头", "弹壳"]),
    ], stage="全书", sort=50),
    _c("clue_behavior", "行为线索", "behavior", [
        ("odd_action", "异常动作", ["异常", "反常", "古怪", "奇怪的举动"]),
        ("lie", "谎言", ["撒谎", "说谎", "谎言", "骗"]),
        ("testimony_gap", "口供漏洞", ["口供", "证词", "前后不一", "对不上", "矛盾"]),
        ("odd_reaction", "反常反应", ["面不改色", "毫不惊讶", "松了口气", "脸色一变"]),
        ("avoidance", "刻意回避", ["回避", "避而不谈", "岔开", "不肯说", "转移话题"]),
    ], stage="全书", sort=60),
    _c("person_doubt", "人物疑点", "person_doubt", [
        ("identity_odd", "身份异常", ["身份", "证件", "档案", "查无此人", "同名"]),
        ("relation_mismatch", "关系错位", ["关系", "其实是", "并不是", "亲生", "养"]),
        ("blank_history", "经历空白", ["空白", "那几年", "没有记录", "查不到"]),
        ("familiarity", "熟悉感异常", ["似曾相识", "面熟", "在哪见过", "叫得出"]),
        ("info_conflict", "信息矛盾", ["矛盾", "对不上", "不一致", "另一份"]),
    ], stage="全书", sort=70),
    _c("env_anomaly", "环境异常", "env_anomaly", [
        ("space", "空间异常", ["多出", "少了", "夹墙", "暗门", "地下室", "阁楼"]),
        ("routine", "日常异常", ["一如往常", "唯独", "偏偏", "从来不"]),
        ("physical_trace", "物理痕迹", ["痕迹", "划痕", "水渍", "灰尘", "脚印"]),
        ("closed_place", "封闭场所", ["反锁", "上锁", "封死", "密室", "从里面"]),
        ("repeating", "重复异象", ["每逢", "每年", "每隔", "又一次", "同样的"]),
    ], stage="全书", sort=80),
    _c("time_memory", "时间记忆", "time_memory", [
        ("time_shift", "时间错位", ["时间对不上", "早于", "晚于", "提前", "之后才"]),
        ("memory_gap", "记忆缺口", ["失忆", "不记得", "毫无印象", "记忆", "想不起"]),
        ("repetition", "重复事件", ["又发生", "同一天", "再一次", "重复"]),
        ("posthumous", "死后记录", ["死后", "已经去世", "身故之后", "遗体"]),
        ("impossible_time", "不可能时间", ["不可能", "当时他在", "同一时间", "分身乏术"]),
    ], stage="全书", sort=90),
    _c("evidence", "证据", "object_anomaly", [
        ("physical", "物证", ["物证", "证物", "检材", "样本"]),
        ("document", "书证", ["档案", "记录", "登记", "台账", "日志"]),
    ], stage="中段", sort=100),
    _c("suspect", "嫌疑人", "person_doubt", [
        ("shortlist", "嫌疑名单", ["嫌疑人", "嫌疑", "名单", "排查"]),
        ("alibi", "不在场证明", ["不在场", "当时在", "有人证", "证明他"]),
    ], stage="中段", sort=110),
    _c("motive", "动机", "person_doubt", [
        ("gain", "利益动机", ["遗产", "保险", "分红", "债", "钱"]),
        ("emotion", "情感动机", ["报复", "嫉妒", "恨", "情杀", "被抛弃"]),
        ("cover", "灭口掩盖", ["灭口", "封口", "知道太多", "掩盖"]),
    ], stage="后段", sort=120),
    _c("misdirection", "误导", "behavior", [
        ("red_herring", "烟雾弹", ["以为", "都认为", "看起来像", "所有人都"]),
        ("frame", "栽赃嫁祸", ["栽赃", "嫁祸", "陷害", "做成", "伪造现场"]),
    ], stage="中段", sort=130),
    _c("foreshadow", "伏笔", "structure", [
        ("planted", "埋设", ["当时没有在意", "并不知道", "后来才", "多年以后"]),
        ("recall", "回收", ["原来", "这才明白", "终于想起", "对上了"]),
    ], stage="全书", sort=140),
    _c("reversal", "反转", "structure", [
        ("identity_flip", "身份反转", ["其实是", "真正的", "根本不是", "居然是"]),
        ("role_flip", "立场反转", ["一直在帮", "反过来", "早就知道", "从一开始"]),
    ], stage="后段", sort=150),
    _c("reveal", "真相揭示", "structure", [
        ("confession", "当事人交代", ["承认", "坦白", "供认", "说出实情"]),
        ("deduction", "推理揭示", ["推理", "只有一个解释", "除非", "因此"]),
    ], stage="结局", sort=160),
    _c("hook", "章节钩子", "hook", [
        ("chapter_end", "章末悬念", []),
    ], stage="章末", sort=170),
    _c("ending_recall", "结局回收", "structure", [
        ("closure", "线索回收", ["终于", "全部", "一一", "了结", "尘埃落定"]),
    ], stage="结局", sort=180),
]

XUANHUAN = [
    _c("protagonist_start", "主角初始状态", "state", [
        ("weak_start", "起点低微", ["废物", "废柴", "垫底", "最差", "被欺", "受辱"]),
        ("talent", "天赋根骨", ["天赋", "根骨", "资质", "灵根", "体质"]),
    ], stage="开篇", sort=10),
    _c("worldview", "世界观", "state", [
        ("realm", "大陆疆域", ["大陆", "界", "域", "州", "疆"]),
        ("race", "种族", ["妖族", "魔族", "人族", "神族", "血脉"]),
    ], stage="开篇", sort=20),
    _c("cheat", "金手指", "object_anomaly", [
        ("artifact", "神秘物件", ["戒指", "珠子", "玉佩", "石碑", "残卷", "老爷爷"]),
        ("system", "系统", ["系统", "面板", "任务", "奖励", "签到"]),
    ], stage="开篇", sort=30),
    _c("power_system", "力量体系", "state", [
        ("cultivation", "修炼体系", ["炼气", "筑基", "金丹", "元婴", "斗气", "魔力"]),
        ("technique", "功法武技", ["功法", "武技", "秘籍", "招式", "神通"]),
    ], stage="全书", sort=40),
    _c("rank_system", "等级体系", "state", [
        ("tier", "境界阶位", ["境", "层", "阶", "级", "品"]),
    ], stage="全书", sort=50),
    _c("bloodline", "血脉体质", "state", [
        ("bloodline", "血脉", ["血脉", "血统", "传承", "先祖"]),
        ("physique", "体质", ["体质", "灵体", "圣体", "废体"]),
    ], stage="全书", sort=60),
    _c("resource", "修炼资源", "object_anomaly", [
        ("spirit_stone", "灵石丹药", ["灵石", "丹药", "灵草", "灵药"]),
        ("equipment", "装备法宝", ["法宝", "宝器", "飞剑", "灵器", "护甲"]),
    ], stage="全书", sort=70),
    _c("faction", "势力", "relation", [
        ("sect", "宗门世家", ["宗门", "世家", "门派", "家族", "长老"]),
        ("hostile", "敌对势力", ["敌对", "仇家", "死敌", "宿敌"]),
    ], stage="全书", sort=80),
    _c("map", "地图秘境", "state", [
        ("secret_realm", "秘境", ["秘境", "遗迹", "洞府", "禁地", "试炼"]),
        ("dungeon", "副本历练", ["历练", "试炼", "大比", "猎场"]),
    ], stage="中段", sort=90),
    _c("enemy_tier", "敌人梯度", "relation", [
        ("rival", "同阶对手", ["对手", "同辈", "天骄", "第一"]),
        ("boss", "上位强敌", ["长老", "宗主", "魔头", "至尊"]),
    ], stage="全书", sort=100),
    _c("upgrade_path", "升级路线", "structure", [
        ("breakthrough", "突破节点", ["突破", "晋级", "进阶", "跨入"]),
        ("bottleneck", "瓶颈", ["瓶颈", "卡在", "多年未", "停滞"]),
    ], stage="全书", sort=110),
    _c("fortune", "奇遇", "event", [
        ("windfall", "机缘", ["机缘", "奇遇", "捡到", "无意中", "意外获得"]),
    ], stage="全书", sort=120),
    _c("payoff", "爽点打脸", "event", [
        ("faceslap", "打脸", ["打脸", "傻眼", "震惊", "跌破眼镜", "刮目相看"]),
        ("revenge", "复仇雪耻", ["复仇", "报仇", "雪耻", "十倍奉还"]),
    ], stage="全书", sort=130),
    _c("arc_goal", "阶段目标", "structure", [
        ("stage_goal", "阶段任务", ["目标", "只要", "必须先", "第一步"]),
        ("long_goal", "长线目标", ["总有一天", "终有", "此生", "毕生"]),
    ], stage="全书", sort=140),
    _c("hook", "章节钩子", "hook", [("chapter_end", "章末悬念", [])], stage="章末", sort=150),
]

XIANXIA = [
    _c("dao_path", "道途", "state", [
        ("enlighten", "悟道", ["悟", "道心", "顿悟", "明悟"]),
        ("tribulation", "天劫", ["天劫", "渡劫", "雷劫", "心魔劫"]),
    ], stage="全书", sort=10),
    _c("power_system", "修炼体系", "state", [
        ("realm", "境界", ["炼气", "筑基", "金丹", "元婴", "化神", "大乘"]),
        ("technique", "功法", ["功法", "道法", "剑诀", "真诀"]),
    ], stage="全书", sort=20),
    _c("sect", "仙门宗派", "relation", [
        ("sect", "宗门", ["宗", "门", "峰", "殿", "掌门", "长老"]),
        ("disciple", "师承", ["师父", "师兄", "师姐", "亲传", "外门", "内门"]),
    ], stage="全书", sort=30),
    _c("resource", "灵物资源", "object_anomaly", [
        ("elixir", "丹药灵草", ["丹", "灵草", "灵药", "药园"]),
        ("artifact", "法宝", ["法宝", "灵宝", "仙器", "本命"]),
    ], stage="全书", sort=40),
    _c("secret_realm", "秘境洞天", "state", [
        ("realm", "秘境", ["秘境", "洞天", "遗府", "禁地"]),
    ], stage="中段", sort=50),
    _c("karma", "因果宿命", "structure", [
        ("karma", "因果", ["因果", "宿命", "前世", "轮回", "命数"]),
    ], stage="全书", sort=60),
    _c("hook", "章节钩子", "hook", [("chapter_end", "章末悬念", [])], stage="章末", sort=70),
]

DUSHI = [
    _c("identity", "身份设定", "state", [
        ("hidden_elite", "隐藏身份", ["隐藏", "低调", "真实身份", "马甲"]),
        ("profession", "职业", ["医生", "律师", "警察", "老师", "程序员", "总裁", "老板"]),
    ], stage="开篇", sort=10),
    _c("conflict", "都市冲突", "event", [
        ("workplace", "职场冲突", ["公司", "上司", "同事", "项目", "裁员", "竞标"]),
        ("business", "商战", ["收购", "股权", "对手公司", "融资", "谈判"]),
        ("street", "街头冲突", ["打架", "混混", "找茬", "堵", "碰瓷"]),
    ], stage="全书", sort=20),
    _c("resource", "资源人脉", "relation", [
        ("connection", "人脉", ["关系", "牵线", "引荐", "背景", "靠山"]),
        ("money", "资金", ["资金", "投资", "分红", "股份", "现金流"]),
    ], stage="全书", sort=30),
    _c("payoff", "爽点", "event", [
        ("faceslap", "打脸", ["打脸", "傻眼", "震惊", "刮目相看"]),
        ("reveal_status", "身份暴露", ["原来他是", "居然是", "才知道他"]),
    ], stage="全书", sort=40),
    _c("hook", "章节钩子", "hook", [("chapter_end", "章末悬念", [])], stage="章末", sort=50),
]

XIANYAN = [
    _c("female_lead", "女主人设", "state", [
        ("persona", "性格", ["独立", "要强", "温柔", "冷静", "乐观", "倔"]),
        ("background", "家庭背景", ["家里", "父母", "单亲", "孤儿", "重男轻女"]),
    ], stage="开篇", sort=10),
    _c("male_lead", "男主人设", "state", [
        ("persona", "性格", ["冷淡", "克制", "毒舌", "温柔", "偏执", "沉稳"]),
        ("profession", "职业", ["医生", "律师", "教授", "总裁", "军人", "警察"]),
    ], stage="开篇", sort=20),
    _c("meeting", "相遇方式", "event", [
        ("first_meet", "初遇", ["第一次见", "初次", "撞见", "被介绍", "重逢"]),
        ("forced", "强制同框", ["合租", "同事", "邻居", "被安排", "不得不"]),
    ], stage="开篇", sort=30),
    _c("attraction", "吸引点", "relation", [
        ("ability", "能力吸引", ["专业", "厉害", "救了", "帮了", "解决"]),
        ("detail", "细节吸引", ["记得", "习惯", "递", "外套", "伞", "留了灯"]),
    ], stage="前中段", sort=40),
    _c("ambiguity", "暧昧事件", "event", [
        ("proximity", "近距离", ["靠近", "呼吸", "指尖", "碰到", "抱"]),
        ("care", "照顾", ["送", "接", "煮", "熬夜", "陪"]),
    ], stage="中段", sort=50),
    _c("escalation", "关系升级", "relation", [
        ("confession", "表白", ["表白", "喜欢你", "在一起", "答应"]),
        ("commitment", "确认关系", ["女朋友", "男朋友", "见家长", "结婚", "领证"]),
    ], stage="中后段", sort=60),
    _c("obstacle", "阻力", "relation", [
        ("secret", "秘密", ["秘密", "瞒着", "没说", "隐瞒"]),
        ("misunderstanding", "误会", ["误会", "以为", "看见了", "听错"]),
        ("ex", "前任", ["前任", "前女友", "前男友", "初恋"]),
        ("family", "家庭阻力", ["父母反对", "不同意", "门不当", "家里"]),
        ("career", "事业冲突", ["调岗", "出国", "外派", "辞职", "机会"]),
    ], stage="中后段", sort=70),
    _c("separation", "分离", "event", [
        ("breakup", "分手", ["分手", "分开", "走了", "断了"]),
        ("chase", "追妻追夫", ["追", "回来", "等", "找她", "找他"]),
    ], stage="后段", sort=80),
    _c("ending", "结局", "structure", [
        ("he", "HE", ["在一起", "婚礼", "余生", "圆满"]),
        ("be", "BE", ["再也没有", "错过", "最后一面", "遗憾"]),
    ], stage="结局", sort=90),
    _c("hook", "章节钩子", "hook", [("chapter_end", "章末悬念", [])], stage="章末", sort=100),
]

GUYAN = [
    _c("status", "身份阶层", "state", [
        ("rank", "品级身份", ["嫡", "庶", "妾", "王妃", "郡主", "县主", "公主"]),
        ("commoner", "平民出身", ["农家", "商户", "寒门", "民女"]),
    ], stage="开篇", sort=10),
    _c("clan", "家族宗族", "relation", [
        ("household", "府中格局", ["府", "院", "房", "老夫人", "当家", "主母"]),
        ("clan_rule", "宗族礼制", ["族规", "宗祠", "族老", "祖训", "礼法"]),
    ], stage="全书", sort=20),
    _c("marriage", "婚姻联姻", "relation", [
        ("betrothal", "议亲", ["议亲", "定亲", "说亲", "纳采", "婚书"]),
        ("alliance", "联姻", ["联姻", "结亲", "两家", "利益"]),
    ], stage="中段", sort=30),
    _c("court", "朝堂官场", "relation", [
        ("office", "官职", ["官", "职", "升迁", "贬", "调任", "赐"]),
        ("faction", "党争", ["党", "派", "结党", "弹劾", "参本"]),
    ], stage="中后段", sort=40),
    _c("palace", "宫廷", "relation", [
        ("rank", "位分", ["贵妃", "皇后", "嫔", "才人", "选秀"]),
        ("intrigue", "宫斗", ["设局", "构陷", "下毒", "失宠", "承宠"]),
    ], stage="中后段", sort=50),
    _c("household_strife", "宅斗", "event", [
        ("scheme", "算计", ["算计", "设计", "陷害", "推", "落水", "小产"]),
        ("resource", "管家权", ["管家", "掌中馈", "钥匙", "账", "月例"]),
    ], stage="中段", sort=60),
    _c("secret_identity", "身份秘密", "person_doubt", [
        ("swap", "换子抱错", ["抱错", "换", "亲生", "不是亲"]),
        ("hidden_origin", "隐藏出身", ["身世", "生母", "外室", "私生"]),
    ], stage="全书", sort=70),
    _c("turnaround", "翻身节点", "structure", [
        ("rise", "翻身", ["翻身", "扳回", "抬举", "重新", "得势"]),
    ], stage="中后段", sort=80),
    _c("ending", "结局归宿", "structure", [
        ("settle", "归宿", ["和离", "归宿", "白首", "圆满", "了结"]),
    ], stage="结局", sort=90),
    _c("hook", "章节钩子", "hook", [("chapter_end", "章末悬念", [])], stage="章末", sort=100),
]

KEHUAN = [
    _c("premise", "核心科学假设", "state", [
        ("hypothesis", "设定前提", ["假设", "如果", "理论", "原理", "定律"]),
        ("phenomenon", "异常现象", ["现象", "观测", "信号", "异常读数"]),
    ], stage="开篇", sort=10),
    _c("tech_rule", "技术规则", "state", [
        ("rule", "规则限制", ["只能", "无法", "必须", "代价", "上限", "限制"]),
        ("device", "关键技术", ["装置", "系统", "芯片", "接口", "引擎", "算法"]),
    ], stage="全书", sort=20),
    _c("society", "社会变化", "state", [
        ("structure", "社会结构", ["阶层", "分区", "配额", "身份编码", "等级"]),
        ("daily", "日常改变", ["日常", "生活", "出行", "工作", "教育"]),
    ], stage="全书", sort=30),
    _c("institution", "制度", "relation", [
        ("law", "法规", ["法", "条例", "禁止", "许可", "登记"]),
        ("org", "机构", ["委员会", "联邦", "公司", "研究所", "军方"]),
    ], stage="全书", sort=40),
    _c("ethics", "伦理问题", "structure", [
        ("dilemma", "两难", ["该不该", "是否应该", "代价是", "牺牲"]),
        ("identity", "人的定义", ["是不是人", "意识", "灵魂", "复制", "克隆"]),
    ], stage="全书", sort=50),
    _c("cost", "技术代价", "structure", [
        ("price", "代价", ["代价", "副作用", "反噬", "失去", "损耗"]),
    ], stage="中后段", sort=60),
    _c("disaster", "灾难", "event", [
        ("failure", "系统失效", ["失控", "崩溃", "故障", "断联", "过载"]),
        ("catastrophe", "大灾变", ["灾难", "毁灭", "撞击", "爆发", "湮灭"]),
    ], stage="中后段", sort=70),
    _c("consequence", "因果后果", "structure", [
        ("chain", "连锁反应", ["因此", "导致", "结果", "连锁", "波及"]),
    ], stage="后段", sort=80),
    _c("hook", "章节钩子", "hook", [("chapter_end", "章末悬念", [])], stage="章末", sort=90),
]

MOSHI = [
    _c("cataclysm", "灾变机制", "state", [
        ("outbreak", "爆发方式", ["爆发", "感染", "扩散", "陨石", "辐射", "病毒"]),
        ("rule", "灾变规则", ["规则", "只有", "会变成", "感染后", "夜里"]),
    ], stage="开篇", sort=10),
    _c("resource", "生存资源", "object_anomaly", [
        ("food", "食物饮水", ["食物", "水", "罐头", "粮", "净水"]),
        ("weapon", "武器弹药", ["武器", "枪", "子弹", "刀", "弹药"]),
        ("medicine", "药品", ["药", "抗生素", "血清", "疫苗"]),
        ("fuel", "燃料能源", ["汽油", "燃料", "电", "发电"]),
    ], stage="全书", sort=20),
    _c("base", "基地据点", "state", [
        ("shelter", "避难所", ["避难所", "基地", "据点", "安全区", "营地"]),
        ("defense", "防御工事", ["围墙", "路障", "岗哨", "加固"]),
    ], stage="中段", sort=30),
    _c("team", "队伍", "relation", [
        ("member", "成员", ["队友", "队长", "同伴", "加入", "带上"]),
        ("betray", "背叛", ["背叛", "抛下", "出卖", "内讧"]),
    ], stage="全书", sort=40),
    _c("ability", "能力", "state", [
        ("awaken", "觉醒", ["觉醒", "异能", "进化", "变强"]),
        ("limit", "能力限制", ["代价", "反噬", "冷却", "次数", "上限"]),
    ], stage="全书", sort=50),
    _c("order", "秩序变化", "state", [
        ("collapse", "秩序崩塌", ["无政府", "抢", "暴乱", "没有法律"]),
        ("new_rule", "新秩序", ["规矩", "管理", "分配", "投票", "首领"]),
    ], stage="中后段", sort=60),
    _c("threat", "危险升级", "event", [
        ("escalate", "威胁升级", ["更强", "进化", "变异", "成群", "第二波"]),
        ("human", "人祸", ["劫掠", "火并", "抢夺", "人比丧尸"]),
    ], stage="中后段", sort=70),
    _c("hook", "章节钩子", "hook", [("chapter_end", "章末悬念", [])], stage="章末", sort=80),
]

WUXIANLIU = [
    _c("instance", "副本", "state", [
        ("setting", "副本场景", ["副本", "场景", "世界", "关卡", "地图"]),
        ("difficulty", "难度等级", ["难度", "等级", "新手", "地狱", "噩梦"]),
    ], stage="全书", sort=10),
    _c("rule", "副本规则", "state", [
        ("explicit", "明面规则", ["规则", "须知", "禁止", "必须", "不得"]),
        ("hidden", "隐藏规则", ["隐藏", "真正的规则", "没有写", "另一条"]),
        ("contradiction", "规则冲突", ["矛盾", "冲突", "同时", "两条规则"]),
    ], stage="全书", sort=20),
    _c("task", "任务", "event", [
        ("main", "主线任务", ["主线", "任务", "目标", "完成"]),
        ("hidden_task", "隐藏任务", ["隐藏任务", "额外", "意外触发"]),
    ], stage="全书", sort=30),
    _c("death_condition", "死亡条件", "state", [
        ("trigger", "触发死亡", ["死", "淘汰", "出局", "抹杀", "违反"]),
    ], stage="全书", sort=40),
    _c("solution", "破解方式", "structure", [
        ("logic", "逻辑破解", ["推理", "发现", "关键在于", "只要"]),
        ("exploit", "规则利用", ["利用规则", "钻空子", "反向", "漏洞"]),
    ], stage="中后段", sort=50),
    _c("team", "队伍配置", "relation", [
        ("role", "分工", ["负责", "分工", "掩护", "断后", "侦查"]),
        ("conflict", "队内冲突", ["内讧", "分歧", "抛弃", "牺牲谁"]),
    ], stage="全书", sort=60),
    _c("reward", "奖励惩罚", "state", [
        ("reward", "奖励", ["奖励", "积分", "道具", "兑换", "提升"]),
        ("penalty", "惩罚", ["惩罚", "扣除", "抹杀", "降级"]),
    ], stage="全书", sort=70),
    _c("hook", "章节钩子", "hook", [("chapter_end", "章末悬念", [])], stage="章末", sort=80),
]

ZHONGTIAN = [
    _c("start_state", "初始困境", "state", [
        ("poverty", "家徒四壁", ["家徒四壁", "米缸", "借米", "断粮", "揭不开锅"]),
        ("family_pos", "家中处境", ["重男轻女", "不受宠", "分家", "偏心", "克扣"]),
    ], stage="开篇", sort=10),
    _c("skill", "谋生手艺", "state", [
        ("craft", "手艺", ["手艺", "会做", "配方", "秘方", "针线", "厨艺"]),
        ("knowledge", "现代知识", ["现代", "前世", "书上说", "记得"]),
    ], stage="全书", sort=20),
    _c("business", "经营发家", "event", [
        ("first_money", "第一桶金", ["第一笔", "卖了", "赚", "换钱", "银子"]),
        ("expand", "扩大经营", ["铺子", "作坊", "田地", "雇", "长工", "分号"]),
    ], stage="中段", sort=30),
    _c("daily", "日常细节", "state", [
        ("food", "吃食", ["米", "粥", "腊肉", "野菜", "红薯", "包子", "腌"]),
        ("chore", "劳作", ["下地", "喂", "砍柴", "挑水", "洗", "缝"]),
    ], stage="全书", sort=40),
    _c("village_conflict", "邻里冲突", "event", [
        ("relative", "亲戚纠纷", ["伯娘", "婶子", "舅舅", "分家", "讨要", "占便宜"]),
        ("neighbor", "村邻是非", ["闲话", "眼红", "嫉妒", "编排", "告状"]),
    ], stage="全书", sort=50),
    _c("rise", "阶层跃迁", "structure", [
        ("marriage", "婚事", ["说亲", "定亲", "出嫁", "娶"]),
        ("status", "身份改变", ["秀才", "进城", "京城", "老爷", "夫人"]),
    ], stage="后段", sort=60),
    _c("hook", "章节钩子", "hook", [("chapter_end", "章末悬念", [])], stage="章末", sort=70),
]

TEMPLATES: dict[str, dict[str, Any]] = {
    "xuanyi": {"label": "悬疑", "categories": XUANYI},
    "xuanhuan": {"label": "玄幻", "categories": XUANHUAN},
    "xianxia": {"label": "仙侠", "categories": XIANXIA},
    "dushi": {"label": "都市", "categories": DUSHI},
    "xianyan": {"label": "现言", "categories": XIANYAN},
    "guyan": {"label": "古言", "categories": GUYAN},
    "kehuan": {"label": "科幻", "categories": KEHUAN},
    "moshi": {"label": "末世", "categories": MOSHI},
    "wuxianliu": {"label": "无限流", "categories": WUXIANLIU},
    "zhongtian": {"label": "种田", "categories": ZHONGTIAN},
}

GENRE_ORDER = list(TEMPLATES.keys())


def template_for(genre_slug: str) -> dict[str, Any] | None:
    return TEMPLATES.get(genre_slug)


def all_category_keys(genre_slug: str) -> list[str]:
    t = TEMPLATES.get(genre_slug)
    return [c["key"] for c in t["categories"]] if t else []


def label_index() -> tuple[dict[str, str], dict[str, str]]:
    """key -> Chinese label, for categories and subcategories.

    The facet panel groups by the stored key, so without this the sidebar shows
    raw slugs (hook / opening_anomaly) next to Chinese facets everywhere else.
    Keys are shared across genres by design, and the labels agree where they
    are, so a flat index is enough.
    """
    cats: dict[str, str] = {}
    subs: dict[str, str] = {}
    for tpl in TEMPLATES.values():
        for c in tpl["categories"]:
            cats.setdefault(c["key"], c["label"])
            for s in c["subcategories"]:
                subs.setdefault(s["key"], s["label"])
    return cats, subs
