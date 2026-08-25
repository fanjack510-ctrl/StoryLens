import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  CAPABILITIES,
  capabilityAcceptsBook,
  FREE_FEATURE_LINES,
  PAID_FEATURE_LINES,
  SHIPPED_CAPABILITIES,
  type Capability,
} from "../services/capabilityCatalog";
import { entitlementApi } from "../services/entitlementApi";
import { ENTITLEMENTS_QUERY_KEY } from "../services/productEdition";
import { booksApi } from "../services/booksApi";
import { collectionsApi } from "../services/collectionsApi";
import { PageHeader, PageSubtitle, PageTitle } from "../components/ui/PageHeader";

/** 这个产品能做什么——**而且在这儿就能开始做**。
 *
 *  这一页改过两次，两次都被同一句话打回来。
 *
 *  第一版叫「专业版能做什么」，只列收费项。用户说「作为用户根本不知道到底能干哪些功能」。
 *
 *  第二版列全了，但每项跟一句「位置：书库 → 打开任意一本书」。用户说：
 *  「我都不知道你想表达啥，像一页说明书。正常的工具不是应该有个功能标签，
 *  点进去然后引导怎么操作，不就完了吗」——他是对的。
 *  **告诉人往哪儿走，和让人点一下就开始，是两回事。**一张写着路线的纸不是入口。
 *
 *  所以现在每张卡上：要选书的就地选书，要选书单的就地选书单，然后一个按钮进去干活。
 *  没有「位置」那一栏了——能点的按钮本身就是位置。
 */
const SCOPE_TITLE: Record<Capability["scope"], string> = {
  book: "对着一本书做的",
  library: "对着整个书库做的",
};

/** 部分收费的那几项，标签直接点名**是哪一步**收费。
 *
 *  原来写的是「免费 + PRO」——那要求用户自己去猜这个功能哪半边要钱。
 *  写清楚是哪一步，他就不用猜了。 */
const PAID_STEP: Record<string, string> = {
  common_patterns: "并到一起那步是 PRO",
  cross_book_search: "找参考是 PRO",
  advanced_export: "PDF 是 PRO",
};

function TierChip({ cap }: { cap: Capability }) {
  if (cap.tier === "free") return <em className="free-tag">免费</em>;
  if (cap.tier === "pro") return <em className="pro-tag-static">PRO</em>;
  return <em className="pro-tag-static">{PAID_STEP[cap.key] || "部分是 PRO"}</em>;
}

/** 一张卡的动作区：先选对象（如果需要），再一个按钮进去。 */
function Launcher({ cap }: { cap: Capability }) {
  const navigate = useNavigate();
  const [target, setTarget] = useState<string>("");

  const needsBook = cap.needs === "book" || cap.needs === "analyzed_book";
  const books = useQuery({
    queryKey: ["library"],
    queryFn: booksApi.library,
    enabled: needsBook,
  });
  const collections = useQuery({
    queryKey: ["collections"],
    queryFn: collectionsApi.list,
    enabled: cap.needs === "collection",
  });

  if (cap.needs === "none") {
    const to = typeof cap.to === "string" ? cap.to : null;
    if (!to) return null;
    return (
      <div className="cap-launch">
        <Link className="primary" to={to} data-testid={`cap-go-${cap.key}`}>
          {cap.cta} →
        </Link>
      </div>
    );
  }

  const options = needsBook
    ? (books.data ?? [])
        .filter((b) => capabilityAcceptsBook(cap, b.material_kind))
        // 「打开报告去导出」要的是**已经分析过**的书。列出没分析过的，
        // 等于让人点进去撞一堵墙。
        .filter((b) => cap.needs !== "analyzed_book" || b.analysis_state === "done")
        .map((b) => ({ id: b.id, label: b.title }))
    : (collections.data ?? []).map((c) => ({ id: c.id, label: c.name }));

  const pending = needsBook ? books.isPending : collections.isPending;

  // 「还不知道」和「没有」是两回事。查询没回来时不能说「你还没有书」——
  // 这个代码库里反复犯过这个错。
  if (pending) {
    return (
      <div className="cap-launch">
        <span className="muted">正在读…</span>
      </div>
    );
  }

  if (options.length === 0) {
    const [hint, to, label] =
      cap.needs === "collection"
        ? ["还没有书单。共性视图比的是一组书，得先圈定是哪一组。", "/library?new-collection=1", "去建一个书单"]
        : cap.needs === "analyzed_book"
          ? ["还没有分析完的书。先跑一次分析，才有报告可导。", "/library", "去书库挑一本分析"]
          : ["书库还是空的。", "/library", "去导入一本书"];
    return (
      <div className="cap-launch cap-launch--empty">
        <span className="muted">{hint}</span>
        <Link className="secondary" to={to} data-testid={`cap-empty-${cap.key}`}>
          {label} →
        </Link>
      </div>
    );
  }

  const go = () => {
    const id = Number(target || options[0].id);
    const to = typeof cap.to === "function" ? cap.to(id) : cap.to;
    if (to) navigate(to);
  };

  return (
    <div className="cap-launch">
      <select
        value={target || String(options[0].id)}
        onChange={(e) => setTarget(e.target.value)}
        aria-label={cap.needs === "collection" ? "选一个书单" : "选一本书"}
        data-testid={`cap-pick-${cap.key}`}
      >
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
      <button type="button" className="primary" onClick={go} data-testid={`cap-go-${cap.key}`}>
        {cap.cta} →
      </button>
    </div>
  );
}

function CapabilityItem({ cap, isPro }: { cap: Capability; isPro: boolean }) {
  return (
    <li className="cap-item" id={`pro-item-${cap.key}`} data-testid={`cap-item-${cap.key}`}>
      <div className="cap-item-head">
        <b>{cap.name}</b>
        <TierChip cap={cap} />
        {isPro && cap.tier !== "free" ? <span className="pro-badge on">已激活</span> : null}
      </div>
      <p className="cap-what">{cap.what}</p>

      {/* 每张卡两行封顶：一句它是什么，一个能按的按钮。
          原来这里还有「免费…／专业版…」两行——那个分界顶上已经说过一次，
          每张卡再重复一遍就是废话。用户的原话：「是不是全是没头没尾的废话」。 */}
      <Launcher cap={cap} />
    </li>
  );
}

export function CapabilitiesPage() {
  const entitlement = useQuery({
    queryKey: ENTITLEMENTS_QUERY_KEY,
    queryFn: entitlementApi.snapshot,
    retry: false,
  });
  const isPro = entitlement.data?.pro_active === true;
  const afdian = entitlement.data?.commerce?.afdian_product_url || "";

  const groups: Capability["scope"][] = ["book", "library"];

  return (
    <section className="page cap-page" data-testid="capabilities-page">
      <PageHeader>
        <div>
          <PageTitle>能做什么</PageTitle>
          <PageSubtitle>
            {isPro
              ? "专业版已激活。挑一件开始。"
              : "挑一件开始。大部分免费，带 PRO 的写清楚了免费到哪儿、付费买什么。"}
          </PageSubtitle>
        </div>
        <Link className="secondary" to="/library" data-testid="cap-back">
          回书库
        </Link>
      </PageHeader>

      {/* 已激活的人要看的是「我买到了什么、什么时候激活的」，不是销售页。
          **没有到期时间**——`/api/v1/entitlements` 不返回这个字段。宁可不显示，
          也不编一个：错的到期日会让人在还能用的时候以为过期了。 */}
      {isPro ? (
        <div className="pro-status" data-testid="pro-status">
          <dl>
            <div>
              <dt>版本</dt>
              <dd>{entitlement.data?.edition_label || "专业版"}</dd>
            </div>
            {entitlement.data?.license_id_masked ? (
              <div>
                <dt>授权号</dt>
                <dd>{entitlement.data.license_id_masked}</dd>
              </div>
            ) : null}
            {entitlement.data?.activated_at ? (
              <div>
                <dt>激活于</dt>
                <dd>{new Date(entitlement.data.activated_at).toLocaleDateString()}</dd>
              </div>
            ) : null}
          </dl>
          <Link to="/settings?tab=license">授权详情与更换 →</Link>
        </div>
      ) : null}

      {/* 没买的人一进来先看这五行：掏钱买什么。
          之前他点右上角的版本徽章进来，先看到三张免费的卡，付费的沉在最下面。 */}
      {!isPro ? (
        <div className="paid-three" data-testid="paid-three">
          <div className="paid-three-head">
            <b>专业版解锁 5 项创作能力</b>
            {afdian ? (
              <a href={afdian} target="_blank" rel="noreferrer" className="primary">
                了解专业版
              </a>
            ) : null}
          </div>
          <dl>
            {PAID_FEATURE_LINES.map((row) => (
              <div key={row.key}>
                <dt>{row.label}</dt>
                <dd>{row.line}</dd>
              </div>
            ))}
          </dl>
          <p className="muted">
            免费版保留 {FREE_FEATURE_LINES.map((row) => row.label).join("、")}。
          </p>
        </div>
      ) : null}

      {groups.map((scope) => (
        <div className="cap-group" key={scope} data-testid={`cap-group-${scope}`}>
          <h2>{SCOPE_TITLE[scope]}</h2>
          <ol className="cap-list">
            {SHIPPED_CAPABILITIES.filter((c) => c.scope === scope).map((cap) => (
              <CapabilityItem key={cap.key} cap={cap} isPro={isPro} />
            ))}
          </ol>
        </div>
      ))}

      {/* 跑不起来的不混在能用的里面——那正是这份清单当初撒谎的方式。 */}
      {CAPABILITIES.some((c) => c.status === "engine_required") ? (
        <p className="muted pro-note" data-testid="pro-not-shipped">
          另有「章节聚合洞察」需要私有分析引擎，当前打包版未包含，因此不在上面。
        </p>
      ) : null}

      {/* 「了解专业版」已经在顶上那块里了。同一页说两遍，第二遍就是噪音。
          这里只留激活入口——它回答的是另一个问题：我已经买了，怎么用上。 */}
      {!isPro ? (
        <div className="pro-cta" data-testid="pro-cta">
          <Link to="/settings?tab=license">已经有授权码 → 去激活</Link>
        </div>
      ) : null}
    </section>
  );
}
