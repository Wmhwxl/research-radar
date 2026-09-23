"""真实匿名 RPC 回归：三专题 × 两个窗口，不调用付费模型或写数据库。"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

from benchmark_long_range_retrieval import TOPICS, load_local_env, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--end", required=True, help="UTC 半开窗口结束日期")
    parser.add_argument("--match-count", type=int, default=20)
    parser.add_argument("--days", type=int, nargs="+", default=[365, 90])
    parser.add_argument(
        "--topics", nargs="+", choices=list(TOPICS), default=list(TOPICS)
    )
    parser.add_argument("--baseline-dir", help="可选：旧实验的 Top-500 向量结果目录")
    args = parser.parse_args()
    if not 1 <= args.match_count <= 1000:
        parser.error("匿名接口验证数量必须在1到1000内，避免触发REST行数截断")
    if any(d <= 0 for d in args.days):
        parser.error("时间窗口必须为正数")
    import requests
    import torch
    from sentence_transformers import SentenceTransformer

    load_local_env()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    model = SentenceTransformer(
        "BAAI/bge-small-en-v1.5", device="cpu", local_files_only=True
    )
    vectors = model.encode(
        ["query: " + TOPICS[t]["query"] for t in args.topics], normalize_embeddings=True
    )
    save(out / "queries.json", dict(zip(args.topics, vectors.tolist())))
    key = os.environ["SUPABASE_ANON_KEY"]
    headers = {"apikey": key, "Authorization": "Bearer " + key}
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    results = []
    for topic, vector in zip(args.topics, vectors):
        for days in args.days:
            start = end - timedelta(days=days)
            for lane in ("exact", "bm25"):
                payload = {
                    "match_count": args.match_count,
                    "filter_published_start": start.isoformat(),
                    "filter_published_end": end.isoformat(),
                }
                payload["query_embedding" if lane == "exact" else "query_text"] = (
                    vector.tolist()
                    if lane == "exact"
                    else {
                        "atsp": "ATSP",
                        "sr": "symbolic regression",
                        "rl": "reinforcement learning",
                    }[topic]
                )
                began = time.monotonic()
                try:
                    response = requests.post(
                        os.environ["SUPABASE_URL"].rstrip("/")
                        + "/rest/v1/rpc/match_arxiv_papers_"
                        + lane,
                        headers=headers,
                        json=payload,
                        timeout=75,
                    )
                    record = {
                        "topic": topic,
                        "days": days,
                        "lane": lane,
                        "status": response.status_code,
                        "seconds": time.monotonic() - began,
                        "data": response.json(),
                        "errors": [],
                    }
                    if not response.ok:
                        record["errors"].append("http_error")
                    else:
                        rows = record["data"]
                        assert isinstance(rows, list)
                        if len(rows) > args.match_count:
                            record["errors"].append("too_many_rows")
                        if len({r["id"] for r in rows}) != len(rows):
                            record["errors"].append("duplicate_version_id")
                        field = "similarity" if lane == "exact" else "score"
                        if any(
                            float(a[field]) < float(b[field]) - 1e-8
                            for a, b in zip(rows, rows[1:])
                        ):
                            record["errors"].append("not_sorted")
                        for row in rows:
                            published = datetime.fromisoformat(
                                row["published"].replace("Z", "+00:00")
                            )
                            if not start <= published < end:
                                record["errors"].append("outside_window")
                            if not row.get("title") or not row.get("abstract"):
                                record["errors"].append("missing_metadata")
                        if args.baseline_dir and lane == "exact":
                            baseline = json.loads(
                                (
                                    Path(args.baseline_dir)
                                    / f"{topic}-{days}-vector.json"
                                ).read_text()
                            )
                            expected = sorted(
                                baseline, key=lambda r: (-r["similarity"], r["id"])
                            )[: args.match_count]
                            actual = {r["id"]: r for r in rows}
                            # 对边界同分允许不同顺序，不能以近似向量结果替代精确 Top-K。
                            cutoff = expected[-1]["similarity"] if expected else 0
                            if len(rows) != len(expected):
                                record["errors"].append("wrong_count_vs_exact_baseline")
                            for row in expected:
                                if (
                                    row["similarity"] > cutoff + 1e-7
                                    and row["id"] not in actual
                                ):
                                    record["errors"].append("missing_exact_top_id")
                            if any(r["similarity"] < cutoff - 1e-7 for r in rows):
                                record["errors"].append("below_exact_cutoff")
                            for row in rows:
                                old = next(
                                    (r for r in baseline if r["id"] == row["id"]), None
                                )
                                if (
                                    old
                                    and abs(row["similarity"] - old["similarity"])
                                    > 1e-7
                                ):
                                    record["errors"].append("changed_similarity")
                except (requests.RequestException, ValueError, AssertionError) as exc:
                    record = {
                        "topic": topic,
                        "days": days,
                        "lane": lane,
                        "seconds": time.monotonic() - began,
                        "errors": [type(exc).__name__],
                    }
                results.append(record)
                save(out / "results.json", results)
                print(
                    topic,
                    days,
                    lane,
                    record.get("status"),
                    round(record["seconds"], 2),
                    record["errors"],
                    flush=True,
                )
    failures = [r for r in results if r["errors"]]
    save(
        out / "summary.json",
        {
            "end_exclusive": end.isoformat(),
            "match_count": args.match_count,
            "total": len(results),
            "passed": len(results) - len(failures),
            "failures": [{k: v for k, v in r.items() if k != "data"} for r in failures],
            "timings": [{k: v for k, v in r.items() if k != "data"} for r in results],
        },
    )
    if failures:
        raise SystemExit(f"{len(failures)} RPC cases failed")


if __name__ == "__main__":
    main()
