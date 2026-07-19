from functools import lru_cache

from app.services.credentials.base import CredentialStore
from app.services.credentials.keyring_store import KeyringCredentialStore


@lru_cache
def get_credential_store() -> CredentialStore:
    return KeyringCredentialStore()
