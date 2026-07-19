from app.model_gateway.base import ModelProvider, ModelRequest, ModelResponse


class ProviderNotFoundError(LookupError):
    pass


class ModelGateway:
    def __init__(self, providers: list[ModelProvider]) -> None:
        self._providers = {provider.name: provider for provider in providers}

    def providers(self) -> list[ModelProvider]:
        return list(self._providers.values())

    def get(self, name: str) -> ModelProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderNotFoundError(name) from exc

    async def generate(self, provider_name: str, request: ModelRequest) -> ModelResponse:
        return await self.get(provider_name).generate(request)
