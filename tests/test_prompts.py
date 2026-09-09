from core.models import EntityType
from llm.prompts import (
    PROMPT_VERSION,
    ROLE_RESPONSE_SCHEMA,
    build_entity_prompt,
    build_party_prompt,
    entity_response_schema,
)


def test_prompt_contract_is_versioned_and_uses_requested_types() -> None:
    prompt = build_entity_prompt("Синтетический текст", [EntityType.EMAIL, EntityType.INN])
    schema = entity_response_schema([EntityType.EMAIL, EntityType.INN])

    assert PROMPT_VERSION
    assert "Синтетический текст" in prompt
    assert schema["properties"]["entities"]["items"]["properties"]["type"]["enum"] == [
        "email",
        "inn",
    ]
    assert ROLE_RESPONSE_SCHEMA["properties"]["role"]["enum"] == [
        "supplier",
        "buyer",
        "unknown",
    ]


def test_party_prompt_is_synthetic_and_explicit() -> None:
    prompt = build_party_prompt("Поставщик Тест", "Тест")

    assert "Поставщик Тест" in prompt
    assert "Тест" in prompt
