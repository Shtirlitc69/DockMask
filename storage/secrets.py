"""Windows Credential Manager-backed provider secrets."""

from __future__ import annotations

import asyncio
from typing import Protocol

import keyring
from keyring.errors import KeyringError

SERVICE_NAME = "DockMask LLM"


class SecretStoreUnavailableError(RuntimeError):
    pass


class SecretStore(Protocol):
    async def get(self, provider: str) -> str | None: ...
    async def set(self, provider: str, value: str) -> None: ...
    async def delete(self, provider: str) -> None: ...


class KeyringSecretStore:
    async def get(self, provider: str) -> str | None:
        try:
            return await asyncio.to_thread(keyring.get_password, SERVICE_NAME, provider)
        except KeyringError:
            raise SecretStoreUnavailableError from None

    async def set(self, provider: str, value: str) -> None:
        try:
            await asyncio.to_thread(keyring.set_password, SERVICE_NAME, provider, value)
        except KeyringError:
            raise SecretStoreUnavailableError from None

    async def delete(self, provider: str) -> None:
        try:
            await asyncio.to_thread(keyring.delete_password, SERVICE_NAME, provider)
        except keyring.errors.PasswordDeleteError:
            return
        except KeyringError:
            raise SecretStoreUnavailableError from None
