"""Actions 启动前实测云端 embedding/rerank；不读取论文库、不调用 DeepSeek。"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-lightweight", action="store_true")
    args = parser.parse_args()
    if args.require_lightweight:
        unexpected = [
            name
            for name in ("torch", "transformers", "sentence_transformers")
            if importlib.util.find_spec(name)
        ]
        if unexpected:
            raise RuntimeError("云端工作流不应依赖本地模型库：" + ",".join(unexpected))
    from model_loader import load_sentence_transformer
    from reranker_api import SiliconFlowReranker
    import numpy as np

    model = load_sentence_transformer("BAAI/bge-small-en-v1.5", device="cpu")
    if not model.is_remote or model.allow_local_fallback:
        raise RuntimeError("要求云端 embedding 且禁止本地回退")
    vectors = model.encode(["query: asymmetric traveling salesman problem"])
    if (
        vectors.shape != (1, 384)
        or not np.isfinite(vectors).all()
        or np.linalg.norm(vectors[0]) < 1e-8
    ):
        raise RuntimeError("云端 embedding 与384维论文库不兼容")
    spec = importlib.util.spec_from_file_location(
        "cloud_rank_check", ROOT / "src/3.rank_papers.py"
    )
    rank = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rank)
    cfg = rank._resolve_rerank_profile_config(
        os.getenv("RERANK_PROFILE") or "public-zwwen-rerank"
    )
    provider = rank._normalize_rerank_provider(
        cfg.get("provider") or os.getenv("RERANK_PROVIDER") or "public_zwwen"
    )
    if provider not in ("public_zwwen", "siliconflow"):
        raise RuntimeError("必须使用云端 reranker")
    client = SiliconFlowReranker(
        api_key=rank._resolve_remote_api_key(provider),
        base_url=rank._resolve_remote_base_url(provider, cfg),
    )
    response = client.rerank(
        query="asymmetric traveling salesman problem",
        documents=[
            "An approximation algorithm for the asymmetric traveling salesman problem.",
            "Measurements of galaxy colors using a telescope.",
        ],
        top_n=2,
        model=cfg.get("model") or "Qwen/Qwen3-Reranker-0.6B",
    )
    results = response.get("results") or response.get("data") or []
    if (
        not isinstance(results, list)
        or len(results) != 2
        or {row.get("index") for row in results} != {0, 1}
    ):
        raise RuntimeError("云端 reranker 未返回完整的两条测试结果")
    print(
        json.dumps(
            {
                "cloud_models": "passed",
                "embedding_dimensions": 384,
                "reranker_provider": provider,
                "rerank_results": len(results),
                "local_model_dependencies": (
                    False if args.require_lightweight else "not_required"
                ),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
