from __future__ import annotations

from dataclasses import dataclass

from src.research_radar.models import CandidatePaper, NormalizedPaper


@dataclass(frozen=True)
class PaperIdentity:
    key_type: str
    key: str


def identity_keys(paper: NormalizedPaper) -> list[PaperIdentity]:
    keys: list[PaperIdentity] = []
    if paper.openalex_id:
        keys.append(PaperIdentity("openalex_id", paper.openalex_id))
    if paper.doi:
        keys.append(PaperIdentity("doi", paper.doi.casefold()))
    if paper.arxiv_id:
        keys.append(PaperIdentity("arxiv_id", paper.arxiv_id.casefold()))
    if paper.normalized_title and paper.year:
        keys.append(PaperIdentity("title_year", f"{paper.normalized_title}|{paper.year}"))
    return keys


def primary_identity_key(paper: NormalizedPaper) -> PaperIdentity:
    keys = identity_keys(paper)
    if not keys:
        raise ValueError("paper has no usable identity key")
    return keys[0]


class CandidateAggregator:
    def __init__(self) -> None:
        self._candidates: dict[str, CandidatePaper] = {}
        self._aliases: dict[PaperIdentity, str] = {}

    def add(self, paper: NormalizedPaper, *, lane_id: str, query: str) -> CandidatePaper:
        canonical = self._find_canonical_key(paper)
        if canonical is None:
            canonical = primary_identity_key(paper).key
            self._candidates[canonical] = CandidatePaper(paper=paper)
        candidate = self._candidates[canonical]
        for identity in identity_keys(paper):
            self._aliases[identity] = canonical
        if lane_id not in candidate.matched_lanes:
            candidate.matched_lanes.append(lane_id)
        if query not in candidate.matched_queries:
            candidate.matched_queries.append(query)
        candidate.retrieval_count += 1
        candidate.retrieval_evidence.setdefault("identities", [identity.__dict__ for identity in identity_keys(paper)])
        return candidate

    def values(self) -> list[CandidatePaper]:
        return list(self._candidates.values())

    def _find_canonical_key(self, paper: NormalizedPaper) -> str | None:
        for identity in identity_keys(paper):
            if identity in self._aliases:
                return self._aliases[identity]
        return None

