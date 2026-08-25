import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { entitlementApi } from "../../services/entitlementApi";
import { ENTITLEMENTS_QUERY_KEY } from "../../services/productEdition";

/** 一个功能是不是要钱，得写在那个功能旁边。
 *
 *  之前「专业版」三个字在整个产品里只出现在 `/pro` 那一页和设置里——真正能点到的
 *  地方（共性视图按钮、按意思找、PDF 导出）一个标记都没有。做一个目录页不等于
 *  让用户知道专业版有什么：他不会先去读目录再来用产品，他是在用的时候撞见的。
 *
 *  所以这个标记有两个职责，缺一不可：
 *   1. **在场**——站在按钮旁边，回答「这个要钱吗」
 *   2. **可点**——点开就是那一项的说明（免费到哪儿 / 付费买什么），而不是一个死徽章
 *
 *  已激活的人看到的是「已激活」而不是「PRO」。对他来说这个标记的意思从
 *  「你还没买」变成「这一项你买到了」——同一个位置，不同的话。
 */
export function ProTag({ capability, className = "" }: { capability: string; className?: string }) {
  const entitlement = useQuery({
    queryKey: ENTITLEMENTS_QUERY_KEY,
    queryFn: entitlementApi.snapshot,
    retry: false,
  });

  // 查询还没回来时先按未激活渲染，但**不说「未解锁」**——只显示中性的「PRO」。
  // 「还不知道」不能当成「没有」，那是这个代码库里反复犯过的同一个错。
  const isPro = entitlement.data?.pro_active === true;

  return (
    <Link
      to={`/capabilities#pro-item-${capability}`}
      className={`pro-tag ${isPro ? "is-active" : ""} ${className}`.trim()}
      data-testid={`pro-tag-${capability}`}
      title={isPro ? "专业版功能 · 你已激活，点击查看说明" : "专业版功能 · 点击看它做什么、免费到哪儿为止"}
    >
      {isPro ? "PRO · 已激活" : "PRO"}
    </Link>
  );
}
