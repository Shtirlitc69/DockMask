"""Evaluate saved synthetic runs against non-overlapping, manually specified spans."""

import json
import re
from pathlib import Path

from core.extractors.docx_extractor import extract_docx
from core.extractors.pdf_extractor import extract_pdf

ROOT = Path("tests/fixtures/masking")
LLM_TYPES = {"person_name", "organization", "address", "amount"}


def expected_spans(blocks, values):
    result = []
    for block in blocks:
        candidates = []
        for kind, names in values.items():
            for value in names:
                pattern = re.compile(r"\s+".join(map(re.escape, value.split())))
                for found in pattern.finditer(block.text):
                    candidates.append(
                        {
                            "block_id": block.block_id,
                            "type": kind,
                            "start": found.start(),
                            "end": found.end(),
                            "text": found.group(),
                        }
                    )
        accepted = []
        for candidate in sorted(candidates, key=lambda c: (c["start"], -c["end"])):
            if not any(
                c["type"] == candidate["type"]
                and c["start"] <= candidate["start"]
                and candidate["end"] <= c["end"]
                for c in accepted
            ):
                accepted.append(candidate)
        result.extend(accepted)
    return result


def score(gold, entities):
    missing = [
        g
        for g in gold
        if not any(
            e["block_id"] == g["block_id"]
            and e["type"] == g["type"]
            and e["start"] <= g["start"]
            and e["end"] >= g["end"]
            for e in entities
        )
    ]
    extra = [
        e
        for e in entities
        if not any(
            e["block_id"] == g["block_id"]
            and e["type"] == g["type"]
            and e["start"] < g["end"]
            and e["end"] > g["start"]
            for g in gold
        )
    ]
    return {
        "expected": len(gold),
        "covered": len(gold) - len(missing),
        "missing": missing,
        "additional_candidates_for_review": extra,
    }


def main():
    output = Path("output/masking-regression")
    values = json.loads((ROOT / "expected.json").read_text(encoding="utf-8"))
    gold = {
        name: expected_spans(
            (extract_docx if name.endswith("docx") else extract_pdf)(ROOT / name).blocks, data
        )
        for name, data in values.items()
    }
    runs = json.loads((output / "ablation.json").read_text(encoding="utf-8"))
    evaluated = []
    for run in runs:
        expected = [g for g in gold[run["document"]] if g["type"] in LLM_TYPES]
        evaluated.append(
            {
                "document": run["document"],
                "arm": run["arm"],
                "repeat": run["repeat"],
                "status": run.get("status", "done"),
                "error": run.get("error"),
                **score(expected, run["entities"]),
            }
        )
    (output / "evaluated.json").write_text(
        json.dumps(evaluated, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for name in values:
        for arm in ("baseline", "prompt", "context"):
            selected = [r for r in evaluated if r["document"] == name and r["arm"] == arm]
            completed = [r for r in selected if r["status"] == "done"]
            print(
                name,
                arm,
                "completed",
                len(completed),
                "/",
                len(selected),
                "coverage",
                [(r["covered"], r["expected"]) for r in completed],
                "extra",
                [len(r["additional_candidates_for_review"]) for r in completed],
            )


if __name__ == "__main__":
    main()
