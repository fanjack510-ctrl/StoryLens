import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { buildMockWholeBookAnalysisV2 } from "./mockAdapter";
import { WholeBookV2ReportView } from "./presentation/WholeBookV2ReportView";
import type { JourneyResult, WholeBookAnalysisV2 } from "./contracts";

afterEach(cleanup);

const journey = (over: Partial<JourneyResult>): JourneyResult => ({
  availability: "available",
  axis: "none",
  axis_label: "",
  lead: "",
  ticks: [],
  points: [],
  bands: [],
  bins: 0,
  caveat: "",
  ...over,
});

const withJourney = (j?: JourneyResult): WholeBookAnalysisV2 => ({
  ...buildMockWholeBookAnalysisV2(),
  ...(j ? { journey: j } : {}),
});

const show = (data: WholeBookAnalysisV2) =>
  render(
    <WholeBookV2ReportView
      data={data}
      activeModule="characters"
      onModuleChange={() => {}}
      mode="formal"
    />,
  );

/** The 人物 module opens on 人物系统; the journey lives behind its own tab. */
const openJourney = (data: WholeBookAnalysisV2, tabName: string) => {
  const rendered = show(data);
  fireEvent.click(screen.getByRole("button", { name: tabName }));
  return rendered;
};

describe("人物页的历程子页签由引擎选的轴决定", () => {
  // The tab is *named* after the axis, not fixed to 「主角历程」. A reader opening a mystery
  // and a progression novel should be able to tell from the tab alone that they are looking
  // at two different measurements, not the same chart with different numbers.
  it("悬疑书拿到认知历程", () => {
    show(withJourney(journey({ axis: "cognition", axis_label: "认知度" })));
    expect(screen.getByRole("button", { name: "认知历程" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "主角历程" })).not.toBeInTheDocument();
  });

  it("升级流拿到升级历程", () => {
    show(withJourney(journey({ axis: "ladder", axis_label: "阶位" })));
    expect(screen.getByRole("button", { name: "升级历程" })).toBeInTheDocument();
  });

  it("群像拿到戏份分布", () => {
    show(withJourney(journey({ axis: "screen_time", axis_label: "戏份占比" })));
    expect(screen.getByRole("button", { name: "戏份分布" })).toBeInTheDocument();
  });

  it("没有轴时退回阶段列表，不画任何曲线", () => {
    show(withJourney(journey({ axis: "none", availability: "unavailable" })));
    expect(screen.getByRole("button", { name: "主角历程" })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /认知度|阶位|戏份/ })).not.toBeInTheDocument();
  });

  it("旧文档没有 journey 字段时不报错，照旧显示主角历程", () => {
    // Every document produced before this section existed lacks the field entirely. It must
    // degrade to the stage list rather than throw on `journey.axis`.
    show(withJourney(undefined));
    expect(screen.getByRole("button", { name: "主角历程" })).toBeInTheDocument();
  });
});

describe("历程图本身", () => {
  const ladder = journey({
    axis: "ladder",
    axis_label: "阶位",
    lead: "陈伶",
    ticks: ["1阶", "2阶", "3阶"],
    caveat: "主线只走「晋升」类读数。",
    points: [
      { chapter: 41, value: 1, label: "第一阶", kind: "promote", who: "陈伶", note: "登临第一阶", load_bearing: true, evidence: [] },
      { chapter: 171, value: 3, label: "三阶", kind: "gain", who: "陈伶", note: "获得三阶技能", load_bearing: false, evidence: [] },
      { chapter: 324, value: 2, label: "第二阶", kind: "promote", who: "陈伶", note: "晋升第二阶", load_bearing: true, evidence: [] },
      // 引擎标的：一次重伤濒死是下跌，哪怕它记在的那个阶位没有变。数值比较看不出这件事。
      { chapter: 807, value: 2, label: "", kind: "setback", who: "陈伶", note: "重伤濒死", load_bearing: false, down: true, evidence: [] },
    ],
  });

  it("画出全部读数，但主线只连 load_bearing 的点", () => {
    const { container } = openJourney(withJourney(ladder), "升级历程");
    expect(container.querySelectorAll(".wb2-journey-dot")).toHaveLength(4);
    expect(container.querySelectorAll(".wb2-journey-dot.lead")).toHaveLength(2);
    const path = container.querySelector(".wb2-journey-line")?.getAttribute("d") ?? "";
    // Two connected readings step once: a move across, then a move up.
    expect(path.match(/L /g) ?? []).toHaveLength(2);
  });

  it("下跌的点单独标出来", () => {
    const { container } = openJourney(withJourney(ladder), "升级历程");
    expect(container.querySelectorAll(".wb2-journey-dot.down")).toHaveLength(1);
    expect(screen.getByText(/共 4 个读数，其中下跌 1 次/)).toBeInTheDocument();
  });

  // 这次改动之前生成的报告里没有 down 这个字段。累计型的轴上，值降了就是跌了——所以旧报告
  // 也不会退化成「下跌 0 次」，而这正是关系亲疏那条轴刚上线时的样子。
  it("旧报告没有 down 字段时，按数值判断跌在哪", () => {
    const legacy = {
      availability: "available" as const,
      axis: "relationship" as const,
      axis_label: "关系亲疏",
      lead: "甲",
      ticks: ["最疏远", "最亲近"],
      caveat: "",
      bands: [],
      bins: 0,
      points: [
        { chapter: 5, value: 2, label: "", kind: "warm", who: "乙", note: "缓和", load_bearing: true, evidence: [] },
        { chapter: 20, value: -1, label: "", kind: "rift", who: "乙", note: "吵翻", load_bearing: true, evidence: [] },
        { chapter: 56, value: 3, label: "", kind: "commit", who: "乙", note: "在一起", load_bearing: true, evidence: [] },
      ],
    };
    const { container } = openJourney(withJourney(legacy as never), "关系历程");
    expect(container.querySelectorAll(".wb2-journey-dot.down")).toHaveLength(1);
    expect(screen.getByText(/共 3 个读数，其中下跌 1 次/)).toBeInTheDocument();
  });

  it("后端给的 caveat 原样显示，不由前端决定说不说", () => {
    openJourney(withJourney(ladder), "升级历程");
    expect(screen.getByText("主线只走「晋升」类读数。")).toBeInTheDocument();
  });

  it("戏份分布把每个人画成一条带子并列出跨度", () => {
    const { container } = openJourney(
      withJourney(
        journey({
          axis: "screen_time",
          axis_label: "戏份占比",
          bins: 3,
          bands: [
            { name: "邓肯", share: [1, 0.5, 0.4], first_chapter: 3, last_chapter: 806, chapters: 451, total: 480 },
            { name: "凡娜", share: [0, 0.5, 0.6], first_chapter: 29, last_chapter: 806, chapters: 127, total: 130 },
          ],
        }),
      ),
      "戏份分布",
    );
    expect(container.querySelectorAll(".wb2-band")).toHaveLength(2);
    expect(screen.getByText("邓肯")).toBeInTheDocument();
    expect(screen.getByText("451 章")).toBeInTheDocument();
  });
});

describe("每程的账本", () => {
  const withLedger = journey({
    axis: "screen_time",
    axis_label: "戏份占比",
    bins: 2,
    bands: [
      { name: "邓肯", share: [1, 1], first_chapter: 1, last_chapter: 800, chapters: 400, total: 400 },
    ],
    ledger: [
      {
        stage_name: "失乡号启航",
        chapter_start: 1,
        chapter_end: 144,
        met: [{ chapter: 9, name: "爱丽丝", relation: "从敌对到接纳为船员" }],
        met_total: 10,
        did: [{ chapter: 4, text: "邓肯握住舵轮，绿火燃起" }],
        did_total: 93,
        gained: ["发现罗盘是异常物品"],
        gained_total: 21,
        lost: [],
        lost_total: 0,
      },
      {
        stage_name: "教堂的谜团",
        chapter_start: 145,
        chapter_end: 288,
        met: [],
        met_total: 0,
        did: [],
        did_total: 71,
        gained: ["拯救城邦"],
        gained_total: 9,
        lost: ["暴露自己与凡娜的联系"],
        lost_total: 2,
      },
    ],
  });

  it("四类账都在，计数是全量而列表是展示的那几条", () => {
    openJourney(withJourney(withLedger), "戏份分布");
    // 做了什么 is the wide timeline; the other three stack beside it. Each heading carries
    // the full tally even though only the load-bearing rows are listed.
    expect(screen.getByText("做了什么 · 93")).toBeInTheDocument();
    expect(screen.getByText("遇见谁 · 10")).toBeInTheDocument();
    expect(screen.getByText("得到 · 21")).toBeInTheDocument();
    expect(screen.getByText("失去 · 0")).toBeInTheDocument();
    expect(screen.getByText("爱丽丝")).toBeInTheDocument();
    expect(
      screen.getByText((_, node) => node?.textContent === "第 9 章 · 从敌对到接纳为船员"),
    ).toBeTruthy();
  });

  it("空栏说清楚是哪一种空，而不是留白", () => {
    // Stage 2 met nobody. An empty cell reads as "not extracted"; the sentence says which.
    openJourney(withJourney(withLedger), "戏份分布");
    fireEvent.click(screen.getByRole("button", { name: /第 2 程/ }));
    expect(screen.getByText("这一程没有新的人")).toBeInTheDocument();
  });

  it("切换到另一程会换掉四栏的内容", () => {
    openJourney(withJourney(withLedger), "戏份分布");
    fireEvent.click(screen.getByRole("button", { name: /第 2 程/ }));
    expect(screen.getByText("暴露自己与凡娜的联系")).toBeInTheDocument();
    expect(screen.getByText("第 145–288 章")).toBeInTheDocument();
    expect(screen.queryByText("发现罗盘是异常物品")).not.toBeInTheDocument();
  });

  it("旧文档没有 ledger 时不渲染这一块", () => {
    openJourney(withJourney(journey({ axis: "screen_time", bands: [] })), "戏份分布");
    expect(screen.queryByText("遇见谁")).not.toBeInTheDocument();
  });
});

describe("节点内容的展开", () => {
  const cognition = journey({
    axis: "cognition",
    axis_label: "认知度",
    ticks: ["什么都不知道", "知道得最多"],
    points: [
      { chapter: 4, value: 1, label: "", kind: "partial", who: "", note: "秦一恒说好像是冤魂", load_bearing: true, evidence: [] },
      { chapter: 28, value: -4, label: "", kind: "twist", who: "", note: "刘瘸子是假冒的", load_bearing: true, evidence: [] },
      { chapter: 45, value: 0, label: "", kind: "resolve", who: "", note: "老板是被水鬼设计", load_bearing: true, evidence: [] },
    ],
  });

  it("点一个点，它的内容显示在图下方，而不是只藏在悬停里", () => {
    const { container } = openJourney(withJourney(cognition), "认知历程");
    fireEvent.click(container.querySelectorAll(".wb2-journey-dot")[1]);
    // The note also appears in the turn list below, so the assertion is scoped to the strip.
    const strip = container.querySelector(".wb2-journey-point-detail");
    expect(strip?.textContent).toContain("刘瘸子是假冒的");
    expect(strip?.textContent).toContain("反转 · 推翻先前认知");
    expect(container.querySelectorAll(".wb2-journey-dot.selected")).toHaveLength(1);
  });

  it("信息量大的节点列成文字清单，partial 不进清单", () => {
    // 31 partial reveals would drown the seven moments that reorganise the book, so only
    // reversals and answers are listed; the partials stay as dots.
    const { container } = openJourney(withJourney(cognition), "认知历程");
    const rows = container.querySelectorAll(".wb2-journey-turns button");
    expect(rows).toHaveLength(2); // twist + resolve, not the partial
    fireEvent.click(rows[1]);
    expect(container.querySelector(".wb2-journey-point-detail")?.textContent).toContain("老板是被水鬼设计");
  });

  it("再点一次收起", () => {
    const { container } = openJourney(withJourney(cognition), "认知历程");
    const dot = container.querySelectorAll(".wb2-journey-dot")[1];
    fireEvent.click(dot);
    fireEvent.click(dot);
    expect(container.querySelector(".wb2-journey-point-detail")).toBeNull();
  });
});
