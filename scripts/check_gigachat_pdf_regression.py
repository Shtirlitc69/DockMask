"""Live check using synthetic fixtures only; key is read from stdin, never saved."""

import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

import fitz
import httpx

from app.certificates import create_gigachat_ssl_context
from core.detectors.entity_detector import detect_all
from core.extractors.pdf_extractor import extract_pdf
from core.models import EntityType
from core.redaction.pdf_redactor import redact_pdf
from llm.gigachat_client import GigaChatClient


class RecordedClient(GigaChatClient):
    async def _complete(self, *args, **kwargs):
        content = await super()._complete(*args, **kwargs)
        root = Path("output/pdf/regression/responses")
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{self._model}-{len(list(root.glob('*.json')))}.json").write_text(
            content, encoding="utf-8"
        )
        return content


async def main():
    key = sys.stdin.readline().strip()
    root = Path("output/pdf/regression")
    summary = []
    async with httpx.AsyncClient(verify=create_gigachat_ssl_context()) as http:
        for model in ("GigaChat-2-Max", "GigaChat-3-Ultra"):
            client = RecordedClient(
                key,
                "GIGACHAT_API_PERS",
                model,
                http,
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                "https://api.giga.chat",
                timeout_seconds=90,
            )
            for name in ("repeated-contract", "repeated-table"):
                source = root / f"{name}.pdf"
                blocks = extract_pdf(source).blocks
                matches = await detect_all(blocks, list(EntityType), client)
                flat = [match for group in matches.values() for match in group]
                text = "\n".join(block.text for block in blocks)
                values = [
                    "ООО «Тестовый Вектор»",
                    "ООО «Учебная Орбита»",
                    "Иванов Иван Иванович",
                    "contact@example.test",
                    "г. Москва, ул. Тестовая, д. 17",
                ]
                coverage = {}
                for value in values:
                    pattern = re.compile(r"\s+".join(map(re.escape, value.split())))
                    expected = len(list(pattern.finditer(text)))
                    covered = sum(
                        any(
                            match.start <= found.start() and match.end >= found.end()
                            for match in matches.get(block.block_id, [])
                        )
                        for block in blocks
                        for found in pattern.finditer(block.text)
                    )
                    coverage[value] = {"expected": expected, "covered": covered}
                for style in ("full", "short", "none"):
                    target = root / model / f"{name}.{style}.pdf"
                    redact_pdf(source, target, matches, label_style=style)
                    with fitz.open(target) as pdf:
                        remaining = " ".join(" ".join(p.get_text().split()) for p in pdf)
                        assert not any(value in remaining for value in values), (
                            "sensitive text remains"
                        )
                        for index, page in enumerate(pdf):
                            page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4)).save(
                                target.with_suffix(f".page{index + 1}.png")
                            )
                result = {
                    "model": model,
                    "document": name,
                    "coverage": coverage,
                    "matches": len(flat),
                    "applied": sum(m.applied for m in flat),
                    "sources": dict(Counter(m.source for m in flat)),
                }
                summary.append(result)
                (root / "live-results.json").write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
