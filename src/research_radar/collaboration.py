from __future__ import annotations

from src.research_radar.repository import ResearchRadarRepository


def rebuild_author_collaborations(repo: ResearchRadarRepository, field_id: str) -> int:
    return repo.rebuild_collaborations(field_id)

