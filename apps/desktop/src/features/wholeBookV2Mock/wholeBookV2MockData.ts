export type ChapterRange = [number, number];

export const bookMeta = {
  title: "《大型长篇小说 Mock》",
  chapterCount: 1299,
  characterCount: 2672342,
  genres: ["奇幻", "悬疑", "成长"],
  tagline: "一个失去名字的边城抄写员，为阻止世界被重新书写，沿着十三座沉睡之城追索自己的来历。",
};

export const overviewFacts = [
  ["类型与叙事画像", "奇幻冒险为外壳、身份悬疑为推进器、长线成长为情感主轴"],
  ["一句话故事", bookMeta.tagline],
  ["全书概要", "边城抄写员林砚发现旧史会在月蚀后改写现实。他与伙伴横跨十三城，追查空白王朝、镜海盟约与自身身世，最终选择让所有人共同保管历史。"],
  ["主角", "林砚｜旧史抄写员、无名者后裔"],
  ["核心目标", "找回被抹去的名字，并阻止归零仪式覆盖众生记忆"],
  ["核心冲突", "个人身份完整与世界秩序稳定之间不可兼得"],
  ["核心悬念", "究竟是谁第一次删去了林砚，以及他为何主动留下第二把钥匙"],
  ["最大转折", "第 873 章：林砚确认终极敌人是未来的自己留下的纠错人格"],
  ["最终高潮", "第 1221—1270 章：十三城共同记忆与归零仪式正面碰撞"],
  ["结局", "旧史不再由一人裁定；林砚保留伤痕与名字，成为第一位公共记忆守门人"],
] as const;

export const storyStages = [
  { name: "边城异响", range: [1, 118] as ChapterRange, summary: "异常文字出现，主角被迫离城" },
  { name: "雾港结盟", range: [119, 276] as ChapterRange, summary: "队伍形成，第一条身份线索落地" },
  { name: "北原试炼", range: [277, 421] as ChapterRange, summary: "能力体系升级，代价规则确立" },
  { name: "镜海迷局", range: [422, 589] as ChapterRange, summary: "叙事视角错位，盟友身份受疑" },
  { name: "王都裂变", range: [590, 748] as ChapterRange, summary: "公开冲突爆发，旧秩序分裂" },
  { name: "地下王朝", range: [749, 903] as ChapterRange, summary: "最大转折揭示，目标被重写" },
  { name: "十三城战争", range: [904, 1087] as ChapterRange, summary: "多线汇合，关系付出代价" },
  { name: "归零之前", range: [1088, 1219] as ChapterRange, summary: "伏笔集中回收，最终选择成形" },
  { name: "共同记忆", range: [1220, 1299] as ChapterRange, summary: "终局高潮与余波" },
];

export const drivers = [
  ["身份谜团", 94], ["成长", 88], ["世界秘密", 84], ["人物关系", 76], ["生存压力", 69],
] as const;

export const storylines = [
  { name: "主线｜归零仪式", range: [1, 1299] as ChapterRange, tone: "main" },
  { name: "支线｜林砚身世", range: [23, 1238] as ChapterRange, tone: "sub" },
  { name: "支线｜镜海盟约", range: [134, 1012] as ChapterRange, tone: "sub" },
  { name: "支线｜十三城继承", range: [277, 1274] as ChapterRange, tone: "sub" },
  { name: "支线｜顾灯失踪", range: [81, 956] as ChapterRange, tone: "sub" },
  { name: "支线｜白塔叛乱", range: [516, 1127] as ChapterRange, tone: "sub" },
];

export const causalChain = [
  "空白页渗出陌生名字", "林砚触发禁书追捕", "队伍进入镜海", "盟约泄露引发王都裂变",
  "地下档案证明未来自我存在", "十三城拒绝交出记忆", "归零仪式失去唯一控制者",
];

export const chronology = [
  { event: "旧王朝封存第一版历史", story: 1, narrative: 742 },
  { event: "林砚的名字被删除", story: 18, narrative: 873 },
  { event: "边城空白页事件", story: 46, narrative: 1 },
  { event: "镜海盟约破裂", story: 61, narrative: 508 },
  { event: "未来人格启动归零", story: 78, narrative: 904 },
  { event: "十三城共享记忆", story: 96, narrative: 1248 },
];

export const characters = [
  ["林砚", "主角", "求真者 → 共同守门人"], ["顾灯", "同行者", "逃避继承 → 主动承担"],
  ["闻雪", "调查者", "规则信徒 → 规则修订者"], ["祝鸦", "对手/镜像", "秩序维护 → 极端归零"],
  ["沈舟", "导师", "隐瞒者 → 公开证人"], ["阿葵", "见证者", "边缘记录者 → 城邦发言人"],
  ["陆峤", "盟友", "雇佣护卫 → 无条件守护"], ["季衡", "政敌", "现实主义者 → 临时同盟"],
  ["缄默王", "历史人物", "传说暴君 → 失败的保护者"], ["小满", "钥匙人物", "被保护者 → 最终授权者"],
  ["白砚", "未来人格", "纠错工具 → 核心敌手"], ["谢回", "记录官", "旁观者 → 泄密者"],
] as const;

export const protagonistArc = [
  [1, "无名日常"], [87, "被迫离城"], [214, "第一次主动选择"], [349, "能力与代价"],
  [503, "信任破裂"], [647, "承担领队责任"], [873, "镜像真相"], [1016, "拒绝唯一答案"],
  [1228, "公开自己的记忆"], [1299, "共同守门人"],
] as const;

const relationPairs = [
  ["林砚", "顾灯", "互疑 → 托付"], ["林砚", "闻雪", "合作 → 决裂 → 和解"],
  ["林砚", "祝鸦", "追捕 → 镜像对抗"], ["林砚", "沈舟", "师徒 → 审判 → 理解"],
  ["林砚", "白砚", "未知 → 自我对抗 → 整合"], ["顾灯", "小满", "保护 → 继承"],
  ["闻雪", "季衡", "政敌 → 战时同盟"], ["祝鸦", "季衡", "交易 → 背叛"],
  ["沈舟", "谢回", "同僚 → 秘密竞争"], ["阿葵", "陆峤", "雇佣 → 亲密盟友"],
  ["陆峤", "林砚", "戒备 → 生死同盟"], ["小满", "白砚", "控制 → 反授权"],
  ["缄默王", "沈舟", "历史传承"], ["谢回", "闻雪", "情报交换 → 公开指证"],
  ["阿葵", "顾灯", "误会 → 相互见证"], ["季衡", "林砚", "利用 → 尊重"],
] as const;
export const relationships = relationPairs.map((r, index) => ({
  source: r[0], target: r[1], lifecycle: r[2], range: [20 + index * 31, Math.min(1299, 510 + index * 47)] as ChapterRange,
}));

const hookNames = ["消失的姓氏", "第十四座城", "镜中回声", "导师的空白信", "会说话的地图", "王冠内侧刻痕", "顾灯的第二份遗嘱", "归零倒计时", "小满的真实年龄", "未来人格", "黑潮为何退去", "最后一页由谁书写"];
export const hookLifecycles = hookNames.map((name, i) => ({
  name,
  nodes: ["提出", "强化", "线索", "误导", "部分揭示", "反转", "最终回收"].map((type, j) => ({
    type, chapter: Math.min(1299, 12 + i * 29 + j * (27 + i * 2)),
  })),
}));

export const pacingSeries = ["剧情推进", "阅读张力", "情绪强度", "阅读动力", "钩子密度", "节奏速度"].map((name, seriesIndex) => ({
  name,
  values: Array.from({ length: 130 }, (_, i) => {
    const ch = 1 + i * 10;
    const wave = Math.sin((i + seriesIndex * 4) / (7 + seriesIndex)) * 14;
    const pulse = [43, 87, 122].some((p) => Math.abs(i - p) < 4) ? 20 : 0;
    const fatigue = i > 66 && i < 75 ? -16 : 0;
    return { chapter: Math.min(ch, 1299), value: Math.max(12, Math.min(98, Math.round(48 + seriesIndex * 3 + wave + pulse + fatigue))) };
  }),
}));

export const heatmapDimensions = ["主线推进", "人物塑造", "冲突升级", "悬念", "伏笔", "回收", "过渡"];
export const chapterHeatmap = Array.from({ length: 26 }, (_, i) => ({
  range: [i * 50 + 1, Math.min(1299, (i + 1) * 50)] as ChapterRange,
  values: heatmapDimensions.map((_, j) => 18 + ((i * 37 + j * 23 + i * j * 7) % 81)),
}));

export const genreLenses = [
  { title: "身份谜团", genre: "悬疑", score: 91, axis: ["身份缺口", "替代解释", "证据冲突", "真相代价"], note: "揭示密度稳定，但中后段替代解释停留稍久。" },
  { title: "成长阶梯", genre: "成长", score: 87, axis: ["能力门槛", "选择代价", "关系反馈", "价值重构"], note: "十阶成长节点清晰，第六至七阶跃迁偏快。" },
  { title: "世界观揭示", genre: "奇幻", score: 84, axis: ["规则提出", "规则验证", "边界破坏", "终局应用"], note: "规则能进入行动，但镜海规则首次说明略集中。" },
];

const diagnosisSeeds = [
  ["结构", "中段目标切换缺少缓冲", [642, 688], "阶段五末尾连续三次改变行动目标", "读者可能误判主线方向", "高"],
  ["结构", "终局前置准备偏长", [1088, 1154], "连续 67 章主要承担集结功能", "削弱高潮前加速度", "中"],
  ["人物", "闻雪的关键选择反馈延迟", [492, 548], "选择后 56 章才出现关系后果", "人物主动性感知下降", "中"],
  ["人物", "祝鸦动机证据分布不均", [731, 902], "动机证据集中于两次回忆", "反派转向显得突兀", "高"],
  ["剧情", "北原试炼重复同类障碍", [326, 382], "四次冲突均以规则破解结束", "推进方式单一", "中"],
  ["剧情", "白塔支线回归主线过晚", [613, 816], "支线核心物件离场 203 章", "支线价值被暂时遗忘", "低"],
  ["悬念", "第十四座城误导持续过久", [455, 706], "三次强化但无新增可验证线索", "悬念可能转为拖延感", "高"],
  ["悬念", "导师空白信回收信息超载", [865, 881], "单次揭示同时解释五项旧疑问", "回收快感相互稀释", "中"],
  ["节奏", "王都会议形成疲劳区", [668, 742], "对话场景占比连续七个窗口超阈值", "阅读速度明显下降", "高"],
  ["节奏", "高潮后余波略短", [1271, 1299], "六条人物线仅三条有独立落点", "情绪释放不充分", "中"],
  ["悬念", "身份谜团公平线索不足", [201, 463], "两条关键线索首次出现时不可辨认", "悬疑公平性下降", "高"],
  ["人物", "成长代价在后段弱化", [1016, 1162], "两次能力升级未产生持久损失", "成长主题力度下降", "中"],
] as const;
export const diagnoses = diagnosisSeeds.map((d, i) => ({ category: d[0], issue: d[1], range: d[2] as ChapterRange, basis: d[3], impact: d[4], severity: d[5], evidence: `MOCK-C${String((d[2] as ChapterRange)[0]).padStart(4, "0")}-P${String(i + 3).padStart(4, "0")}` }));

export const progress = {
  percent: 63, currentStage: "人物关系", window: [386, 612], chapters: [1, 817], calls: 1482,
  success: 1451, failed: 9, retries: 22, elapsed: "6 小时 42 分", remaining: "约 3 小时 51 分",
  estimatedCost: 186.4, currentCost: 117.82, provider: "Mock Provider（静态展示）", waitSeconds: 18,
  recentlyCompleted: ["人物弧｜窗口 381–385", "故事线统一｜第 1–1299 章", "人物统一｜12 个核心人物"],
  processing: ["关系归一化｜林砚 ↔ 白砚", "窗口 386 / 612｜第 816–820 章", "Evidence 索引｜批次 97"],
};
export const progressStages = ["准备正文", "类型识别", "建立窗口", "人物事件提取", "人物统一", "故事线", "人物弧", "人物关系", "悬念回收", "因果时间线", "节奏分析", "作品策略分析", "综合评估", "Evidence", "最终报告"];
