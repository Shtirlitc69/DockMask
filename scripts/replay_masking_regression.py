"""Replay recorded synthetic GigaChat candidates through current masking code, offline."""

import asyncio
import json
import re
from pathlib import Path

from core.extractors.docx_extractor import extract_docx
from core.extractors.pdf_extractor import extract_pdf
from core.models import EntityType, JobStatus
from core.orchestrator import run_pipeline
from llm.mock_client import MockLLMClient
from llm.structured import EntityItem, to_entity_spans
from scripts.masking_quality import ROOT, expected_spans, score


class ReplayClient(MockLLMClient):
    provider_name = "gigachat_replay"

    def __init__(self, directory):
        self.by_text = {}
        for path in directory.glob("request-*.json"):
            entry = json.loads(path.read_text(encoding="utf-8"))
            if not entry.get("response"):
                continue
            try:
                prompt = json.loads(entry["input"])
                if "blocks" not in prompt:
                    continue
                source = {b["id"]: b["text"] for b in prompt["blocks"]}
                response = json.loads(
                    re.sub(r"^```(?:json)?\s*|\s*```$", "", entry["response"].strip())
                )
            except (ValueError, TypeError):
                continue
            for entity in response.get("entities", []):
                if entity.get("block_id") in source:
                    self.by_text.setdefault(source[entity["block_id"]], []).append(
                        EntityItem(
                            type=entity["type"],
                            text=entity["text"],
                            party_role=entity.get("party_role", "unknown"),
                        )
                    )

    async def find_entities(self, text, types):
        return to_entity_spans(
            text, frozenset(types), self.by_text.get(text, []), source="gigachat_replay"
        )

    async def classify_party(self, context_snippet, candidate_name):
        return None


async def main():
    output = Path("output/masking-regression")
    expected = json.loads((ROOT / "expected.json").read_text(encoding="utf-8"))
    results = []
    for name, extract in (("contract.docx", extract_docx), ("invoice.pdf", extract_pdf)):
        blocks = extract(ROOT / name).blocks
        gold = expected_spans(blocks, expected[name])
        directory = output / name / "pipeline"
        if not directory.exists():
            raise RuntimeError("live_pipeline_recordings_required")
        client = ReplayClient(directory)
        result = await run_pipeline(
            ROOT / name, output / "replay" / Path(name).stem, list(EntityType), client
        )
        decisions = {}
        if result.status is JobStatus.NEEDS_CLARIFICATION:
            # Test-only decisions derived from the manually annotated fixture.
            for question in result.open_questions:
                matches = [
                    m
                    for m in result.matches
                    if question.question_id
                    == f"mask:party:{m.entity_type.value}:{m.entity_id or m.replacement}"
                ]
                decisions[question.question_id] = (
                    "mask"
                    if any(
                        g["block_id"] == m.block_id
                        and g["type"] == m.entity_type.value
                        and m.start < g["end"]
                        and g["start"] < m.end
                        for g in gold
                        for m in matches
                    )
                    else "keep"
                )
            result = await run_pipeline(
                ROOT / name,
                output / "replay" / Path(name).stem,
                list(EntityType),
                client,
                prepared_matches=result.matches,
                answers=decisions,
            )
        entities = [
            {
                "block_id": m.block_id,
                "type": m.entity_type.value,
                "start": m.start,
                "end": m.end,
                "text": m.text,
            }
            for m in result.matches
            if m.applied
        ]
        evaluation = score(gold, entities)
        remaining = (
            "\n".join(b.text for b in extract(result.output_document).blocks)
            if result.output_document
            else ""
        )
        leaks = [
            g["text"]
            for g in gold
            if re.search(r"\s+".join(map(re.escape, g["text"].split())), remaining)
        ]
        entry = {
            "document": name,
            "status": result.status.value,
            "error": result.error_message,
            "applied": len(entities),
            "test_decisions": decisions,
            "remaining_values": leaks,
            **evaluation,
        }
        results.append(entry)
        (output / "replay-results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    k: entry[k]
                    for k in (
                        "document",
                        "status",
                        "applied",
                        "expected",
                        "covered",
                        "remaining_values",
                    )
                }
            ),
            flush=True,
        )
        assert result.status is JobStatus.DONE and not leaks and not evaluation["missing"]


if __name__ == "__main__":
    asyncio.run(main())
