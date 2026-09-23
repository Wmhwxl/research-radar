from __future__ import annotations

import re
from collections import OrderedDict

from src.research_radar.models import QueryLane, ResearchField


def build_query_lanes(field: ResearchField, *, max_lanes: int | None = None) -> list[QueryLane]:
    lanes: list[QueryLane] = []
    exact_terms = _dedupe(
        term
        for term in field.core_keywords
        if _meaningful(term)
        and (" " in term.strip() or "-" in term.strip())
        and _has_specific_field_constraint(term)
    )
    for idx, term in enumerate(exact_terms[:4]):
        lanes.append(
            QueryLane(
                id=f"exact_{idx + 1}",
                name=f"Exact {idx + 1}",
                query=_quote(term),
                weight=1.0,
                type="exact",
                description=f"Exact phrase lane for {term}",
            )
        )

    groups = _groups(field)
    recommendation = groups.get("recommendation", [])
    multimodal = groups.get("multimodal", [])
    missingness = groups.get("missingness", [])
    recovery = groups.get("recovery", [])
    if recommendation and multimodal and missingness:
        lanes.append(
            QueryLane(
                id="broad_missing",
                name="Broad Missingness",
                query=f"{_or(multimodal)} AND {_or(recommendation)} AND {_or(missingness)}",
                weight=0.85,
                type="broad",
                description="Broad field lane requiring modality, recommendation, and missingness signals.",
            )
        )
    if recommendation and multimodal and recovery:
        lanes.append(
            QueryLane(
                id="broad_recovery",
                name="Broad Recovery",
                query=f"{_or(multimodal)} AND {_or(recommendation)} AND {_or(recovery)}",
                weight=0.75,
                type="broad",
                description="Broad field lane requiring modality, recommendation, and recovery/robustness signals.",
            )
        )

    for idx, query in enumerate(_dedupe(field.intent_queries)):
        if not _meaningful(query):
            continue
        lanes.append(
            QueryLane(
                id=f"intent_{idx + 1}",
                name=f"Intent {idx + 1}",
                query=_normalize_query_text(query),
                weight=0.65,
                type="intent",
                description="Research-field intent query.",
            )
        )

    if not lanes:
        fallback_terms = _dedupe([*field.intent_queries, *field.core_keywords, field.name])
        for idx, term in enumerate(fallback_terms[:3]):
            if not _meaningful(term):
                continue
            lanes.append(
                QueryLane(
                    id=f"generic_{idx + 1}",
                    name=f"Generic {idx + 1}",
                    query=_normalize_query_text(term),
                    weight=0.55,
                    type="generic",
                    description="Generic field-name or keyword lane.",
                )
            )

    unique = list(OrderedDict((lane.query, lane) for lane in lanes).values())
    return unique[:max_lanes] if max_lanes else unique


def keyword_groups_for_field(field: ResearchField) -> dict[str, list[str]]:
    return _groups(field)


def _groups(field: ResearchField) -> dict[str, list[str]]:
    if field.keyword_groups:
        return {key: _dedupe(value) for key, value in field.keyword_groups.items()}
    terms = _dedupe([*field.core_keywords, *field.optional_keywords])
    groups = {"recommendation": [], "multimodal": [], "missingness": [], "recovery": []}
    for term in terms:
        lowered = term.casefold()
        if "recommend" in lowered or "recommender" in lowered:
            groups["recommendation"].append(term)
        if any(token in lowered for token in ("multimodal", "multi-modal", "modality", "modalities", "visual", "textual", "image", "audio")):
            groups["multimodal"].append(term)
        if any(token in lowered for token in ("missing", "incomplete", "partial", "unavailable", "absent")):
            groups["missingness"].append(term)
        if any(token in lowered for token in ("completion", "imputation", "reconstruction", "recovery", "robust", "corrupt")):
            groups["recovery"].append(term)
    return {key: _dedupe(value) for key, value in groups.items()}


def _or(terms: list[str]) -> str:
    cleaned = [_quote(term) if " " in term.strip() or "-" in term.strip() else term.strip() for term in _dedupe(terms)]
    return cleaned[0] if len(cleaned) == 1 else "(" + " OR ".join(cleaned) + ")"


def _quote(term: str) -> str:
    return '"' + term.strip().replace('"', '\\"') + '"'


def _normalize_query_text(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip())


def _meaningful(value: str) -> bool:
    return bool(value and value.strip())


def _has_specific_field_constraint(value: str) -> bool:
    lowered = value.casefold()
    return any(
        token in lowered
        for token in (
            "missing",
            "incomplete",
            "partial",
            "completion",
            "imputation",
            "reconstruction",
            "robust",
            "unavailable",
            "absent",
        )
    )


def _dedupe(values) -> list[str]:
    seen = OrderedDict()
    for value in values:
        text = str(value).strip()
        if text:
            seen.setdefault(text.casefold(), text)
    return list(seen.values())
