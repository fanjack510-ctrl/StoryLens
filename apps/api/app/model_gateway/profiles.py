import json
from pathlib import Path

from pydantic import BaseModel


class LocalModelProfile(BaseModel):
    provider_name: str
    model_family: str
    model_path: str
    context_size: int = 4096
    gpu_layers: int = 16
    parallel: int = 1
    batch_size: int = 128
    ubatch_size: int = 64
    max_output_tokens: int = 512
    enable_thinking: bool = False
    structured_output_mode: str = "auto"
    enabled: bool = True
    default: bool = False
    manual_only: bool = False


def load_profiles(path: Path) -> dict[str, LocalModelProfile]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {name: LocalModelProfile.model_validate(value) for name, value in raw.items()}
