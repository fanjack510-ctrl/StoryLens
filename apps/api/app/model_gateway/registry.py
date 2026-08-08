from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.model_gateway.profiles import load_profiles


@lru_cache
def get_model_gateway() -> ModelGateway:
    settings = get_settings()
    local = OpenAICompatibleProvider(
        name="local_llama",
        base_url=settings.local_llama_base_url,
        api_key=settings.local_llama_api_key,
        default_model=settings.local_llama_model,
        timeout_seconds=settings.local_llama_timeout_seconds,
        max_context_tokens=settings.local_llama_max_context_tokens,
        profile_name="legacy_local_llama",
        enabled=False,
        manual_only=True,
    )
    providers = [local]
    for profile_name, profile in load_profiles(Path("config/local_model_profiles.yaml")).items():
        providers.append(
            OpenAICompatibleProvider(
                name=profile.provider_name,
                base_url=settings.local_llama_base_url,
                api_key=settings.local_llama_api_key,
                default_model=Path(profile.model_path).stem,
                timeout_seconds=settings.local_llama_timeout_seconds,
                max_context_tokens=profile.context_size,
                enabled=profile.enabled,
                profile_name=profile_name,
                default=profile.default,
                manual_only=profile.manual_only,
                structured_output_mode=(
                    "prompt_only"
                    if profile.structured_output_mode == "auto"
                    else profile.structured_output_mode
                ),
                supports_json_schema=profile.structured_output_mode == "json_schema",
                supports_grammar=profile.structured_output_mode == "grammar",
                supports_thinking_control=True,
            )
        )
    from app.services.aliyun_endpoint import resolve_aliyun_compatible_base_url

    # Shared resolution path (same as ProviderConfiguration bootstrap / canary seed).
    aliyun_base_url = resolve_aliyun_compatible_base_url(settings=settings)
    aliyun_roles = (
        ("aliyun_qwen_plus", settings.aliyun_plus_model, False),
        ("aliyun_qwen_max", settings.aliyun_max_model, True),
        ("aliyun_qwen_flash", settings.aliyun_flash_model, True),
    )
    for name, model, manual_only in aliyun_roles:
        # Bootstrap only: settings.aliyun_enabled is deprecated for per-provider
        # health. Runtime overlays ProviderConfiguration.enabled via provider_runtime.
        providers.append(
            OpenAICompatibleProvider(
                name=name,
                base_url=aliyun_base_url or "https://disabled.invalid/v1",
                api_key=settings.aliyun_api_key,
                default_model=model,
                timeout_seconds=settings.aliyun_timeout_seconds,
                max_context_tokens=32768,
                enabled=False,
                profile_name=name,
                default=False,
                manual_only=manual_only,
                structured_output_mode=settings.aliyun_structured_output_mode,
                supports_thinking_control=True,
                cloud=True,
                provider_family="aliyun_qwen",
                supports_json_object=True,
                sends_content_to_cloud=True,
                region="cn-beijing",
                supports_scene_analysis=name == "aliyun_qwen_plus",
                supports_boundary_candidates=name == "aliyun_qwen_plus",
                automatic_boundary_routing=False,
                requires_boundary_review=name == "aliyun_qwen_plus",
            )
        )
    deepseek_base = (settings.deepseek_base_url or "https://api.deepseek.com").rstrip("/")
    providers.append(
        OpenAICompatibleProvider(
            name="deepseek",
            base_url=deepseek_base,
            api_key=settings.deepseek_api_key,
            default_model=settings.deepseek_model or "deepseek-v4-flash",
            timeout_seconds=settings.deepseek_timeout_seconds,
            max_context_tokens=128000,
            enabled=False,
            profile_name="deepseek",
            default=False,
            manual_only=False,
            structured_output_mode=settings.deepseek_structured_output_mode,
            supports_thinking_control=True,
            cloud=True,
            provider_family="deepseek",
            supports_json_object=True,
            sends_content_to_cloud=True,
            region=None,
            supports_scene_analysis=True,
            supports_boundary_candidates=True,
            automatic_boundary_routing=False,
            requires_boundary_review=True,
        )
    )
    return ModelGateway(providers)
