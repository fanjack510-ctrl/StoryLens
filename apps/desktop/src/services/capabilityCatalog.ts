/** 这个产品能做什么——一处定义，界面各处都照着它说。
 *
 *  这份清单改过两次，两次都是被同一句话打回来的。
 *
 *  第一版只列付费项。用户说：「作为用户根本不知道到底能干哪些功能」——
 *  一份只列收费项的清单答不了那个问题，还顺带说了句「免费的不值一提」。
 *
 *  第二版列全了，但每项后面跟一句「位置：书库 → 打开任意一本书」。
 *  用户说：「像一页说明书。正常的工具不是应该有个功能标签，点进去然后引导怎么操作？」
 *  他是对的——**告诉人往哪儿走，和让人点一下就开始，是两回事**。
 *
 *  第三版是改名。前两版的名字——共性视图、按意思找、三种读法、归纳套路、找写法——
 *  用户的反应是「这起的太AI味了，一眼假，莫名其妙」。他是对的：那些词全是我
 *  拿一个动词和一个名词硬拼出来的，写手不这么说话。
 *
 *  **而正确的名字其实一直在他嘴里。**问「按意思找是找啥」时他自己说的是「找参考？」；
 *  问共性视图该叫什么时他自己给的是「共同套路」。我拿着这两个真词，
 *  又去造了一轮「归纳套路」「找写法」——把他的真话翻译成了我的假话。
 *
 *  所以现在每一项带的是「怎么开始」而不是「在哪儿」：
 *   - `needs`  开始之前要先选什么：一本书 / 一本已分析的书 / 一个书单 / 什么都不用
 *   - `cta`    按钮上写什么
 *   - `to`     选好之后去哪儿（拿到目标 id 拼路径）
 *  界面照着这些字段直接渲染成一个能按的按钮。
 */
export type Tier = "free" | "pro" | "mixed";
export type Scope = "book" | "library";
export type BookKind = "fiction" | "reference" | "any";
/** 开始这件事之前要先选中什么。`none`＝直接就能进。 */
export type Needs = "none" | "book" | "analyzed_book" | "collection";

export type Capability = {
  key: string;
  name: string;
  what: string;
  tier: Tier;
  /** 部分收费时：免费到哪儿为止。tier 不是 mixed 时为空。 */
  free: string;
  /** 付费买到哪一步。tier 为 free 时为空。 */
  paid: string;
  /** 开始之前要先选什么。 */
  needs: Needs;
  /** 按钮上的字。写「点完会发生什么」，不写功能名。 */
  cta: string;
  /** 选好目标之后去哪儿。`id` 是选中的书或书单。 */
  to: ((id: number) => string) | string | null;
  scope: Scope;
  /** 这个入口能接哪类书。非 book 能力固定为 any。 */
  bookKind: BookKind;
  status: "available" | "engine_required";
};

export const CAPABILITIES: Capability[] = [
  // ── 一本书之内 ──────────────────────────────────────────────
  // 这三条原来挤成一张卡叫「三种读法」——那是我从代码里搬出来的内部叫法
  // （实现上它们确实是同一条流水线的三个模式）。但对用户来说是三件事、三种人：
  // **一个想「评测我的稿子」的人，不会在「三种读法」四个字里认出自己。**
  // 而且「读法」对评测就是错的——他不是在读，是在让人诊断自己的稿子。
  {
    key: "diagnostic",
    name: "评测",
    what: "看自己的书：该改哪里、为什么、动的时候不能损伤什么。",
    tier: "free",
    free: "",
    paid: "",
    needs: "book",
    cta: "开始评测",
    to: (id: number) => `/books/${id}/whole-book?mode=diagnostic`,
    scope: "book",
    bookKind: "fiction",
    status: "available",
  },
  {
    key: "story_breakdown",
    name: "拆文",
    what: "看别人的书：起承转合、爆点在哪、钩子怎么下。不打分。",
    tier: "free",
    free: "",
    paid: "",
    needs: "book",
    cta: "开始拆文",
    to: (id: number) => `/books/${id}/whole-book?mode=story_breakdown`,
    scope: "book",
    bookKind: "fiction",
    status: "available",
  },
  {
    key: "comprehend",
    name: "读懂",
    what: "看不是小说的书：专著、教材、工具书。读英文原书也出中文。",
    tier: "free",
    free: "",
    paid: "",
    needs: "book",
    cta: "开始读懂",
    to: (id: number) => `/books/${id}/whole-book?mode=comprehend`,
    scope: "book",
    bookKind: "reference",
    status: "available",
  },
  {
    key: "material_lab",
    name: "题材知识库",
    what: "浏览、分类和检索已经沉淀的题材知识，例如悬疑线索、种田天气和作物种植。",
    tier: "free",
    free: "",
    // 这一条值得单独说：产品里每个实质功能都要花用户的模型钱，只有它不花。
    paid: "",
    needs: "none",
    cta: "打开知识库",
    to: "/knowledge",
    scope: "library",
    bookKind: "fiction",
    status: "available",
  },
  {
    key: "knowledge_extraction",
    name: "从全书提取素材",
    what: "从已经完成全文拆文的小说中，按题材和固定分类沉淀少量、可核对的知识素材。",
    tier: "pro",
    free: "",
    paid: "单本提取、重新提取，以及后续批量沉淀",
    needs: "none",
    cta: "管理全书来源",
    to: "/knowledge",
    scope: "library",
    bookKind: "fiction",
    status: "available",
  },
  {
    key: "book_skill_generation",
    name: "生成作品 Skill",
    what: "把一本全文拆完的小说整理成可下载的创作机制 Skill，不复制原文与专有设定。",
    tier: "pro",
    free: "",
    paid: "选择全书来源、生成并下载 SKILL.md",
    needs: "none",
    cta: "选择一本书生成 Skill",
    to: "/knowledge?view=skill",
    scope: "library",
    bookKind: "fiction",
    status: "available",
  },
  {
    key: "advanced_export",
    // 这一条不起花名。「导出 PDF」本来就是白话，配个名字只会让它变假。
    name: "报告导出",
    what: "把分析结果导成一份能发出去、能存档的文件。",
    tier: "mixed",
    free: "HTML，内容一样，可以自己在浏览器里打印",
    paid: "PDF：中文字体、页边距、页码",
    needs: "analyzed_book",
    cta: "打开报告去导出",
    to: (id: number) => `/books/${id}/whole-book`,
    scope: "book",
    bookKind: "any",
    status: "available",
  },

  // ── 跨越整个书库 ────────────────────────────────────────────
  {
    key: "common_patterns",
    // 「共同套路」是用户自己给的名字。我拿着它又造了个「归纳套路」，是多此一举。
    name: "共同套路",
    what: "几本一起看，重复出现的招才是套路。",
    tier: "mixed",
    free: "类型分布、每本读到第几章、哪几本还没拆过文——这一屏是数出来的，可以逐条回到原书核对",
    // 原来这里拿两个自造例子当解释，用户说「这写的太AI了」。
    // 换成说清楚它替你干了什么：合并同类项。
    paid: "说法不一样、其实是同一招的，给你并到一起",
    // 不再要求「先选一个书单」——挑书是共性视图自己的第一步。
    needs: "none",
    cta: "挑几本书来比",
    to: "/patterns",
    scope: "library",
    bookKind: "any",
    status: "available",
  },
  {
    key: "cross_book_search",
    // 「跨书」是实现细节。问他「按意思找是找啥」时，他自己的回答是「找参考？」——
    // 那就是它的名字，不需要我再翻译一遍。
    name: "找参考",
    what: "从已经分析过的小说里找原句、定位案例，或者说个效果、看谁这么写过。",
    tier: "mixed",
    free: "关键词，找书里出现过的字",
    paid: "找参考：说个效果，看你库里谁这么写过",
    needs: "none",
    cta: "去找参考",
    to: "/search",
    scope: "library",
    bookKind: "any",
    status: "available",
  },
  {
    key: "chapter_aggregate_insights",
    name: "章节聚合洞察",
    what: "把逐章的精细分析聚合成整书结论。",
    tier: "pro",
    free: "",
    paid: "把逐章的精细分析聚合成整书结论",
    needs: "none",
    cta: "",
    to: null,
    scope: "book",
    bookKind: "any",
    status: "engine_required",
  },
];

/** 已经能用的那几项。界面默认只展示这些——把跑不起来的东西混在能用的里面，
 *  就是这份清单当初撒谎的方式。 */
export const SHIPPED_CAPABILITIES = CAPABILITIES.filter((c) => c.status === "available");

/** 要钱的那几项。设置页和「已激活」状态用得到。 */
export const PAID_CAPABILITIES = SHIPPED_CAPABILITIES.filter((c) => c.tier !== "free");

export function capabilityByKey(key: string): Capability | undefined {
  return CAPABILITIES.find((c) => c.key === key);
}

export function capabilityAcceptsBook(
  capability: Capability,
  materialKind: "fiction" | "reference",
): boolean {
  return capability.bookKind === "any" || capability.bookKind === materialKind;
}

/** 免费版保留的完整创作闭环。设置页和能力页共用，避免两处口径漂移。 */
export const FREE_FEATURE_LINES: ReadonlyArray<{ label: string; line: string }> = [
  {
    label: "导入与阅读",
    line: "导入书籍、识别章节、阅读正文和确认作品画像",
  },
  {
    label: "单章分析",
    line: "识别场景、人工调整边界，再查看人物、冲突和阅读节奏",
  },
  {
    label: "全书分析",
    line: "评测、拆文和读懂三种完整分析流程",
  },
  {
    label: "基础资料与导出",
    line: "浏览知识库、关键词检索，以及导出可打印的 HTML",
  },
];

/** 专业版买到的五项能力。
 *
 *  用户点右上角「StoryLens 免费版 ›」时，他想知道的是**掏钱买什么**，
 *  而不是想看一张目录。之前那一页先给他三张免费的卡、付费的沉在最下面、
 *  每张还挂着两行「免费…专业版…」的解释——他的原话是
 *  「这个页面是不是全是没头没尾的废话」。
 *
 *  这五行答的就是那一句。看完就能决定要不要买，不用往下翻。
 *  **注意最后一条没有花名**：「导出 PDF」本来就是白话，给它配个名字只会让它变假。
 */
export const PAID_FEATURE_LINES: ReadonlyArray<{ label: string; line: string; key: string }> = [
  {
    key: "knowledge_extraction",
    label: "从全书提取素材",
    line: "把拆完的小说沉淀成分类明确、能回原文核对的知识",
  },
  {
    key: "book_skill_generation",
    label: "生成作品 Skill",
    line: "把完整拆解结论整理成可下载、可执行的创作规范",
  },
  {
    key: "common_patterns",
    label: "共同套路",
    line: "说法不一样、其实是同一招的，给你并到一起",
  },
  {
    key: "cross_book_search",
    label: "找参考",
    line: "说个效果，看你库里谁这么写过",
  },
  {
    key: "advanced_export",
    label: "导出 PDF",
    line: "中文字体、页边距、页码",
  },
];
