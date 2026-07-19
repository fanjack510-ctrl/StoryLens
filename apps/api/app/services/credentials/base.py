from abc import ABC, abstractmethod


class CredentialStore(ABC):
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def get(self, name: str) -> str | None: ...

    @abstractmethod
    def set(self, name: str, value: str) -> None: ...

    @abstractmethod
    def delete(self, name: str) -> None: ...
