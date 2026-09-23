from __future__ import annotations

import argparse
import os
from collections import Counter
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

from src.providers.openalex import OpenAlexProvider
from src.research_radar.collaboration import rebuild_author_collaborations
from src.research_radar.config import load_research_radar_env
from src.research_radar.dedupe import CandidateAggregator, primary_identity_key
from src.research_radar.field_seed import DEMO_FIELD_SLUG, demo_research_field
from src.research_radar.models import CandidatePaper, QueryLane, ResearchField
from src.research_radar.query_builder import build_query_lanes
from src.research_radar.relevance import CORE, RELATED, evaluate_candidate
from src.research_radar.repository import ResearchRadarRepository, SupabaseResearchRadarRepository


def sync_field_history(
    *,
    field: ResearchField,
    provider: OpenAlexProvider,
    repository: ResearchRadarRepository | None,
    from_date: str,
    to_date: str,
    max_pages: int | None = None,
    dry_run: bool = False,
    resume_run_id: str | None = None,
    test_fail_before_checkpoint_on_page: int | None = None,
) -> dict[str, Any]:
    lanes = build_query_lanes(field)
    if not lanes:
        raise ValueError("research field produced no query lanes")
    run_id = None
    checkpoint = {
        "lane_index": 0,
        "lane_id": lanes[0].id,
        "cursor": "*",
        "pages_completed": 0,
        "completed_lanes": [],
        "last_successful_page": None,
    }
    if not dry_run and repository is None:
        raise ValueError("repository is required unless dry_run=True")
    if not dry_run and repository:
        if resume_run_id:
            run = repository.get_sync_run(resume_run_id)
            if not run:
                raise ValueError(f"sync run not found: {resume_run_id}")
            run_id = resume_run_id
            checkpoint.update(run.get("checkpoint") or {})
        else:
            run_id = repository.create_sync_run(
                field,
                provider=provider.name,
                from_date=from_date,
                to_date=to_date,
                queries=[asdict(lane) for lane in lanes],
            )

    page_budget = max_pages
    counters = Counter(
        candidates_retrieved=0,
        accepted_core=0,
        accepted_related=0,
        rejected=0,
        pages=0,
        papers_written=0,
        failures=0,
    )
    aggregator = CandidateAggregator()
    counted_candidate_keys: set[str] = set()
    samples: dict[str, list[dict[str, Any]]] = {"core": [], "related": [], "rejected": []}

    start_lane_index = int(checkpoint.get("lane_index") or 0)
    cursor = str(checkpoint.get("cursor") or "*")
    completed_lanes = list(checkpoint.get("completed_lanes") or [])
    for lane_index in range(start_lane_index, len(lanes)):
        lane = lanes[lane_index]
        if lane.id in completed_lanes:
            cursor = "*"
            continue
        while True:
            if page_budget is not None and counters["pages"] >= page_budget:
                if not dry_run and repository and field.id:
                    counters["collaborations_created"] = rebuild_author_collaborations(repository, field.id)
                _complete_if_needed(repository, run_id, dry_run, counters, status="partial")
                return _summary(field, lanes, counters, samples, checkpoint, run_id, dry_run)
            current_checkpoint = {
                "lane_index": lane_index,
                "lane_id": lane.id,
                "cursor": cursor,
                "pages_completed": counters["pages"],
                "completed_lanes": completed_lanes,
                "last_successful_page": checkpoint.get("last_successful_page"),
            }
            page = provider.search_works(
                query=lane.query,
                from_publication_date=from_date,
                to_publication_date=to_date,
                cursor=cursor,
                per_page=100 if not dry_run else 20,
            )
            page_candidates: list[CandidatePaper] = []
            for paper in page.items:
                candidate = aggregator.add(paper, lane_id=lane.id, query=lane.query)
                page_candidates.append(candidate)
            counters["candidates_retrieved"] += len(page.items)
            unique_page_candidates = list({_candidate_key(candidate): candidate for candidate in page_candidates}.values())
            decisions = [(candidate, evaluate_candidate(candidate, field, lanes)) for candidate in unique_page_candidates]
            try:
                for candidate, decision in decisions:
                    candidate_key = _candidate_key(candidate)
                    already_counted = candidate_key in counted_candidate_keys
                    if not already_counted:
                        counted_candidate_keys.add(candidate_key)
                        if decision.label == CORE:
                            counters["accepted_core"] += 1
                            _sample(samples["core"], candidate, decision)
                        elif decision.label == RELATED:
                            counters["accepted_related"] += 1
                            _sample(samples["related"], candidate, decision)
                        else:
                            counters["rejected"] += 1
                            _sample(samples["rejected"], candidate, decision)
                    if decision.label == CORE:
                        pass
                    elif decision.label == RELATED:
                        pass
                    else:
                        pass
                    if not dry_run and decision.accepted and repository and field.id:
                        repository.upsert_accepted_paper(field.id, candidate, decision)
                        if not already_counted:
                            counters["papers_written"] += 1
                if test_fail_before_checkpoint_on_page == counters["pages"] + 1:
                    raise RuntimeError(f"controlled failure before checkpoint on page {counters['pages'] + 1}")
            except Exception:
                counters["failures"] += 1
                # Do not advance checkpoint. The same lane+cursor will be retried on resume.
                if not dry_run and repository and run_id:
                    repository.update_sync_checkpoint(run_id, current_checkpoint, _sync_counter_payload(counters))
                raise

            counters["pages"] += 1
            next_cursor = page.next_cursor
            checkpoint = {
                "lane_index": lane_index,
                "lane_id": lane.id,
                "cursor": next_cursor or "*",
                "pages_completed": counters["pages"],
                "completed_lanes": completed_lanes,
                "last_successful_page": {
                    "lane_id": lane.id,
                    "cursor": cursor,
                    "next_cursor": next_cursor,
                    "items": len(page.items),
                },
            }
            if not next_cursor or not page.items:
                completed_lanes = [*completed_lanes, lane.id]
                checkpoint.update(
                    {
                        "lane_index": lane_index + 1,
                        "lane_id": lanes[lane_index + 1].id if lane_index + 1 < len(lanes) else None,
                        "cursor": "*",
                        "completed_lanes": completed_lanes,
                    }
                )
                cursor = "*"
                if not dry_run and repository and run_id:
                    repository.update_sync_checkpoint(run_id, checkpoint, _sync_counter_payload(counters))
                break
            cursor = next_cursor
            if not dry_run and repository and run_id:
                repository.update_sync_checkpoint(run_id, checkpoint, _sync_counter_payload(counters))

    if not dry_run and repository and field.id:
        counters["collaborations_created"] = rebuild_author_collaborations(repository, field.id)
    _complete_if_needed(repository, run_id, dry_run, counters, status="succeeded")
    return _summary(field, lanes, counters, samples, checkpoint, run_id, dry_run)


def _complete_if_needed(repository, run_id, dry_run: bool, counters: Counter, *, status: str) -> None:
    if not dry_run and repository and run_id:
        repository.complete_sync_run(run_id, status=status, counters=_sync_counter_payload(counters))


def _sync_counter_payload(counters: Counter) -> dict[str, int]:
    return {
        "candidates_retrieved": counters["candidates_retrieved"],
        "accepted_core": counters["accepted_core"],
        "accepted_related": counters["accepted_related"],
        "rejected": counters["rejected"],
        "failures": counters["failures"],
        "papers_inserted": counters["papers_written"],
        "collaborations_created": counters["collaborations_created"],
    }


def _sample(bucket: list[dict[str, Any]], candidate: CandidatePaper, decision) -> None:
    if len(bucket) >= 10:
        return
    bucket.append(
        {
            "title": candidate.paper.title,
            "year": candidate.paper.year,
            "openalex_id": candidate.paper.openalex_id,
            "score": decision.score,
            "label": decision.label,
            "matched_lanes": list(candidate.matched_lanes),
            "reason_codes": list(decision.reason_codes),
        }
    )


def _candidate_key(candidate: CandidatePaper) -> str:
    try:
        identity = primary_identity_key(candidate.paper)
        return f"{identity.key_type}:{identity.key}"
    except ValueError:
        return f"title:{candidate.paper.normalized_title}|{candidate.paper.year}"


def _summary(field, lanes, counters, samples, checkpoint, run_id, dry_run) -> dict[str, Any]:
    return {
        "field": {"id": field.id, "slug": field.slug, "name": field.name},
        "run_id": run_id,
        "dry_run": dry_run,
        "queries": [asdict(lane) for lane in lanes],
        "checkpoint": checkpoint,
        "counters": dict(counters),
        "samples": samples,
    }


def _resolve_dates(args) -> tuple[str, str]:
    if args.from_date and args.to_date:
        return args.from_date, args.to_date
    end = date.fromisoformat(args.to_date) if args.to_date else date.today()
    start = date.fromisoformat(args.from_date) if args.from_date else end - timedelta(days=max(args.years, 1) * 365)
    return start.isoformat(), end.isoformat()


def _load_field(args, repo: ResearchRadarRepository | None) -> ResearchField:
    if repo and (args.field_id or args.field_slug):
        field = repo.get_research_field(field_id=args.field_id, field_slug=args.field_slug)
        if field:
            return field
    if args.field_slug in (None, DEMO_FIELD_SLUG):
        field = demo_research_field()
        if repo and not args.dry_run:
            field_id = repo.upsert_research_field(field)
            return ResearchField.from_mapping({**asdict(field), "id": field_id})
        return field
    raise ValueError("research field not found; seed it first or use the demo slug")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Research Radar field history from OpenAlex.")
    parser.add_argument("--field-id")
    parser.add_argument("--field-slug", default=DEMO_FIELD_SLUG)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume-run-id")
    parser.add_argument("--test-fail-before-checkpoint-on-page", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    load_research_radar_env()
    if args.test_fail_before_checkpoint_on_page is not None and os.getenv("RESEARCH_RADAR_ENABLE_TEST_HOOKS") != "1":
        parser.error("controlled failure hooks require RESEARCH_RADAR_ENABLE_TEST_HOOKS=1")

    repo = None
    if not args.dry_run:
        repo = SupabaseResearchRadarRepository()
    field = _load_field(args, repo)
    from_date, to_date = _resolve_dates(args)
    summary = sync_field_history(
        field=field,
        provider=OpenAlexProvider(),
        repository=repo,
        from_date=from_date,
        to_date=to_date,
        max_pages=args.max_pages,
        dry_run=args.dry_run,
        resume_run_id=args.resume_run_id,
        test_fail_before_checkpoint_on_page=args.test_fail_before_checkpoint_on_page,
    )
    _print_summary(summary)
    return 0


def _print_summary(summary: dict[str, Any]) -> None:
    print(f"field: {summary['field']['name']}")
    print(f"dry_run: {summary['dry_run']}")
    print(f"run_id: {summary['run_id']}")
    print(f"queries: {len(summary['queries'])}")
    counters = summary["counters"]
    for key in ("pages", "candidates_retrieved", "accepted_core", "accepted_related", "rejected", "papers_written", "collaborations_created"):
        print(f"{key}: {counters.get(key, 0)}")
    for label in ("core", "related", "rejected"):
        print(f"\n{label} samples:")
        for item in summary["samples"][label]:
            print(f"- [{item['score']}] {item['title']} ({item['year']}) {item['openalex_id']}")


if __name__ == "__main__":
    raise SystemExit(main())
