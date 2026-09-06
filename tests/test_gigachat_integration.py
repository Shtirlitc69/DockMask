"""Opt-in GigaChat integration test using synthetic text only."""

from __future__ import annotations

import os
import ssl
import unittest

import httpx

from core.models import EntityType
from llm.gigachat_client import GigaChatClient

RUN_INTEGRATION = os.getenv("GIGACHAT_RUN_INTEGRATION") == "1"
AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")


@unittest.skipUnless(
    RUN_INTEGRATION and AUTH_KEY,
    "set GIGACHAT_RUN_INTEGRATION=1 and GIGACHAT_AUTH_KEY to call GigaChat",
)
class GigaChatIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_only_exact_synthetic_entities(self) -> None:
        ca_bundle = os.getenv("GIGACHAT_CA_BUNDLE")
        verify: ssl.SSLContext | bool = (
            ssl.create_default_context(cafile=ca_bundle) if ca_bundle else True
        )
        async with httpx.AsyncClient(verify=verify) as http_client:
            client = GigaChatClient(
                auth_key=AUTH_KEY or "",
                scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
                model=os.getenv("GIGACHAT_MODEL", "GigaChat-2"),
                http_client=http_client,
                oauth_url=os.getenv(
                    "GIGACHAT_OAUTH_URL",
                    "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                ),
                base_url=os.getenv(
                    "GIGACHAT_BASE_URL",
                    "https://api.giga.chat",
                ),
            )
            text = (
                "Поставщик ООО Тестовый Вектор. Директор Иванов Иван Иванович."
            )
            spans = await client.find_entities(
                text,
                [EntityType.ORGANIZATION, EntityType.PERSON_NAME],
            )

        actual = {(span.entity_type, span.text) for span in spans}
        self.assertEqual(
            actual,
            {
                (EntityType.ORGANIZATION, "ООО Тестовый Вектор"),
                (EntityType.PERSON_NAME, "Иванов Иван Иванович"),
            },
        )
        for span in spans:
            self.assertEqual(text[span.start : span.end], span.text)


if __name__ == "__main__":
    unittest.main()
