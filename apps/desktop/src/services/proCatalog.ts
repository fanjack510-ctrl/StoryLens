/** 专业版到底卖什么——一处定义，界面各处都照着它说。
 *
 *  这份清单存在的理由是它之前撒过谎：设置页列着「故事实验台」（产品里没有这个东西）、
 *  「整书分析」（那是**免费**的核心功能），却没有刚做出来的共性视图。一个列了六项、
 *  其中一项能用的清单，比不列更糟——买的人是照着它掏钱的。
 *
 *  所以每一项都带三样东西：**免费到哪儿为止**、**付费买到什么**、**在哪儿能找到它**。
 *  第三样是这一轮才补的：四个付费功能原来全藏在流程内部，一个新装的用户永远不会
 *  知道它们存在。不打扰和不存在之间，之前选过头了。
 */
export type ProCapability = {
  key: string;
  name: string;
  /** 这件事免费能做到哪一步。空字符串＝这件事没有免费的部分。 */
  free: string;
  /** 付费买到的是哪一步。 */
  paid: string;
  /** 在产品里怎么走到它。写给一个刚装好、什么都没试过的人看。 */
  where: string;
  /** 站内路径。没有站内页面（比如需要先有数据）时为 null。 */
  href: string | null;
  status: "available" | "engine_required";
};

export const PRO_CAPABILITIES: ProCapability[] = [
  {
    key: "common_patterns",
    name: "共性视图",
    free: "类型分布、每本读到第几章、哪几本还没拆过文——这一屏是数出来的，可以逐条回到原书核对",
    paid: "把一组书归纳成共同手法：看出「用一句反常识的话立住人物」和「小人物报出真名」做的是同一件事",
    where: "书库 → 选中一个书单 → 看这组书的共性",
    href: "/library",
    status: "available",
  },
  {
    key: "cross_book_search",
    name: "跨书检索 · 按意思找",
    free: "关键词检索，覆盖全部条目（技法、高光片段、章末钩子、逐章功能、原文证据）",
    paid: "用自己的话描述要找的写法，由模型在写法层里挑出来并说明为什么符合——关键词答不了「让主角一出场就打破读者预期」这种问题",
    where: "顶栏 → 检索",
    href: "/search",
    status: "available",
  },
  {
    key: "advanced_export",
    name: "成品报告导出（PDF）",
    free: "HTML 导出——内容完全一样，可以自己打印",
    paid: "排版好的 PDF：中文字体嵌入、纸张边距、页脚页码",
    where: "打开任意一本书的分析报告 → 右上角导出",
    href: null,
    status: "available",
  },
  {
    key: "chapter_aggregate_insights",
    name: "章节聚合洞察",
    free: "",
    paid: "把逐章的精细分析聚合成整书结论",
    where: "需要私有分析引擎，当前打包版未包含",
    href: null,
    status: "engine_required",
  },
];

/** 已经能用的那几项。界面默认只展示这些——把跑不起来的东西混在能用的里面卖，
 *  就是这份清单当初撒谎的方式。 */
export const SHIPPED_PRO_CAPABILITIES = PRO_CAPABILITIES.filter(
  (c) => c.status === "available",
);
