import json
from pathlib import Path


def pricing_status(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"configured": False, "valid": False, "enabled": False,
                "pricing_version": None, "currency": None, "model_names": [],
                "error_code": "CLOUD_PRICING_NOT_CONFIGURED",
                "error_message": "云端价格配置文件不存在"}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"configured": True, "valid": False, "enabled": False,
                "pricing_version": None, "currency": None, "model_names": [],
                "error_code": "CLOUD_PRICING_INVALID", "error_message": "云端价格配置无效"}
    models = config.get("models")
    version = config.get("version")
    currency = config.get("currency")
    if not isinstance(models, dict) or not isinstance(version, str) or not isinstance(currency, str):
        return {"configured": True, "valid": False, "enabled": False,
                "pricing_version": version if isinstance(version, str) else None,
                "currency": currency if isinstance(currency, str) else None,
                "model_names": [], "error_code": "CLOUD_PRICING_INVALID",
                "error_message": "价格配置缺少version、currency或models"}
    complete = bool(models) and all(
        isinstance(item, dict)
        and isinstance(item.get("input_per_million"), (int, float))
        and isinstance(item.get("output_per_million"), (int, float))
        and item["input_per_million"] >= 0 and item["output_per_million"] >= 0
        for item in models.values()
    )
    enabled = complete and version.lower() not in {"unconfigured", "unverified"}
    return {"configured": True, "valid": True, "enabled": enabled,
            "pricing_version": version, "currency": currency,
            "model_names": sorted(str(name) for name in models),
            "error_code": None if enabled else "CLOUD_PRICING_UNVERIFIED",
            "error_message": None if enabled else "价格配置未验证"}


def estimate_cost(
    model: str, input_tokens: int | None, output_tokens: int | None, path: Path
) -> tuple[float | None, str | None, str | None]:
    if not path.exists() or input_tokens is None or output_tokens is None:
        return None, None, None
    config = json.loads(path.read_text(encoding="utf-8"))
    pricing = config.get("models", {}).get(model)
    if not pricing:
        return None, config.get("currency"), config.get("version")
    input_price = pricing.get("input_per_million")
    output_price = pricing.get("output_per_million")
    if input_price is None or output_price is None:
        return None, config.get("currency"), config.get("version")
    cost = input_tokens * input_price / 1_000_000 + output_tokens * output_price / 1_000_000
    return cost, config.get("currency"), config.get("version")
