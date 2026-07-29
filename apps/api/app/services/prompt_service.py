import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.core.paths import resource_root
from app.services.response_contract import render_contract


@dataclass(frozen=True)
class PromptBundle:
    task_type: str
    version: str
    system: str
    user_template: str
    repair_template: str
    content_hash: str


def _prompt_root() -> Path:
    configured = Path(get_settings().prompt_root)
    if configured.is_absolute():
        return configured
    return (resource_root() / configured).resolve()


def load_prompt(task_type: str, version: str = "v1") -> PromptBundle:
    root = _prompt_root() / task_type / version
    system = (root / "system.md").read_text(encoding="utf-8")
    user = (root / "user.md").read_text(encoding="utf-8")
    repair = (root / "repair.md").read_text(encoding="utf-8")
    digest = hashlib.sha256((system + user + repair).encode()).hexdigest()
    return PromptBundle(task_type, version, system, user, repair, digest)


def with_response_contract(prompt: PromptBundle, schema) -> PromptBundle:
    return PromptBundle(
        prompt.task_type,
        prompt.version,
        render_contract(prompt.system, schema),
        render_contract(prompt.user_template, schema),
        render_contract(prompt.repair_template, schema),
        prompt.content_hash,
    )
