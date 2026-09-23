from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from src.research_radar.models import CandidatePaper, QueryLane, RelevanceDecision, ResearchField
from src.research_radar.query_builder import keyword_groups_for_field


CORE = "core"
RELATED = "related"
REJECTED = "rejected"


def evaluate_candidate(
    candidate: CandidatePaper,
    field: ResearchField,
    lanes: Iterable[QueryLane] | None = None,
) -> RelevanceDecision:
    paper = candidate.paper
    groups = keyword_groups_for_field(field)
    title = paper.title or ""
    abstract = paper.abstract or ""
    topic_text = " ".join(topic.name for topic in paper.topics)
    full_text = " ".join([title, abstract, topic_text])
    title_matches = _matched_by_group(title, groups)
    abstract_matches = _matched_by_group(abstract, groups)
    topic_matches = _matched_by_group(topic_text, groups)
    matched_terms = _merge_matches(title_matches, abstract_matches, topic_matches)
    generic_terms = _generic_terms(field)
    generic_matches = _match_terms(full_text, generic_terms)

    components = {
        "recommendation": _component(matched_terms, "recommendation"),
        "multimodal": _component(matched_terms, "multimodal"),
        "missingness": _component(matched_terms, "missingness"),
        "recovery": _component(matched_terms, "recovery"),
        "title_bonus": min(0.12, sum(len(v) for v in title_matches.values()) * 0.03),
        "abstract_score": min(0.08, sum(len(v) for v in abstract_matches.values()) * 0.01),
        "topic_score": min(0.05, sum(len(v) for v in topic_matches.values()) * 0.02),
        "query_lane_score": _lane_score(candidate, lanes),
        "generic_score": min(0.45, len(generic_matches) * 0.18),
    }
    score = min(
        1.0,
        components["recommendation"] * 0.22
        + components["multimodal"] * 0.22
        + components["missingness"] * 0.22
        + components["recovery"] * 0.12
        + components["title_bonus"]
        + components["abstract_score"]
        + components["topic_score"]
        + components["query_lane_score"],
    )
    excluded = _match_terms(full_text, field.excluded_keywords)
    recommendation = components["recommendation"] > 0
    multimodal = components["multimodal"] > 0
    hard_recovery_terms = [
        term
        for term in matched_terms.get("recovery", [])
        if term.casefold() not in {"robust", "robustness", "corrupted"}
    ]
    incomplete = components["missingness"] > 0 or bool(hard_recovery_terms)
    reason_codes: list[str] = []
    if excluded:
        reason_codes.append("excluded_keyword")
    if recommendation:
        reason_codes.append("recommendation_signal")
    if multimodal:
        reason_codes.append("multimodal_signal")
    if incomplete:
        reason_codes.append("missingness_or_recovery_signal")
    if len(candidate.matched_lanes) > 1:
        reason_codes.append("multi_lane_match")

    if excluded:
        label = REJECTED
    elif _is_generic_field(groups) and generic_matches and components["generic_score"] + components["query_lane_score"] >= 0.18:
        label = RELATED
        reason_codes.append("generic_field_match")
    elif recommendation and multimodal and incomplete and score >= 0.55:
        label = CORE
    elif recommendation and multimodal and score >= 0.42:
        label = RELATED
    else:
        label = REJECTED

    evidence = {
        "matched_lanes": list(candidate.matched_lanes),
        "matched_queries": list(candidate.matched_queries),
        "retrieval_count": candidate.retrieval_count,
        "matched_terms": matched_terms,
        "title_terms": title_matches,
        "abstract_terms": abstract_matches,
        "topic_terms": topic_matches,
        "generic_terms": generic_matches,
        "components": components,
        "excluded_terms": excluded,
    }
    return RelevanceDecision(
        score=round(score, 4),
        label=label,
        accepted=label in {CORE, RELATED},
        evidence=evidence,
        reason_codes=reason_codes,
        matched_terms=matched_terms,
    )


def _component(matches: dict[str, list[str]], group: str) -> float:
    return min(1.0, len(matches.get(group, [])) / 2.0)


def _is_generic_field(groups: dict[str, list[str]]) -> bool:
    return not (groups.get("recommendation") and groups.get("multimodal"))


def _generic_terms(field: ResearchField) -> list[str]:
    return _dedupe([*field.core_keywords, *field.optional_keywords, *field.intent_queries, field.name])


def _lane_score(candidate: CandidatePaper, lanes: Iterable[QueryLane] | None) -> float:
    weights = {lane.id: lane.weight for lane in lanes or []}
    raw = sum(weights.get(lane_id, 0.4) for lane_id in set(candidate.matched_lanes))
    return min(0.17, raw * 0.08)


def _matched_by_group(text: str, groups: dict[str, list[str]]) -> dict[str, list[str]]:
    return {group: _match_terms(text, terms) for group, terms in groups.items() if _match_terms(text, terms)}


def _merge_matches(*items: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = defaultdict(list)
    for item in items:
        for group, terms in item.items():
            for term in terms:
                if term not in merged[group]:
                    merged[group].append(term)
    return dict(merged)


def _match_terms(text: str, terms: Iterable[str]) -> list[str]:
    normalized = text.casefold()
    matched = []
    for term in terms:
        cleaned = str(term).strip()
        if not cleaned:
            continue
        pattern = r"(?<!\w)" + re.escape(cleaned.casefold()) + r"(?!\w)"
        if re.search(pattern, normalized):
            matched.append(cleaned)
    return matched


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: dict[str, str] = {}
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned:
            seen.setdefault(cleaned.casefold(), cleaned)
    return list(seen.values())
