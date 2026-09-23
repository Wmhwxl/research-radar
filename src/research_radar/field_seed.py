from __future__ import annotations

import argparse

from src.research_radar.config import load_research_radar_env
from src.research_radar.models import ResearchField
from src.research_radar.repository import SupabaseResearchRadarRepository


DEMO_FIELD_SLUG = "incomplete-multimodal-recommendation"


def demo_research_field() -> ResearchField:
    return ResearchField(
        id=None,
        slug=DEMO_FIELD_SLUG,
        name="Incomplete Multimodal Recommendation",
        description="Multimodal recommender systems under missing, incomplete, unavailable, or partially observed modality conditions.",
        core_keywords=[
            "multimodal recommendation",
            "incomplete multimodal recommendation",
            "missing modality",
            "missing modalities",
            "modality completion",
            "robust multimodal recommendation",
        ],
        optional_keywords=[
            "recommendation",
            "recommender",
            "multimodal",
            "multi-modal",
            "missing",
            "incomplete",
            "completion",
            "imputation",
            "robust",
        ],
        intent_queries=[
            "papers studying multimodal recommender systems under missing modality conditions",
            "methods for completing or estimating missing modalities in multimodal recommendation",
            "robust multimodal recommendation with incomplete visual text or audio information",
            "recommendation methods handling partially observed multimodal features",
        ],
        keyword_groups={
            "recommendation": [
                "recommendation",
                "recommendations",
                "recommender",
                "recommenders",
                "recommender system",
                "personalized recommendation",
            ],
            "multimodal": [
                "multimodal",
                "multi-modal",
                "visual",
                "textual",
                "image",
                "audio",
                "acoustic",
                "modality",
                "modalities",
            ],
            "missingness": [
                "missing",
                "incomplete",
                "partial",
                "partially observed",
                "unavailable",
                "absent",
                "missing modality",
                "missing modalities",
                "modality missingness",
            ],
            "recovery": [
                "completion",
                "imputation",
                "reconstruction",
                "recovery",
                "robust",
                "robustness",
                "corrupted",
            ],
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update the Research Radar demo field.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    load_research_radar_env()
    field = demo_research_field()
    if args.dry_run:
        print(field)
        return 0
    repo = SupabaseResearchRadarRepository()
    row_id = repo.upsert_research_field(field)
    print(f"upserted {field.slug}: {row_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
