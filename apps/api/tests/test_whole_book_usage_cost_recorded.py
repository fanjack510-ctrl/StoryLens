"""全书分析的每一次调用都要记下价钱——费用是唯一的日闸门，计数器不能是 0。"""
from app.services.cloud_pricing import estimate_cost


def test_a_real_whole_book_call_gets_a_price():
    """171 次云端调用里 121 次的 estimated_cost 是 NULL，全是全书分析写的。

    日费用统计对这些行求和得到 0，于是跑了一整天分析、「今日已花」纹丝不动。费用现在是
    唯一的日闸门，一个永远为 0 的计数器等于没有闸门。
    """
    cost, currency, version = estimate_cost("deepseek-v4-flash", 263_254, 37_559)
    assert cost is not None and cost > 0
    assert currency == "CNY"
    assert version


def test_a_model_the_price_table_does_not_know_stays_empty():
    """宁可空着，也不要写一个编出来的价钱——日闸门是按它拦人的。"""
    cost, _currency, _version = estimate_cost("no-such-model", 1000, 1000)
    assert cost is None


def test_the_ledger_writes_the_three_pricing_columns():
    """光有 estimate_cost 不够，写入那一侧得真的把它带上。"""
    import inspect

    from app.narrative_core.whole_book_v2 import usage_ledger

    source = inspect.getsource(usage_ledger)
    assert "estimated_cost=cost" in source
    assert "currency=currency" in source
    assert "pricing_version=pricing_version" in source
