import asyncio
import json
import os
import time
from pathlib import Path

from pydantic import BaseModel

from app.core.config import get_settings
from app.model_gateway.base import ModelRequest
from app.model_gateway.registry import get_model_gateway
from app.schemas.scene import SceneAnalysisResult, SceneBoundaryResult
from app.services.prompt_service import load_prompt
from app.services.structured_output import extract_json_object


class MinimalResult(BaseModel):
    status: str


def fixture(path: str) -> tuple[str, list[dict[str, str]]]:
    lines = [
        line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return lines[0], [
        {"id": f"B0001-C0001-P{index:04d}", "text": text} for index, text in enumerate(lines[1:], 1)
    ]


async def call(
    provider_name: str, messages: list[dict[str, str]], schema: type[BaseModel]
) -> dict[str, object]:
    gateway = get_model_gateway()
    started = time.perf_counter()
    try:
        response = await gateway.generate(
            provider_name,
            ModelRequest(
                messages=messages,
                temperature=0,
                max_output_tokens=1024,
                response_schema=schema.model_json_schema(),
                response_format_mode="json_object",
                enable_thinking=False,
            ),
        )
        parsed = schema.model_validate_json(extract_json_object(response.text))
        return {
            "provider": provider_name,
            "ok": True,
            "http_status": response.http_status_code,
            "request_id": response.request_id,
            "response_model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "total_tokens": response.total_tokens,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "json_valid": True,
            "schema_valid": True,
            "sends_content_to_cloud": True,
            "result": parsed.model_dump(),
        }
    except Exception as exc:
        return {
            "provider": provider_name,
            "ok": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


async def main() -> int:
    if os.getenv("STORYLENS_RUN_ALIYUN_TESTS") != "1":
        print("Set STORYLENS_RUN_ALIYUN_TESTS=1 to authorize paid calls.")
        return 3
    settings = get_settings()
    if not settings.aliyun_enabled or not settings.aliyun_api_key:
        print("Aliyun configuration is disabled or incomplete; no request was sent.")
        return 3
    if not settings.aliyun_base_url and not settings.aliyun_workspace_id:
        print("Aliyun Workspace ID or Base URL is missing; no request was sent.")
        return 3
    gateway = get_model_gateway()
    results: list[dict[str, object]] = []
    for name in ("aliyun_qwen_flash", "aliyun_qwen_plus", "aliyun_qwen_max"):
        health = await gateway.get(name).health()
        results.append({"provider": name, "health": health.status})
        results.append(
            await call(
                name,
                [
                    {"role": "system", "content": "Return JSON only."},
                    {"role": "user", "content": 'Return JSON {"status":"ok"}.'},
                ],
                MinimalResult,
            )
        )
    prompt = load_prompt("scene_boundary", "v2")
    for name in ("no_boundary", "clear_location_change"):
        title, paragraphs = fixture(f"data/fixtures/local_model_calibration/{name}.txt")
        snapshot = {"chapter_id": "B0001-C0001", "title": title, "paragraphs": paragraphs}
        results.append(
            await call(
                "aliyun_qwen_plus",
                [
                    {"role": "system", "content": prompt.system},
                    {
                        "role": "user",
                        "content": prompt.user_template.format(
                            input_json=json.dumps(snapshot, ensure_ascii=False)
                        ),
                    },
                ],
                SceneBoundaryResult,
            )
        )
    _, paragraphs = fixture("data/fixtures/local_model_calibration/no_boundary.txt")
    analysis = load_prompt("scene_analysis", "v2")
    snapshot = {"scene_id": "B0001-C0001-S0001", "paragraphs": paragraphs[:3]}
    results.append(
        await call(
            "aliyun_qwen_plus",
            [
                {"role": "system", "content": analysis.system},
                {
                    "role": "user",
                    "content": analysis.user_template.format(
                        input_json=json.dumps(snapshot, ensure_ascii=False)
                    ),
                },
            ],
            SceneAnalysisResult,
        )
    )
    output = Path("data/runtime/aliyun/probe.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(item.get("ok", True) for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
