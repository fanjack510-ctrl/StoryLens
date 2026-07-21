import json
import os
from functools import lru_cache
from pathlib import Path


def resolve_cloud_pricing_path(explicit: Path | None = None) -> Path:
    """Resolve the active cloud pricing file for eligibility, budget, and estimates.

    Search order:
    1. Explicit path argument (when the file exists)
    2. STORYLENS_CLOUD_PRICING_PATH env (when the file exists)
    3. User config dir cloud_pricing.json (packaged installs)
    4. Resource/repo config/cloud_pricing.json
    5. Bundled config/cloud_pricing.default.json (verified list-price fallback)
    """
    from app.core.paths import resource_root, user_data_layout

    candidates: list[Path] = []

    env = os.environ.get("STORYLENS_CLOUD_PRICING_PATH")
    if env:
        candidates.append(Path(env).expanduser())

    if explicit is not None:
        candidates.append(explicit)

    try:
        candidates.append(user_data_layout()["config"] / "cloud_pricing.json")
    except Exception:  # noqa: BLE001 — layout may be unavailable in unit isolation
        pass

    root = resource_root()
    candidates.append(root / "config" / "cloud_pricing.json")
    candidates.append(root / "config" / "cloud_pricing.default.json")
    # Relative cwd fallback (frozen sidecar chdirs to resource_root).
    candidates.append(Path("config") / "cloud_pricing.json")
    candidates.append(Path("config") / "cloud_pricing.default.json")

    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            if path.is_file():
                return path.resolve()
        except OSError:
            continue
    return (root / "config" / "cloud_pricing.default.json").resolve()


@lru_cache
def default_pricing_path() -> Path:
    return resolve_cloud_pricing_path()


def clear_pricing_path_cache() -> None:
    default_pricing_path.cache_clear()


def _is_conventional_cloud_pricing_path(path: Path) -> bool:
    name = path.name.lower()
    if name not in {"cloud_pricing.json", "cloud_pricing.default.json"}:
        return False
    parts = {part.lower() for part in path.parts}
    return "config" in parts or name == "cloud_pricing.default.json"


def pricing_status(path: Path | None = None) -> dict[str, object]:
    if path is None:
        resolved = resolve_cloud_pricing_path()
    elif path.exists():
        resolved = path
    elif _is_conventional_cloud_pricing_path(path):
        resolved = resolve_cloud_pricing_path(path)
    else:
        return {
            "configured": False,
            "valid": False,
            "enabled": False,
            "pricing_version": None,
            "currency": None,
            "model_names": [],
            "error_code": "CLOUD_PRICING_NOT_CONFIGURED",
            "error_message": "云端价格配置文件不存在",
            "pricing_path": str(path),
        }

    if not resolved.exists():
        return {
            "configured": False,
            "valid": False,
            "enabled": False,
            "pricing_version": None,
            "currency": None,
            "model_names": [],
            "error_code": "CLOUD_PRICING_NOT_CONFIGURED",
            "error_message": "云端价格配置文件不存在",
            "pricing_path": str(resolved),
        }
    try:
        config = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "configured": True,
            "valid": False,
            "enabled": False,
            "pricing_version": None,
            "currency": None,
            "model_names": [],
            "error_code": "CLOUD_PRICING_INVALID",
            "error_message": "云端价格配置无效",
            "pricing_path": str(resolved),
        }
    models = config.get("models")
    version = config.get("version")
    currency = config.get("currency")
    if not isinstance(models, dict) or not isinstance(version, str) or not isinstance(currency, str):
        return {
            "configured": True,
            "valid": False,
            "enabled": False,
            "pricing_version": version if isinstance(version, str) else None,
            "currency": currency if isinstance(currency, str) else None,
            "model_names": [],
            "error_code": "CLOUD_PRICING_INVALID",
            "error_message": "价格配置缺少version、currency或models",
            "pricing_path": str(resolved),
        }
    complete = bool(models) and all(
        isinstance(item, dict)
        and isinstance(item.get("input_per_million"), (int, float))
        and isinstance(item.get("output_per_million"), (int, float))
        and item["input_per_million"] >= 0
        and item["output_per_million"] >= 0
        for item in models.values()
    )
    enabled = complete and version.lower() not in {"unconfigured", "unverified"}
    return {
        "configured": True,
        "valid": True,
        "enabled": enabled,
        "pricing_version": version,
        "currency": currency,
        "model_names": sorted(str(name) for name in models),
        "error_code": None if enabled else "CLOUD_PRICING_UNVERIFIED",
        "error_message": None if enabled else "价格配置未验证",
        "pricing_path": str(resolved),
    }


def estimate_cost(
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    path: Path | None = None,
) -> tuple[float | None, str | None, str | None]:
    if path is None:
        resolved = resolve_cloud_pricing_path()
    elif path.exists():
        resolved = path
    elif _is_conventional_cloud_pricing_path(path):
        resolved = resolve_cloud_pricing_path(path)
    else:
        return None, None, None
    if not resolved.exists() or input_tokens is None or output_tokens is None:
        return None, None, None
    config = json.loads(resolved.read_text(encoding="utf-8"))
    pricing = config.get("models", {}).get(model)
    if not pricing:
        return None, config.get("currency"), config.get("version")
    input_price = pricing.get("input_per_million")
    output_price = pricing.get("output_per_million")
    if input_price is None or output_price is None:
        return None, config.get("currency"), config.get("version")
    cost = input_tokens * input_price / 1_000_000 + output_tokens * output_price / 1_000_000
    return cost, config.get("currency"), config.get("version")


def model_pricing_available(model: str, path: Path | None = None) -> bool:
    """True when the model has numeric list prices in the active pricing file."""
    status = pricing_status(path)
    if not status.get("enabled"):
        return False
    resolved = Path(str(status.get("pricing_path") or resolve_cloud_pricing_path(path)))
    if not resolved.exists():
        return False
    config = json.loads(resolved.read_text(encoding="utf-8"))
    pricing = config.get("models", {}).get(model)
    if not isinstance(pricing, dict):
        return False
    return (
        isinstance(pricing.get("input_per_million"), (int, float))
        and isinstance(pricing.get("output_per_million"), (int, float))
        and pricing["input_per_million"] >= 0
        and pricing["output_per_million"] >= 0
    )
