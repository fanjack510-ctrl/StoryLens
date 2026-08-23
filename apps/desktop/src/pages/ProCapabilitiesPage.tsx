import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { PRO_CAPABILITIES, SHIPPED_PRO_CAPABILITIES } from "../services/proCatalog";
import { entitlementApi } from "../services/entitlementApi";
import { PageHeader, PageSubtitle, PageTitle } from "../components/ui/PageHeader";

/** 专业版能做什么。
 *
 *  这一页存在的原因很直接：用户装好之后连着问了两次「为啥没有 pro 的功能」。
 *  四个付费功能当时全藏在流程内部——共性视图要先选中一个书单才出现，
 *  「按意思找」要先搜一次才出现，PDF 导出在报告页右上角。**一个新装的用户
 *  永远不会知道它们存在。**
 *
 *  我一路守着「不到该收钱的地方不提钱」，做出来的结果是不打扰过了头。
 *  这一页是补上那一课：不弹窗、不打断，但要有一个地方能一次看完
 *  「免费到哪儿为止、付费买到什么、在哪儿能找到它」。
 */
export function ProCapabilitiesPage() {
  const entitlement = useQuery({
    queryKey: ["entitlement"],
    queryFn: entitlementApi.snapshot,
    retry: false,
  });
  const isPro = entitlement.data?.pro_active === true;
  const afdian = entitlement.data?.commerce?.afdian_product_url || "";

  return (
    <section className="page pro-page" data-testid="pro-capabilities-page">
      <PageHeader>
        <div>
          <PageTitle>专业版能做什么</PageTitle>
          <PageSubtitle>
            {isPro
              ? "已激活。下面每一项都可以用了。"
              : "大部分功能免费。这里列清楚每一项免费到哪儿、付费买到什么。"}
          </PageSubtitle>
        </div>
        <Link className="secondary" to="/library" data-testid="pro-back">
          回书库
        </Link>
      </PageHeader>

      <ol className="pro-list">
        {SHIPPED_PRO_CAPABILITIES.map((cap) => (
          <li key={cap.key} className="pro-item" data-testid={`pro-item-${cap.key}`}>
            <div className="pro-item-head">
              <b>{cap.name}</b>
              {isPro ? <span className="pro-badge on">已激活</span> : null}
            </div>
            {cap.free ? (
              <p className="pro-free">
                <span>免费</span>
                {cap.free}
              </p>
            ) : null}
            <p className="pro-paid">
              <span>专业版</span>
              {cap.paid}
            </p>
            {/* 「在哪儿能找到它」是这一页最要紧的一栏——功能藏在流程里正是当初的问题。 */}
            <p className="pro-where">
              位置：
              {cap.href ? (
                <Link to={cap.href}>{cap.where}</Link>
              ) : (
                <span>{cap.where}</span>
              )}
            </p>
          </li>
        ))}
      </ol>

      {/* 跑不起来的东西不混在能用的里面卖——那正是这份清单当初撒谎的方式。 */}
      {PRO_CAPABILITIES.some((c) => c.status === "engine_required") ? (
        <p className="muted pro-note" data-testid="pro-not-shipped">
          另有「章节聚合洞察」需要私有分析引擎，当前打包版未包含，因此不在上面的清单里。
        </p>
      ) : null}

      {!isPro && afdian ? (
        <div className="pro-cta" data-testid="pro-cta">
          <a href={afdian} target="_blank" rel="noreferrer" className="primary">
            了解专业版
          </a>
          <Link to="/settings?tab=license">已经有授权码 → 去激活</Link>
        </div>
      ) : null}
    </section>
  );
}
