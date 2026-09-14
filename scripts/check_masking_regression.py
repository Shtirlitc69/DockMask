"""Synthetic-only live ablation. Secret supplied on stdin, never persisted."""

import asyncio
import json
import re
import sys
from dataclasses import replace
from pathlib import Path

import httpx

from app.certificates import create_gigachat_ssl_context
from core.detectors.entity_detector import _fragment_blocks, _llm_batches
from core.extractors.docx_extractor import extract_docx
from core.extractors.pdf_extractor import extract_pdf
from core.models import EntityType
from core.orchestrator import run_pipeline
from llm import structured
from llm.gigachat_client import GigaChatClient
from llm.prompts import BATCH_ENTITY_SYSTEM_PROMPT
from llm.structured import LLMResponseError

FIXTURES = Path("tests/fixtures/masking")
OUTPUT = Path("output/masking-regression")


class RecordedClient(GigaChatClient):
    recording_dir: Path
    request_number = 0

    async def _complete(self, prompt, response_schema, *, system_prompt=None):
        self.request_number += 1
        self.recording_dir.mkdir(parents=True, exist_ok=True)
        target = self.recording_dir / f"request-{self.request_number}.json"
        entry = {"system": system_prompt, "input": prompt, "schema": response_schema, "schema_in_prompt_before_request": self._schema_in_prompt}
        target.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            response = await super()._complete(prompt, response_schema, system_prompt=system_prompt)
        except LLMResponseError as exc:
            entry["error"] = exc.category
            target.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
            raise
        entry["response"] = response
        target.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        return response


async def main():
    key = sys.stdin.readline().strip()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "experiment.json").write_text(json.dumps({
        "model": "GigaChat-3-Pro", "temperature": 0.1, "output_tokens": 4096,
        "repeats": 3, "batch_character_budget": 7000,
        "prompt_versions": ["2.1.0", "2.2.0"],
        "recordings": "synthetic fixture text and responses only; no HTTP headers or keys",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path = OUTPUT / "ablation.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else []
    async with httpx.AsyncClient(verify=create_gigachat_ssl_context()) as http:
        client = RecordedClient(
            key,
            "GIGACHAT_API_PERS",
            "GigaChat-3-Pro",
            http,
            "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            "https://api.giga.chat",
            timeout_seconds=90,
        )
        try:
            models = await client.list_models()
            print(json.dumps({"available_models": [m.id for m in models]}), flush=True)
            if client._model not in {m.id for m in models}:
                raise RuntimeError("requested_model_unavailable")
            for filename, extract in (
                ("contract.docx", extract_docx),
                ("invoice.pdf", extract_pdf),
            ):
                blocks = extract(FIXTURES / filename).blocks
                if not blocks or "СИНТЕТИЧЕСКИЙ" not in blocks[0].text:
                    raise RuntimeError("synthetic_fixture_required")
                # Same four LLM categories as the application, same block boundaries in all arms.
                types = [
                    EntityType.PERSON_NAME,
                    EntityType.ORGANIZATION,
                    EntityType.ADDRESS,
                    EntityType.AMOUNT,
                ]
                for arm in ("baseline", "prompt", "context"):
                    structured.BATCH_ENTITY_SYSTEM_PROMPT = (
                        (FIXTURES / "baseline-prompt.txt").read_text(encoding="utf-8")
                        if arm == "baseline"
                        else BATCH_ENTITY_SYSTEM_PROMPT
                    )
                    for repeat in range(3):
                        if any(
                            r["document"] == filename
                            and r["arm"] == arm
                            and r["repeat"] == repeat + 1
                            for r in summary
                        ):
                            continue
                        client.recording_dir = OUTPUT / filename / arm / str(repeat + 1)
                        client.request_number = 0
                        selected = (
                            blocks if arm == "context" else [replace(b, context={}) for b in blocks]
                        )
                        result = {}
                        # Use identical groups in all arms; budget based on the richer context.
                        batches = _llm_batches(_fragment_blocks(blocks, 6000), 7000)
                        selected_by_id = {b.block_id: b for b in selected}
                        run_error = None
                        try:
                            for batch in batches:
                                result.update(
                                    await client.find_entities_for_analysis(
                                        [selected_by_id[f.block.block_id] for f in batch], types, ()
                                    )
                                )
                        except LLMResponseError as exc:
                            run_error = exc.category
                        values = [
                            {
                                "block_id": block_id,
                                "type": m.entity_type.value,
                                "text": m.text,
                                "start": m.start,
                                "end": m.end,
                            }
                            for block_id, spans in result.items()
                            for m in spans
                        ]
                        expected = json.loads(
                            (FIXTURES / "expected.json").read_text(encoding="utf-8")
                        )[filename]
                        missing = []
                        expected_count = 0
                        for kind in [t.value for t in types]:
                            for value in expected[kind]:
                                pattern = re.compile(r"\s+".join(map(re.escape, value.split())))
                                for block in blocks:
                                    for found in pattern.finditer(block.text):
                                        expected_count += 1
                                        if not any(
                                            v["block_id"] == block.block_id
                                            and v["type"] == kind
                                            and v["start"] <= found.start()
                                            and v["end"] >= found.end()
                                            for v in values
                                        ):
                                            missing.append(
                                                {
                                                    "type": kind,
                                                    "block_id": block.block_id,
                                                    "value": value,
                                                }
                                            )
                        item = {
                            "document": filename,
                            "arm": arm,
                            "repeat": repeat + 1,
                            "expected_occurrences": expected_count,
                            "missing": missing,
                            "entities": values,
                            "status": "failed" if run_error else "done",
                            "error": run_error,
                        }
                        summary.append(item)
                        (OUTPUT / "ablation.json").write_text(
                            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        print(
                            json.dumps(
                                {
                                    "document": filename,
                                    "arm": arm,
                                    "repeat": repeat + 1,
                                    "entities": len(values),
                                    "error": run_error,
                                }
                            ),
                            flush=True,
                        )
                structured.BATCH_ENTITY_SYSTEM_PROMPT = BATCH_ENTITY_SYSTEM_PROMPT
                client.recording_dir = OUTPUT / filename / "pipeline"
                result = await run_pipeline(
                    FIXTURES / filename, OUTPUT / filename / "result", list(EntityType), client
                )
                print(
                    json.dumps(
                        {
                            "pipeline": filename,
                            "status": result.status.value,
                            "applied": len(result.matches),
                            "error": result.error_message,
                        }
                    ),
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001 - never expose request headers on CLI failure
            # Never print exception messages that could contain HTTP headers.
            failure = {
                "error_type": type(exc).__name__,
                "status": getattr(exc, "status_code", None),
            }
            (OUTPUT / "failure.json").write_text(json.dumps(failure), encoding="utf-8")
            print(json.dumps(failure), flush=True)
            raise SystemExit(1) from None
        finally:
            structured.BATCH_ENTITY_SYSTEM_PROMPT = BATCH_ENTITY_SYSTEM_PROMPT


if __name__ == "__main__":
    asyncio.run(main())
