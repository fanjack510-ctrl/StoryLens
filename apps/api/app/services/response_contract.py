import hashlib
import json
from typing import Any

from pydantic import BaseModel


def normalized_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema["additionalProperties"] = False
    return schema


def contract_hash(model: type[BaseModel]) -> str:
    payload = json.dumps(normalized_schema(model), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def compact_contract(model: type[BaseModel]) -> str:
    schema = normalized_schema(model)
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


def example_skeleton(model: type[BaseModel]) -> dict[str, Any]:
    schema = normalized_schema(model)

    def value(node: dict[str, Any]) -> Any:
        if "$ref" in node:
            node = schema["$defs"][node["$ref"].split("/")[-1]]
        if "anyOf" in node:
            candidates = [item for item in node["anyOf"] if item.get("type") != "null"]
            return value(candidates[0]) if candidates else None
        if "enum" in node:
            return node["enum"][0]
        kind = node.get("type")
        if kind == "object" or "properties" in node:
            return {name: value(child) for name, child in node.get("properties", {}).items()}
        if kind == "array":
            return []
        if kind == "string":
            return ""
        if kind in {"number", "integer"}:
            return 0
        if kind == "boolean":
            return False
        return None

    return value(schema)


def render_contract(text: str, model: type[BaseModel]) -> str:
    return text.replace("{response_contract}", compact_contract(model)).replace(
        "{response_example}", json.dumps(example_skeleton(model), ensure_ascii=False)
    )
