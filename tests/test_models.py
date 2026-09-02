import json
import unittest
from dataclasses import asdict

from core.models import (
    BlockKind,
    EntitySpan,
    EntityType,
    JobStatus,
    Location,
    Match,
    PartyRole,
    TextBlock,
)


class DomainModelsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.location = Location(paragraph_index=0)

    def test_text_block_is_constructible_and_serializable(self) -> None:
        block = TextBlock(
            block_id="p:0",
            text="ИНН 7701234567",
            kind=BlockKind.DOCX_PARAGRAPH,
            location=self.location,
        )

        payload = asdict(block)
        self.assertEqual(payload["block_id"], "p:0")
        json.dumps(payload, ensure_ascii=False)

    def test_all_location_variants_are_optional(self) -> None:
        self.assertEqual(Location(), Location())
        xlsx = Location(sheet_name="Лист1", cell_coordinate="B4")
        self.assertEqual(xlsx.cell_coordinate, "B4")
        pdf = Location(page_number=0, bbox=(1.0, 2.0, 3.0, 4.0))
        self.assertEqual(pdf.page_number, 0)

    def test_stable_enum_values(self) -> None:
        self.assertEqual(JobStatus.QUEUED.value, "queued")
        self.assertEqual(EntityType.ORGANIZATION.value, "organization")
        self.assertEqual(PartyRole.UNKNOWN.value, "unknown")

    def test_entity_span_validates_offsets_and_confidence(self) -> None:
        span = EntitySpan(EntityType.INN, "7701234567", 4, 14, "rule", 1.0)
        self.assertEqual(span.end, 14)

        invalid_cases = (
            ("x", -1, 0, 0.5),
            ("x", 1, 1, 0.5),
            ("xx", 0, 1, 0.5),
            ("x", 0, 1, -0.1),
            ("x", 0, 1, 1.1),
        )
        for text, start, end, confidence in invalid_cases:
            with self.subTest(text=text, start=start, end=end, confidence=confidence):
                with self.assertRaises(ValueError):
                    EntitySpan(EntityType.PERSON_NAME, text, start, end, confidence=confidence)

    def test_match_is_flat_and_serializable(self) -> None:
        match = Match(
            block_id="p:0",
            entity_type=EntityType.INN,
            text="7701234567",
            start=4,
            end=14,
            replacement="[INN_1]",
            source="rule",
            confidence=1.0,
            location=self.location,
        )

        payload = asdict(match)
        self.assertEqual(payload["party_role"], PartyRole.UNKNOWN)
        json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
