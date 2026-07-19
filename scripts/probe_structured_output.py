import argparse
import asyncio
import json
import os
import time

from jsonschema import validate

from app.model_gateway.base import ModelRequest
from app.model_gateway.registry import get_model_gateway
from app.services.structured_output import extract_json_object

SCHEMA = {
    "type": "object",
    "properties": {"status": {"type": "string", "const": "ok"}},
    "required": ["status"],
    "additionalProperties": False,
}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="local_llama")
    args = parser.parse_args()
    if os.getenv("STORYLENS_RUN_LOCAL_MODEL_TESTS") != "1":
        return 3
    gateway = get_model_gateway()
    results = []
    for mode in ("json_schema", "native_json_schema", "grammar", "prompt_only"):
        started = time.perf_counter()
        entry = {"mode": mode, "thinking_enabled": False}
        try:
            response = await gateway.generate(
                args.provider,
                ModelRequest(
                    messages=[{"role": "user", "content": 'Return {"status":"ok"} only.'}],
                    temperature=0,
                    max_output_tokens=32,
                    response_schema=SCHEMA,
                    response_format_mode=mode,
                    enable_thinking=False,
                ),
            )
            raw = response.text
            parsed = json.loads(extract_json_object(raw))
            validate(parsed, SCHEMA)
            entry.update(
                accepted=True,
                http_status=response.http_status_code,
                pure_json=raw.strip() == json.dumps(parsed, separators=(",", ":")),
                schema_valid=True,
                raw_response=raw,
                model=response.model,
            )
        except Exception as exc:
            entry.update(accepted=False, schema_valid=False, error=str(exc))
        entry["latency_ms"] = int((time.perf_counter() - started) * 1000)
        results.append(entry)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
