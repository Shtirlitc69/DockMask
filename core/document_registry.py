"""Ephemeral document-wide aggregation for organizations and people."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256

from core.models import (
    EntityRelation,
    EntitySpan,
    EntityType,
    EvidenceKind,
    EvidenceRecord,
    OrganizationRecord,
    PartyRole,
    PersonRecord,
    TextBlock,
)

MentionKey = tuple[str, EntityType, int, int]
_LEGAL_FORMS = re.compile(
    r"\b(?:ооо|ао|пао|зао|оао|ип|индивидуальный\s+предприниматель|"
    r"общество\s+с\s+ограниченной\s+ответственностью)\b",
    re.IGNORECASE,
)
_REPRESENTATION = re.compile(r"\b(?:в\s+лице|действующ\w*\s+от\s+имени)\b", re.IGNORECASE)


def normalize_name(value: str) -> str:
    value = value.casefold().replace("ё", "е")
    value = _LEGAL_FORMS.sub(" ", value)
    value = re.sub(r"[«»\"'`.,;:()\[\]{}]", " ", value)
    return " ".join(value.split())


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{sha256(value.encode('utf-8')).hexdigest()[:16]}"


def _legal_form(value: str) -> str:
    match = _LEGAL_FORMS.search(value)
    if match is None:
        return ""
    form = " ".join(match.group().casefold().split())
    return {
        "общество с ограниченной ответственностью": "ооо",
        "индивидуальный предприниматель": "ип",
    }.get(form, form)


@dataclass(slots=True)
class DocumentRegistry:
    organizations: tuple[OrganizationRecord, ...]
    people: tuple[PersonRecord, ...]
    relations: tuple[EntityRelation, ...]
    mention_entities: dict[MentionKey, str]
    person_organizations: dict[MentionKey, str]


def build_document_registry(
    blocks: Iterable[TextBlock],
    spans_by_block: dict[str, list[EntitySpan]],
) -> DocumentRegistry:
    """Aggregate aliases using strong identifiers, then conservative name equality."""

    block_list = list(blocks)
    organizations: list[tuple[MentionKey, EntitySpan]] = []
    identifiers_by_block: dict[str, list[EntitySpan]] = defaultdict(list)
    for block in block_list:
        for span in spans_by_block.get(block.block_id, ()):
            key = (block.block_id, span.entity_type, span.start, span.end)
            if span.entity_type is EntityType.ORGANIZATION:
                organizations.append((key, span))
            elif span.entity_type in {EntityType.INN, EntityType.OGRN, EntityType.KPP}:
                identifiers_by_block[block.block_id].append(span)

    parent = list(range(len(organizations)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    strong_by_org: list[set[tuple[EntityType, str]]] = []
    for key, organization in organizations:
        block = next(item for item in block_list if item.block_id == key[0])
        left = (
            max(
                block.text.rfind(separator, 0, organization.start)
                for separator in (";", "\n", "\r")
            )
            + 1
        )
        right = min(
            (
                position
                for separator in (";", "\n", "\r")
                if (position := block.text.find(separator, organization.end)) >= 0
            ),
            default=len(block.text),
        )
        local_organizations = [
            (candidate_key, candidate)
            for candidate_key, candidate in organizations
            if candidate_key[0] == key[0] and left <= candidate.start and candidate.end <= right
        ]
        values = []
        for item in identifiers_by_block.get(key[0], ()):
            if not left <= item.start or item.end > right:
                continue
            nearest_key, _ = min(
                local_organizations,
                key=lambda candidate: abs(
                    (candidate[1].start + candidate[1].end) - (item.start + item.end)
                ),
            )
            if nearest_key == key:
                values.append(item)
        strong_by_org.append(
            {
                (item.entity_type, re.sub(r"\s", "", item.text))
                for item in values
                if item.entity_type in {EntityType.INN, EntityType.OGRN}
            }
        )

    for left in range(len(organizations)):
        left_name = normalize_name(organizations[left][1].text)
        for right in range(left):
            right_name = normalize_name(organizations[right][1].text)
            shared_strong = strong_by_org[left] & strong_by_org[right]
            conflicting = any(
                left_values and right_values and left_values.isdisjoint(right_values)
                for kind in (EntityType.INN, EntityType.OGRN)
                if (left_values := {v for k, v in strong_by_org[left] if k is kind}) is not None
                if (right_values := {v for k, v in strong_by_org[right] if k is kind}) is not None
            )
            left_key, left_span = organizations[left]
            right_key, right_span = organizations[right]
            explicit_alias = False
            if left_key[0] == right_key[0]:
                text = next(b.text for b in block_list if b.block_id == left_key[0])
                first, second = sorted((left_span, right_span), key=lambda s: s.start)
                explicit_alias = bool(
                    re.fullmatch(r"\s*\(\s*", text[first.end : second.start])
                    and text[second.end :].lstrip().startswith(")")
                )
            same_name = (
                left_name
                and left_name == right_name
                and _legal_form(left_span.text) == _legal_form(right_span.text)
            )
            if shared_strong or ((explicit_alias or same_name) and not conflicting):
                union(left, right)

    grouped: dict[int, list[int]] = defaultdict(list)
    for index in range(len(organizations)):
        grouped[find(index)].append(index)

    mention_entities: dict[MentionKey, str] = {}
    records: list[OrganizationRecord] = []
    for indexes in grouped.values():
        names = [organizations[index][1].text for index in indexes]
        canonical = max(names, key=lambda item: (len(normalize_name(item)), len(item)))
        stable_basis = "|".join(sorted(normalize_name(item) for item in names))
        entity_id = _stable_id("org", stable_basis)
        roles = {
            organizations[index][1].party_role
            for index in indexes
            if organizations[index][1].party_role is not PartyRole.UNKNOWN
        }
        role = next(iter(roles)) if len(roles) == 1 else PartyRole.UNKNOWN
        evidence: list[EvidenceRecord] = []
        for index in indexes:
            key, span = organizations[index]
            mention_entities[key] = entity_id
            kind = (
                EvidenceKind.SHARED_IDENTIFIER
                if strong_by_org[index]
                else EvidenceKind.NORMALIZED_NAME
            )
            evidence.append(
                EvidenceRecord(kind, key[0], entity_id, value=span.text, confidence=1.0)
            )
        records.append(
            OrganizationRecord(
                entity_id=entity_id,
                canonical_name=canonical,
                aliases=tuple(dict.fromkeys(names)),
                mention_keys=tuple(
                    (organizations[i][0][0], organizations[i][0][2], organizations[i][0][3])
                    for i in indexes
                ),
                role=role,
                confidence=1.0 if role is not PartyRole.UNKNOWN else 0.0,
                conflict=len(roles) > 1,
                evidence=tuple(evidence),
            )
        )

    people: list[PersonRecord] = []
    relations: list[EntityRelation] = []
    person_organizations: dict[MentionKey, str] = {}
    blocks_by_id = {block.block_id: block for block in block_list}
    orgs_by_block: dict[str, list[tuple[MentionKey, EntitySpan]]] = defaultdict(list)
    for key, span in organizations:
        orgs_by_block[key[0]].append((key, span))
    for block_id, spans in spans_by_block.items():
        block = blocks_by_id.get(block_id)
        if block is None:
            continue
        for span in spans:
            if span.entity_type is not EntityType.PERSON_NAME:
                continue
            key = (block_id, span.entity_type, span.start, span.end)
            person_id = _stable_id("person", normalize_name(span.text))
            mention_entities[key] = person_id
            organization_id: str | None = None
            evidence: tuple[EvidenceRecord, ...] = ()
            before = block.text[: span.start]
            marker = tuple(_REPRESENTATION.finditer(before))
            # A second representation clause cannot inherit the organization before
            # the previous clause when its own organization was not recognized.
            previous_marker_end = marker[-2].end() if len(marker) > 1 else 0
            candidates = [
                item
                for item in orgs_by_block.get(block_id, ())
                if marker
                and previous_marker_end <= item[1].start
                and item[1].end <= marker[-1].start()
            ]
            if marker and candidates:
                org_key, _ = max(candidates, key=lambda item: item[1].end)
                organization_id = mention_entities.get(org_key)
                if organization_id:
                    record = EvidenceRecord(
                        EvidenceKind.PERSON_REPRESENTS_ORGANIZATION,
                        block_id,
                        person_id,
                        organization_id,
                        confidence=1.0,
                    )
                    evidence = (record,)
                    relations.append(
                        EntityRelation(record.kind, person_id, organization_id, evidence)
                    )
                    person_organizations[key] = organization_id
            people.append(
                PersonRecord(person_id, span.text, (span.text,), organization_id, evidence)
            )

    return DocumentRegistry(
        tuple(records), tuple(people), tuple(relations), mention_entities, person_organizations
    )
