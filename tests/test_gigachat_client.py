"""Unit tests for the asynchronous GigaChat adapter."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import unittest
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx

from core.detectors.entity_detector import detect_all
from core.models import BlockKind, EntityType, Location, PartyRole, TextBlock
from llm.base import BaseLLMClient
from llm.gigachat_client import (
    GigaChatClient,
    GigaChatError,
    GigaChatHTTPError,
    LLMResponseError,
)
from llm.http_utils import LLMContextLimitError

AUTH_KEY = "test-auth-key-do-not-log"
ACCESS_TOKEN = "test-access-token-do-not-log"
OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
BASE_URL = "https://api.giga.chat"
MODEL = "test-gigachat-model"


def token_response(
    request: httpx.Request,
    token: str = ACCESS_TOKEN,
    expires_at: int | None = None,
) -> httpx.Response:
    expiry = expires_at or int((time.time() + 3600) * 1000)
    return httpx.Response(
        200,
        json={"access_token": token, "expires_at": expiry},
        request=request,
    )


def chat_response(request: httpx.Request, content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
        request=request,
    )


def entities_content(*entities: dict[str, str]) -> str:
    return json.dumps({"entities": list(entities)}, ensure_ascii=False)


Handler = Callable[[httpx.Request], httpx.Response]


class GigaChatClientTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, handler: Handler) -> GigaChatClient:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http_client.aclose)
        return GigaChatClient(
            auth_key=AUTH_KEY,
            scope="GIGACHAT_API_PERS",
            model=MODEL,
            http_client=http_client,
            oauth_url=OAUTH_URL,
            base_url=BASE_URL,
        )

    async def test_implements_base_contract(self) -> None:
        client = self.make_client(lambda request: token_response(request))
        self.assertIsInstance(client, BaseLLMClient)

    async def test_batches_many_blocks_into_one_sequential_chat_request(self) -> None:
        oauth_calls = 0
        chat_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal oauth_calls, chat_calls
            if request.url.path == "/api/v2/oauth":
                oauth_calls += 1
                return token_response(request)
            chat_calls += 1
            return chat_response(
                request,
                entities_content(
                    {
                        "block_id": 0,
                        "type": "organization",
                        "text": "ООО Тест",
                        "party_role": "supplier",
                    }
                ),
            )

        client = self.make_client(handler)
        blocks = [
            TextBlock(
                block_id=f"p:{index}",
                text="ООО Тест" if index == 0 else f"Обычный текст {index}",
                kind=BlockKind.DOCX_PARAGRAPH,
                location=Location(paragraph_index=index),
            )
            for index in range(100)
        ]
        result = await detect_all(blocks, [EntityType.ORGANIZATION], client)

        self.assertEqual(oauth_calls, 1)
        self.assertEqual(chat_calls, 1)
        self.assertEqual(result["p:0"][0].party_role, PartyRole.SUPPLIER)

    async def test_lists_only_chat_models_with_cached_oauth_token(self) -> None:
        oauth_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal oauth_calls
            if request.url.path == "/api/v2/oauth":
                oauth_calls += 1
                return token_response(request)
            if request.url.path == "/v1/models":
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"id": "GigaChat-2", "type": "chat"},
                            {"id": "Embeddings", "type": "embedding"},
                        ]
                    },
                    request=request,
                )
            return chat_response(request, entities_content())

        client = self.make_client(handler)
        await client.find_entities("Текст", [EntityType.PERSON_NAME])
        models = await client.list_models()
        self.assertEqual([model.id for model in models], ["GigaChat-2"])
        self.assertEqual(oauth_calls, 1)

    async def test_gets_and_reuses_cached_token(self) -> None:
        oauth_requests: list[httpx.Request] = []
        chat_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/oauth":
                oauth_requests.append(request)
                return token_response(request)
            chat_requests.append(request)
            return chat_response(request, entities_content())

        client = self.make_client(handler)
        await client.find_entities("Первый текст", [EntityType.PERSON_NAME])
        await client.find_entities("Второй текст", [EntityType.PERSON_NAME])

        self.assertEqual(len(oauth_requests), 1)
        self.assertEqual(len(chat_requests), 2)
        for request in chat_requests:
            self.assertEqual(
                request.headers["Authorization"],
                f"Bearer {ACCESS_TOKEN}",
            )

    async def test_expired_token_is_refreshed(self) -> None:
        oauth_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal oauth_calls
            if request.url.path == "/api/v2/oauth":
                oauth_calls += 1
                return token_response(request, token=f"token-{oauth_calls}")
            return chat_response(request, entities_content())

        client = self.make_client(handler)
        await client.find_entities("Первый", [EntityType.PERSON_NAME])
        client._token_expires_at = time.time() - 1
        await client.find_entities("Второй", [EntityType.PERSON_NAME])

        self.assertEqual(oauth_calls, 2)

    async def test_provider_expiry_supports_seconds_and_milliseconds(self) -> None:
        expiries = [int(time.time() + 3600), int((time.time() + 3600) * 1000)]

        for expiry in expiries:
            with self.subTest(expiry=expiry):
                oauth_calls = 0

                def handler(
                    request: httpx.Request,
                    current_expiry: int = expiry,
                ) -> httpx.Response:
                    nonlocal oauth_calls
                    if request.url.path == "/api/v2/oauth":
                        oauth_calls += 1
                        return token_response(request, expires_at=current_expiry)
                    return chat_response(request, entities_content())

                client = self.make_client(handler)
                await client.find_entities("Один", [EntityType.PERSON_NAME])
                await client.find_entities("Два", [EntityType.PERSON_NAME])
                self.assertEqual(oauth_calls, 1)

    async def test_token_cache_uses_ten_percent_safety_margin(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/oauth":
                return token_response(request, expires_at=2000)
            return chat_response(request, entities_content())

        client = self.make_client(handler)
        with patch("llm.gigachat_client.time.time", return_value=1000):
            await client.find_entities("Текст", [EntityType.PERSON_NAME])

        self.assertEqual(client._token_expires_at, 1900)

    async def test_concurrent_calls_share_one_token_request(self) -> None:
        oauth_calls = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal oauth_calls
            if request.url.path == "/api/v2/oauth":
                oauth_calls += 1
                await asyncio.sleep(0)
                return token_response(request)
            return chat_response(request, entities_content())

        client = self.make_client(handler)  # type: ignore[arg-type]
        await asyncio.gather(
            *(
                client.find_entities(f"Текст {index}", [EntityType.PERSON_NAME])
                for index in range(8)
            )
        )

        self.assertEqual(oauth_calls, 1)

    async def test_oauth_request_has_unique_rquid_scope_and_basic_auth(self) -> None:
        oauth_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/oauth":
                oauth_requests.append(request)
                return token_response(
                    request,
                    token=f"token-{len(oauth_requests)}",
                )
            return chat_response(request, entities_content())

        client = self.make_client(handler)
        await client.find_entities("Один", [EntityType.PERSON_NAME])
        client._token_expires_at = 0
        await client.find_entities("Два", [EntityType.PERSON_NAME])

        self.assertEqual(len(oauth_requests), 2)
        rquids = [request.headers["RqUID"] for request in oauth_requests]
        self.assertNotEqual(rquids[0], rquids[1])
        for request, rquid in zip(oauth_requests, rquids, strict=True):
            self.assertEqual(request.url, httpx.URL(OAUTH_URL))
            self.assertEqual(request.headers["Authorization"], f"Basic {AUTH_KEY}")
            self.assertEqual(request.headers["User-Agent"], "DockMask/0.1")
            self.assertEqual(
                request.headers["Content-Type"],
                "application/x-www-form-urlencoded",
            )
            self.assertEqual(request.content, b"scope=GIGACHAT_API_PERS")
            self.assertEqual(str(UUID(rquid)), rquid)

    async def test_oauth_transient_status_is_retried(self) -> None:
        oauth_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal oauth_calls
            if request.url.path == "/api/v2/oauth":
                oauth_calls += 1
                if oauth_calls == 1:
                    return httpx.Response(503, request=request)
                return token_response(request)
            return chat_response(request, entities_content())

        client = self.make_client(handler)
        with patch("llm.http_utils.asyncio.sleep", new=AsyncMock()):
            await client.find_entities("Текст", [EntityType.PERSON_NAME])

        self.assertEqual(oauth_calls, 2)

    async def test_401_refreshes_once_and_retries_with_new_token(self) -> None:
        oauth_calls = 0
        chat_tokens: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal oauth_calls
            if request.url.path == "/api/v2/oauth":
                oauth_calls += 1
                return token_response(request, token=f"token-{oauth_calls}")
            chat_tokens.append(request.headers["Authorization"])
            if len(chat_tokens) == 1:
                return httpx.Response(401, request=request)
            return chat_response(request, entities_content())

        client = self.make_client(handler)
        await client.find_entities("Текст", [EntityType.PERSON_NAME])

        self.assertEqual(oauth_calls, 2)
        self.assertEqual(chat_tokens, ["Bearer token-1", "Bearer token-2"])

    async def test_second_401_is_not_retried(self) -> None:
        oauth_calls = 0
        chat_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal oauth_calls, chat_calls
            if request.url.path == "/api/v2/oauth":
                oauth_calls += 1
                return token_response(request, token=f"token-{oauth_calls}")
            chat_calls += 1
            return httpx.Response(401, request=request)

        client = self.make_client(handler)
        with self.assertRaisesRegex(GigaChatHTTPError, "status 401"):
            await client.find_entities("Текст", [EntityType.PERSON_NAME])

        self.assertEqual(oauth_calls, 2)
        self.assertEqual(chat_calls, 2)

    async def test_429_and_5xx_are_retried(self) -> None:
        for retry_status in (429, 503):
            with self.subTest(status=retry_status):
                chat_calls = 0

                def handler(
                    request: httpx.Request,
                    current_status: int = retry_status,
                ) -> httpx.Response:
                    nonlocal chat_calls
                    if request.url.path == "/api/v2/oauth":
                        return token_response(request)
                    chat_calls += 1
                    if chat_calls == 1:
                        return httpx.Response(current_status, request=request)
                    return chat_response(request, entities_content())

                client = self.make_client(handler)
                with patch(
                    "llm.http_utils.asyncio.sleep",
                    new=AsyncMock(),
                ):
                    await client.find_entities("Текст", [EntityType.PERSON_NAME])
                self.assertEqual(chat_calls, 2)

    async def test_context_limit_is_not_retried(self) -> None:
        chat_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal chat_calls
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            chat_calls += 1
            return httpx.Response(413, request=request)

        client = self.make_client(handler)
        with self.assertRaises(LLMContextLimitError):
            await client.find_entities("Текст", [EntityType.PERSON_NAME])

        self.assertEqual(chat_calls, 1)

    async def test_timeout_and_connection_errors_stop_after_three_attempts(self) -> None:
        for error_type in (httpx.ReadTimeout, httpx.ConnectError):
            with self.subTest(error_type=error_type):
                chat_calls = 0

                def handler(
                    request: httpx.Request,
                    current_error_type: type[httpx.RequestError] = error_type,
                ) -> httpx.Response:
                    nonlocal chat_calls
                    if request.url.path == "/api/v2/oauth":
                        return token_response(request)
                    chat_calls += 1
                    raise current_error_type(
                        "synthetic network failure",
                        request=request,
                    )

                client = self.make_client(handler)
                sleep_mock = AsyncMock()
                with patch(
                    "llm.http_utils.asyncio.sleep",
                    new=sleep_mock,
                ), self.assertRaises(GigaChatError):
                    await client.find_entities(
                        "Текст",
                        [EntityType.PERSON_NAME],
                    )
                self.assertEqual(chat_calls, 3)
                # Two retry waits plus optional pacing shared with the previous client.
                self.assertIn(sleep_mock.await_count, (2, 3))

    async def test_other_4xx_is_not_retried(self) -> None:
        chat_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal chat_calls
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            chat_calls += 1
            return httpx.Response(422, request=request)

        client = self.make_client(handler)
        with self.assertRaisesRegex(GigaChatHTTPError, "status 422"):
            await client.find_entities("Текст", [EntityType.PERSON_NAME])
        self.assertEqual(chat_calls, 1)

    async def test_request_uses_configured_model_url_and_json_schema(self) -> None:
        chat_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal chat_request
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            chat_request = request
            return chat_response(request, entities_content())

        client = self.make_client(handler)
        await client.find_entities("Текст", [EntityType.PERSON_NAME])

        assert chat_request is not None
        body = json.loads(chat_request.content)
        self.assertEqual(
            chat_request.url,
            httpx.URL("https://api.giga.chat/v1/chat/completions"),
        )
        self.assertEqual(body["model"], MODEL)
        self.assertEqual(body["temperature"], 0.1)
        self.assertEqual(body["repetition_penalty"], 1.0)
        self.assertEqual(chat_request.headers["User-Agent"], "DockMask/0.1")
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertTrue(body["response_format"]["strict"])
        self.assertEqual(
            body["response_format"]["schema"]["properties"]["entities"]
            ["items"]["properties"]["type"]["enum"],
            ["person_name"],
        )

    async def test_parses_plain_and_markdown_wrapped_json(self) -> None:
        responses = iter(
            [
                entities_content(
                    {"type": "person_name", "text": "Иванов И.И."}
                ),
                "```json\n"
                + entities_content(
                    {"type": "person_name", "text": "Петров П.П."}
                )
                + "\n```",
            ]
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            return chat_response(request, next(responses))

        client = self.make_client(handler)
        first = await client.find_entities(
            "Сотрудник Иванов И.И.",
            [EntityType.PERSON_NAME],
        )
        second = await client.find_entities(
            "Сотрудник Петров П.П.",
            [EntityType.PERSON_NAME],
        )

        self.assertEqual([span.text for span in first], ["Иванов И.И."])
        self.assertEqual([span.text for span in second], ["Петров П.П."])

    async def test_repeated_values_create_all_spans_and_duplicates_are_removed(self) -> None:
        value = "Иванов И.И."

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            return chat_response(
                request,
                entities_content(
                    {"type": "person_name", "text": value},
                    {"type": "person_name", "text": value},
                ),
            )

        text = f"{value} подписал акт. Копию получил {value}."
        client = self.make_client(handler)
        spans = await client.find_entities(text, [EntityType.PERSON_NAME])

        self.assertEqual(len(spans), 2)
        self.assertEqual([span.start for span in spans], [0, text.rindex(value)])
        for span in spans:
            self.assertEqual(text[span.start : span.end], span.text)

    async def test_unknown_unrequested_and_missing_entities_are_ignored_safely(self) -> None:
        rejected_value = "ЗНАЧЕНИЕ-НЕ-ДОЛЖНО-БЫТЬ-В-ЛОГЕ"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            return chat_response(
                request,
                entities_content(
                    {"type": "mystery", "text": rejected_value},
                    {"type": "organization", "text": "ООО Тест"},
                    {"type": "person_name", "text": rejected_value},
                ),
            )

        client = self.make_client(handler)
        with self.assertLogs("llm.structured", logging.WARNING) as logs:
            spans = await client.find_entities(
                "В документе нет совпадений",
                [EntityType.PERSON_NAME],
            )

        self.assertEqual(spans, [])
        output = "\n".join(logs.output)
        self.assertNotIn(rejected_value, output)
        self.assertIn("unknown entity type", output)
        self.assertIn("unrequested entity type", output)
        self.assertIn("absent from source text", output)

    async def test_classifies_role_and_maps_unknown_to_none(self) -> None:
        responses = iter(['{"role":"buyer"}', "```json\n{\"role\":\"unknown\"}\n```"])

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            return chat_response(request, next(responses))

        client = self.make_client(handler)
        role = await client.classify_party("Покупатель: ООО Тест", "ООО Тест")
        unknown = await client.classify_party("Стороны договора", "ООО Тест")

        self.assertEqual(role, PartyRole.BUYER)
        self.assertIsNone(unknown)

    async def test_broken_json_and_chat_envelope_raise_response_error(self) -> None:
        contents: list[str | None] = ["not-json", None]

        for content in contents:
            with self.subTest(content=content):
                def handler(
                    request: httpx.Request,
                    current_content: str | None = content,
                ) -> httpx.Response:
                    if request.url.path == "/api/v2/oauth":
                        return token_response(request)
                    if current_content is None:
                        return httpx.Response(
                            200,
                            json={"choices": []},
                            request=request,
                        )
                    return chat_response(request, current_content)

                client = self.make_client(handler)
                with self.assertRaises(LLMResponseError):
                    await client.find_entities(
                        "Текст",
                        [EntityType.PERSON_NAME],
                    )

    async def test_valid_empty_entities_is_successful(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            return chat_response(request, entities_content())

        client = self.make_client(handler)
        self.assertEqual(
            await client.find_entities("Текст", [EntityType.PERSON_NAME]),
            [],
        )

    async def test_secrets_are_absent_from_logs_and_safe_errors(self) -> None:
        secret_model_value = "private-model-value"

        def warning_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            return chat_response(
                request,
                entities_content(
                    {"type": "person_name", "text": secret_model_value}
                ),
            )

        client = self.make_client(warning_handler)
        with self.assertLogs("llm.structured", logging.WARNING) as logs:
            await client.find_entities("Другой текст", [EntityType.PERSON_NAME])
        logged = "\n".join(logs.output)
        for secret in (AUTH_KEY, ACCESS_TOKEN, secret_model_value):
            self.assertNotIn(secret, logged)

        def error_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"access_token": AUTH_KEY},
                request=request,
            )

        failing_client = self.make_client(error_handler)
        with self.assertRaises(LLMResponseError) as raised:
            await failing_client.find_entities(
                "Текст",
                [EntityType.PERSON_NAME],
            )
        self.assertNotIn(AUTH_KEY, str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)

    async def test_external_http_client_is_not_closed_by_adapter(self) -> None:
        http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: token_response(request))
        )
        self.addAsyncCleanup(http_client.aclose)
        client = GigaChatClient(
            AUTH_KEY,
            "GIGACHAT_API_PERS",
            MODEL,
            http_client,
            OAUTH_URL,
            BASE_URL,
        )

        await client.aclose()

        self.assertFalse(http_client.is_closed)

    async def test_internal_http_client_enables_tls_verification(self) -> None:
        internal_client = MagicMock(spec=httpx.AsyncClient)
        with patch(
            "llm.gigachat_client.httpx.AsyncClient",
            return_value=internal_client,
        ) as constructor:
            GigaChatClient(
                AUTH_KEY,
                "GIGACHAT_API_PERS",
                MODEL,
                None,
                OAUTH_URL,
                BASE_URL,
            )

        constructor.assert_called_once_with(verify=True)


if __name__ == "__main__":
    unittest.main()
