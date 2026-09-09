from __future__ import annotations

import httpx
import pytest

from app.certificates import CertificateStatus
from app.dependencies import ModelDiscoveryError
from app.runtime import RuntimeConfigService
from app.schemas import ModelsRequest
from llm.http_utils import LLMHTTPError
from llm.types import LLMClientConfig, LLMModelInfo, ProviderId


class FakeRepository:
    async def get_config(self) -> LLMClientConfig:
        return LLMClientConfig(ProviderId.MOCK, "mock")


class EmptySecretStore:
    async def get(self, provider: str) -> str | None:
        del provider
        return None


@pytest.mark.asyncio
async def test_gigachat_model_discovery_uses_one_time_key_and_scope(monkeypatch) -> None:
    captured: list[LLMClientConfig] = []

    async def fake_list(config, _http_client):
        captured.append(config)
        return [LLMModelInfo("GigaChat-3-Ultra", "GigaChat-3-Ultra")]

    monkeypatch.setattr("app.runtime.list_llm_models", fake_list)
    async with httpx.AsyncClient() as http_client:
        service = RuntimeConfigService(
            FakeRepository(),
            EmptySecretStore(),
            http_client,
            http_client,
            CertificateStatus("ready"),
            development=True,
        )
        response = await service.list_models(
            ModelsRequest(provider="gigachat", scope="GIGACHAT_API_PERS"),
            api_key="one-time-secret",
        )

    assert [item.id for item in response.models] == ["GigaChat-3-Ultra"]
    assert captured[0].api_key == "one-time-secret"
    assert captured[0].scope == "GIGACHAT_API_PERS"


@pytest.mark.asyncio
async def test_gigachat_model_discovery_preserves_authentication_diagnostic(monkeypatch) -> None:
    async def failed_list(_config, _http_client):
        raise LLMHTTPError("GigaChat", 401)

    monkeypatch.setattr("app.runtime.list_llm_models", failed_list)
    async with httpx.AsyncClient() as http_client:
        service = RuntimeConfigService(
            FakeRepository(),
            EmptySecretStore(),
            http_client,
            http_client,
            CertificateStatus("ready"),
            development=True,
        )
        with pytest.raises(ModelDiscoveryError) as caught:
            await service.list_models(
                ModelsRequest(provider="gigachat", scope="GIGACHAT_API_PERS"),
                api_key="invalid-secret",
            )

    assert caught.value.status_code == 401
    assert caught.value.code == "gigachat_authentication_failed"
