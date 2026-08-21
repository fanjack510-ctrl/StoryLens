from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CloudBudgetReservation, ModelInvocation, RequestGateDecision


class RequestBlockedError(RuntimeError):
    """Raised when a cloud attempt is blocked by master switch or budget gates."""

    def __init__(self, reason_code: str, *, details: dict | None = None):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.details = dict(details or {})

    def as_safe_dict(self) -> dict[str, object]:
        """Technical details for persistence / UI — never includes API keys."""
        safe_keys = {
            "error_type",
            "error_code",
            "used",
            "used_requests",
            "used_tokens",
            "used_cost",
            "reserved_initial",
            "reserved_remaining",
            "reserved_consumed",
            "daily_limit",
            "requested_amount",
            "run_id",
            "reservation_id",
            "dimension",
        }
        out: dict[str, object] = {
            "error_type": "RequestBlockedError",
            "error_code": self.reason_code,
        }
        for key, value in self.details.items():
            if key in safe_keys and value is not None:
                out[key] = value
        return out


def active_reservation_remaining_totals(session: Session) -> tuple[int, int, float]:
    """Sum *remaining* (not initial) across active, unexpired reservations."""
    now = datetime.now(timezone.utc)
    row = session.execute(
        select(
            func.coalesce(func.sum(CloudBudgetReservation.remaining_requests), 0),
            func.coalesce(func.sum(CloudBudgetReservation.remaining_tokens), 0),
            func.coalesce(func.sum(CloudBudgetReservation.remaining_cost), 0.0),
        ).where(
            CloudBudgetReservation.status == "active",
            CloudBudgetReservation.expires_at > now,
        )
    ).one()
    return int(row[0]), int(row[1]), float(row[2])


def daily_usage(session: Session, budget: dict, cloud_enabled: bool, pricing: dict) -> dict:
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    row = session.execute(
        select(
            func.count(ModelInvocation.id),
            func.coalesce(func.sum(ModelInvocation.input_tokens), 0),
            func.coalesce(func.sum(ModelInvocation.output_tokens), 0),
            func.coalesce(func.sum(ModelInvocation.total_tokens), 0),
            func.coalesce(func.sum(ModelInvocation.estimated_cost), 0.0),
        ).where(
            ModelInvocation.is_cloud.is_(True),
            ModelInvocation.http_request_sent.is_(True),
            ModelInvocation.created_at >= start,
        )
    ).one()
    requests, input_tokens, output_tokens, total_tokens, cost = row
    blocked = (
        session.scalar(
            select(func.count())
            .select_from(RequestGateDecision)
            .where(
                RequestGateDecision.allowed.is_(False),
                RequestGateDecision.created_at >= start,
            )
        )
        or 0
    )
    reserved_requests, reserved_tokens, reserved_cost = active_reservation_remaining_totals(
        session
    )
    remaining_requests = max(0, int(budget["cloud_daily_request_limit"]) - int(requests))
    remaining_tokens = max(0, int(budget["cloud_daily_token_limit"]) - int(total_tokens))
    remaining_cost = round(
        max(0.0, float(budget["cloud_daily_estimated_cost_limit"]) - float(cost)), 6
    )
    # committed = used + sum(active remaining); available = daily - committed
    committed_requests = int(requests) + reserved_requests
    committed_tokens = int(total_tokens) + reserved_tokens
    committed_cost = round(float(cost) + reserved_cost, 6)
    reasons = cloud_block_reasons(
        cloud_enabled, budget, pricing, int(requests), int(total_tokens), float(cost)
    )
    return {
        "date": today.isoformat(),
        "request_count": int(requests),
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(total_tokens),
        "estimated_cost": round(float(cost), 6),
        "currency": str(budget["currency"]),
        "remaining_requests": remaining_requests,
        "remaining_tokens": remaining_tokens,
        "remaining_estimated_cost": remaining_cost,
        # reserved_* = sum of active reservation *remaining* (not initial)
        "reserved_requests": reserved_requests,
        "reserved_tokens": reserved_tokens,
        "reserved_estimated_cost": round(reserved_cost, 6),
        "committed_requests": committed_requests,
        "committed_tokens": committed_tokens,
        "committed_estimated_cost": committed_cost,
        "available_requests": max(
            0, int(budget["cloud_daily_request_limit"]) - committed_requests
        ),
        "available_tokens": max(0, int(budget["cloud_daily_token_limit"]) - committed_tokens),
        "available_estimated_cost": round(
            max(0.0, float(budget["cloud_daily_estimated_cost_limit"]) - committed_cost), 6
        ),
        "within_budget": not reasons,
        "blocked_reasons": reasons,
        "blocked_gate_count": int(blocked),
    }


def cloud_block_reasons(
    cloud_enabled: bool,
    budget: dict,
    pricing: dict,
    requests: int = 0,
    tokens: int = 0,
    cost: float = 0.0,
) -> list[str]:
    reasons: list[str] = []
    if not cloud_enabled:
        reasons.append("云端总开关已关闭")
    if not budget["cloud_request_budget_enabled"]:
        reasons.append("云端预算保护未启用")
    if budget["cloud_stop_on_unknown_pricing"] and not pricing["enabled"]:
        reasons.append("价格未知或尚未验证")
    # 只有钱能拦人。
    #
    # 这里原先还有请求数和 Token 两道日闸。它们量的是同一件事的另外两种单位——用得多就是
    # 花得多——却各自独立地拦，于是出现了实际只花了 ¥1.7、费用额度 ¥50 一分没动，却因为
    # Token 到顶而无法分析的情况。而屏幕上只写「当前额度不足」，三条里撞了哪条都不说。
    #
    # 用量仍然逐项统计并展示（请求数、Token、费用都在 usage 里），只是不再各自设闸：
    # 想知道用了多少，看得到；能不能继续，只问钱。
    if cost >= budget["cloud_daily_estimated_cost_limit"]:
        reasons.append(
            f"今日估算费用已达上限（{budget['currency']} {cost:.2f} / "
            f"{budget['cloud_daily_estimated_cost_limit']:.2f}），明天零点重置"
        )
    return reasons
