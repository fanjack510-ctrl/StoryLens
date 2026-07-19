import hashlib
import json

CONVERTER_VERSION = "storylens-v1"


def schema_hash(schema: dict[str, object]) -> str:
    canonical = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def schema_to_gbnf(schema: dict[str, object]) -> str:
    if schema.get("type") != "object":
        raise ValueError("Only object-root StoryLens schemas are supported")
    return (
        'root ::= ws object ws\nobject ::= "{" ws (string ws ":" ws value '
        '(ws "," ws string ws ":" ws value)*)? ws "}"\n'
        'array ::= "[" ws (value (ws "," ws value)*)? ws "]"\n'
        'value ::= object | array | string | number | "true" | "false" | "null"\n'
        'string ::= "\\"" chars "\\""\nchars ::= [^"\\\\]*\n'
        'number ::= "-"? ("0" | [1-9] [0-9]*) ("." [0-9]+)?\nws ::= [ \\t\\n\\r]*'
    )


def grammar_hash(grammar: str) -> str:
    return hashlib.sha256(grammar.encode()).hexdigest()


def select_structured_output_mode(results: dict[str, bool]) -> tuple[str, str | None]:
    for mode in ("json_schema", "native_json_schema", "grammar"):
        if results.get(mode):
            return mode, None
    if results.get("prompt_only"):
        return "prompt_only", "server rejected schema and grammar constraints"
    return "unsupported", "all structured-output probes failed"
