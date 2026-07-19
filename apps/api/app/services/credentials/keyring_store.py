import keyring
from keyring.errors import KeyringError

from app.services.credentials.base import CredentialStore


class KeyringCredentialStore(CredentialStore):
    service_name = "StoryLens"

    def available(self) -> bool:
        try:
            return keyring.get_keyring().priority > 0
        except (KeyringError, RuntimeError):
            return False

    def get(self, name: str) -> str | None:
        if not self.available():
            return None
        try:
            return keyring.get_password(self.service_name, name)
        except KeyringError:
            return None

    def set(self, name: str, value: str) -> None:
        if not self.available():
            raise RuntimeError("Windows Credential Manager is unavailable")
        keyring.set_password(self.service_name, name, value)

    def delete(self, name: str) -> None:
        if not self.available():
            raise RuntimeError("Windows Credential Manager is unavailable")
        try:
            keyring.delete_password(self.service_name, name)
        except keyring.errors.PasswordDeleteError:
            return
