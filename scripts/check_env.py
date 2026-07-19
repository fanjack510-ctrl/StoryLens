import os
from pathlib import Path

LEGACY_NAMES = {
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "DATABASE_URL",
    "DEFAULT_MODEL_PROVIDER",
    "LOCAL_LLAMA_BASE_URL",
    "LOCAL_LLAMA_API_KEY",
    "LOCAL_LLAMA_MODEL",
    "LOCAL_LLAMA_TIMEOUT_SECONDS",
    "LOCAL_LLAMA_MAX_CONTEXT",
    "ALIYUN_BAILIAN_ENABLED",
    "ALIYUN_BAILIAN_BASE_URL",
    "ALIYUN_BAILIAN_API_KEY",
    "ALIYUN_BAILIAN_MODEL",
}
REQUIRED = (
    "STORYLENS_LOCAL_LLAMA_BASE_URL",
    "STORYLENS_LOCAL_LLAMA_MODEL",
)


def env_names(path: Path) -> set[str]:
    names: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                names.add(stripped.split("=", 1)[0].strip())
    return names


def env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                name, value = stripped.split("=", 1)
                values[name.strip()] = value.strip()
    return values


def main() -> int:
    names = env_names(Path(".env"))
    legacy = sorted(names & LEGACY_NAMES)
    if legacy:
        print("WARNING: legacy variables will not take effect: " + ", ".join(legacy))
        print(
            "Back up .env and rename them with the STORYLENS_ prefix; values were not read or printed."
        )
    example_names = env_names(Path(".env.example"))
    missing = [
        name
        for name in REQUIRED
        if name not in names and name not in os.environ and name not in example_names
    ]
    if missing:
        print("ERROR: missing required local model configuration names: " + ", ".join(missing))
        return 1
    values = env_values(Path(".env"))
    enabled = os.getenv("STORYLENS_ALIYUN_ENABLED", values.get("STORYLENS_ALIYUN_ENABLED", "false"))
    if enabled.lower() in {"1", "true", "yes", "on"}:
        api_key = os.getenv("STORYLENS_ALIYUN_API_KEY", values.get("STORYLENS_ALIYUN_API_KEY", ""))
        workspace = os.getenv(
            "STORYLENS_ALIYUN_WORKSPACE_ID", values.get("STORYLENS_ALIYUN_WORKSPACE_ID", "")
        )
        base_url = os.getenv(
            "STORYLENS_ALIYUN_BASE_URL", values.get("STORYLENS_ALIYUN_BASE_URL", "")
        )
        errors = []
        if not api_key:
            errors.append("STORYLENS_ALIYUN_API_KEY")
        if not workspace and not base_url:
            errors.append("STORYLENS_ALIYUN_WORKSPACE_ID or STORYLENS_ALIYUN_BASE_URL")
        if errors:
            print(
                "ERROR: Aliyun is enabled but required secret/config names are missing: "
                + ", ".join(errors)
            )
            return 1
        print("Aliyun configuration is enabled and complete; secret values were not displayed.")
    print("Environment configuration names checked; no secret values were displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
