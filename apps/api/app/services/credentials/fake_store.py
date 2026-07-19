from app.services.credentials.base import CredentialStore


class FakeCredentialStore(CredentialStore):
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def available(self) -> bool:
        return True

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)
