"""Тесты детерминированного поиска структурированных сущностей."""

import unittest

from core.detectors.rule_based import detect_rule_based
from core.models import EntityType


ALL_RULE_TYPES = [
    EntityType.INN,
    EntityType.KPP,
    EntityType.OGRN,
    EntityType.PHONE,
    EntityType.EMAIL,
    EntityType.BANK_ACCOUNT,
    EntityType.BIK,
    EntityType.CONTRACT_NUMBER,
]


class RuleBasedDetectorTests(unittest.TestCase):
    def assert_values(
        self,
        text: str,
        requested_types: list[EntityType],
        expected: list[tuple[EntityType, str]],
    ) -> None:
        spans = detect_rule_based(text, requested_types)
        actual = [(span.entity_type, span.text) for span in spans]
        self.assertEqual(actual, expected)
        for span in spans:
            self.assertEqual(text[span.start : span.end], span.text)
            self.assertEqual(span.source, "rule")
            self.assertEqual(span.confidence, 1.0)

    def test_positive_case_for_every_type(self) -> None:
        cases = (
            ("ИНН: 7707083893", EntityType.INN, "7707083893"),
            ("КПП 773601001", EntityType.KPP, "773601001"),
            ("ОГРН 1027700132195", EntityType.OGRN, "1027700132195"),
            ("телефон: +7 (495) 123-45-67", EntityType.PHONE, "+7 (495) 123-45-67"),
            ("info@example.ru", EntityType.EMAIL, "info@example.ru"),
            (
                "расчётный счёт 40702810900000000001",
                EntityType.BANK_ACCOUNT,
                "40702810900000000001",
            ),
            ("БИК: 044525225", EntityType.BIK, "044525225"),
            (
                "Договор поставки № 15-А/2026",
                EntityType.CONTRACT_NUMBER,
                "15-А/2026",
            ),
        )

        for text, entity_type, value in cases:
            with self.subTest(entity_type=entity_type):
                self.assert_values(text, [entity_type], [(entity_type, value)])

    def test_negative_case_for_every_type(self) -> None:
        cases = (
            ("7707083893", EntityType.INN),
            ("773601001", EntityType.KPP),
            ("ОГРН 1027700132194", EntityType.OGRN),
            ("+7 (495) 123-45-67", EntityType.PHONE),
            ("пишите на info@localhost", EntityType.EMAIL),
            ("40702810900000000001", EntityType.BANK_ACCOUNT),
            ("044525225", EntityType.BIK),
            ("№ 15-А/2026", EntityType.CONTRACT_NUMBER),
        )

        for text, entity_type in cases:
            with self.subTest(entity_type=entity_type):
                self.assert_values(text, [entity_type], [])

    def test_inn_and_kpp_in_combined_requisites(self) -> None:
        text = "ИНН/КПП 7707083893/773601001"
        self.assert_values(
            text,
            [EntityType.INN, EntityType.KPP],
            [
                (EntityType.INN, "7707083893"),
                (EntityType.KPP, "773601001"),
            ],
        )

    def test_inn_control_digits_for_legal_entity_and_person(self) -> None:
        text = "ИНН 7707083893; ИНН 500100732259"
        self.assert_values(
            text,
            [EntityType.INN],
            [
                (EntityType.INN, "7707083893"),
                (EntityType.INN, "500100732259"),
            ],
        )

        self.assert_values(
            "ИНН 7707083894; ИНН 500100732258",
            [EntityType.INN],
            [],
        )

    def test_ogrn_and_ogrnip_control_digits(self) -> None:
        text = "ОГРН 1027700132195; ОГРНИП 304500116000157"
        self.assert_values(
            text,
            [EntityType.OGRN],
            [
                (EntityType.OGRN, "1027700132195"),
                (EntityType.OGRN, "304500116000157"),
            ],
        )

        self.assert_values(
            "ОГРН 1027700132194; ОГРНИП 304500116000156",
            [EntityType.OGRN],
            [],
        )

    def test_account_starting_with_eight_is_not_a_phone(self) -> None:
        account = "81234567890123456789"
        text = f"тел. {account}; р/с {account}"
        self.assert_values(
            text,
            [EntityType.PHONE, EntityType.BANK_ACCOUNT],
            [(EntityType.BANK_ACCOUNT, account)],
        )

    def test_random_ten_digit_number_is_not_inn(self) -> None:
        self.assert_values("Код операции 7707083893", [EntityType.INN], [])

    def test_values_at_text_boundaries_and_two_values_in_one_line(self) -> None:
        text = "first@example.ru, email: second@example.ru; БИК 044525225"
        self.assert_values(
            text,
            [EntityType.EMAIL, EntityType.BIK],
            [
                (EntityType.EMAIL, "first@example.ru"),
                (EntityType.EMAIL, "second@example.ru"),
                (EntityType.BIK, "044525225"),
            ],
        )
        spans = detect_rule_based(text, [EntityType.EMAIL, EntityType.BIK])
        self.assertEqual(spans[0].start, 0)
        self.assertEqual(spans[-1].end, len(text))

    def test_requested_type_filter_empty_input_and_duplicate_types(self) -> None:
        text = "ИНН 7707083893, БИК 044525225, email info@example.ru"
        self.assert_values(text, [], [])
        self.assert_values(
            text,
            [EntityType.INN, EntityType.INN],
            [(EntityType.INN, "7707083893")],
        )

    def test_synthetic_contract_finds_all_marked_entities_without_overlaps(self) -> None:
        text = (
            "Договор поставки № 15-А/2026\n"
            "Реквизиты: ИНН/КПП 7707083893/773601001, ОГРН 1027700132195.\n"
            "р/с 40702810900000000001, БИК 044525225.\n"
            "Телефон: +7 (495) 123-45-67, email: tender@example.ru."
        )
        spans = detect_rule_based(text, ALL_RULE_TYPES)

        self.assertEqual(
            [(span.entity_type, span.text) for span in spans],
            [
                (EntityType.CONTRACT_NUMBER, "15-А/2026"),
                (EntityType.INN, "7707083893"),
                (EntityType.KPP, "773601001"),
                (EntityType.OGRN, "1027700132195"),
                (EntityType.BANK_ACCOUNT, "40702810900000000001"),
                (EntityType.BIK, "044525225"),
                (EntityType.PHONE, "+7 (495) 123-45-67"),
                (EntityType.EMAIL, "tender@example.ru"),
            ],
        )
        for previous, current in zip(spans, spans[1:]):
            self.assertLessEqual(previous.end, current.start)
        for span in spans:
            self.assertEqual(text[span.start : span.end], span.text)


if __name__ == "__main__":
    unittest.main()
