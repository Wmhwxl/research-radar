"""回归测试：preprint 维护链路在「抓取零结果 / 上游不可用」时的行为契约。

背景：bioRxiv / medRxiv / ChemRxiv 三条链路曾长期全红，根因是
  fetcher 抓到 0 篇时不写输出文件 → sync.py 因缺文件抛 FileNotFoundError → 整条流水线崩。
同时 cleanup 跑在 fetch 之前，导致「删了旧数据却没补上新数据」，把表逐日削空。

本文件锁住修复后的四条契约：
  1. 抓取结果一律落盘，0 篇时写空数组；
  2. 所有窗口都抓失败时非零退出（上游故障必须可见，不能静默绿）；
  3. 有窗口失败时不推进水位线，避免失败区间被永久跳过；
  4. cleanup / sync 在非 arXiv 源解析不出表名时报错，拒绝回退到 arxiv_papers。
"""

import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class PreprintFetcherEmptyResultTest(unittest.TestCase):
    """三个 fetcher 的落盘与水位线契约。"""

    SOURCES = ("biorxiv", "medrxiv")  # 这两个是窗口式抓取，chemrxiv 走整包数据集

    @classmethod
    def setUpClass(cls):
        if str(SRC) not in sys.path:
            sys.path.insert(0, str(SRC))
        cls.mods = {
            name: _load_module(
                f"fetch_{name}_resilience_mod",
                SRC / "maintain" / "fetchers" / f"fetch_{name}.py",
            )
            for name in cls.SOURCES
        }

    def _run_fetch(self, name, *, window_side_effect, tmpdir):
        """跑一次抓取，把窗口请求打桩，返回 (输出文件路径, 水位线是否推进, 抛出的异常)。"""
        mod = self.mods[name]
        out = os.path.join(tmpdir, f"{name}_out.json")
        advanced = {"seen": False, "crawl": False}

        orig_fetch = mod.fetch_window_records
        orig_seen = mod.save_seen_state
        orig_crawl = mod.save_last_crawl_at
        orig_load_seen = mod.load_seen_state
        mod.fetch_window_records = window_side_effect
        mod.save_seen_state = lambda *a, **k: advanced.__setitem__("seen", True)
        mod.save_last_crawl_at = lambda *a, **k: advanced.__setitem__("crawl", True)
        mod.load_seen_state = lambda *a, **k: (set(), None)
        try:
            error = None
            try:
                getattr(mod, f"fetch_{name}_metadata")(
                    days=1, output_file=out, chunk_days=1, ignore_seen=True
                )
            except SystemExit as exc:
                error = exc
            return out, advanced, error
        finally:
            mod.fetch_window_records = orig_fetch
            mod.save_seen_state = orig_seen
            mod.save_last_crawl_at = orig_crawl
            mod.load_seen_state = orig_load_seen

    def test_zero_result_still_writes_empty_array(self):
        """契约 1：窗口请求成功但没有新论文时，必须写出 [] 而不是不写文件。"""
        for name in self.SOURCES:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as tmp:
                out, advanced, error = self._run_fetch(
                    name, window_side_effect=lambda s, e, **k: [], tmpdir=tmp
                )
                self.assertIsNone(error, f"{name}: 零结果不应抛异常")
                self.assertTrue(
                    os.path.exists(out), f"{name}: 零结果时必须落盘，否则下游 sync 会因缺文件崩溃"
                )
                with open(out, encoding="utf-8") as f:
                    self.assertEqual(json.load(f), [], f"{name}: 应写空数组")

    def test_zero_result_still_advances_watermark(self):
        """契约 3 的反面：窗口成功、只是没有新论文时，水位线应正常推进。"""
        for name in self.SOURCES:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as tmp:
                _, advanced, _ = self._run_fetch(
                    name, window_side_effect=lambda s, e, **k: [], tmpdir=tmp
                )
                self.assertTrue(advanced["crawl"], f"{name}: 抓取成功时应推进 last_crawl_at")

    def test_all_windows_failed_exits_nonzero(self):
        """契约 2：所有窗口都抓失败属于上游故障，必须非零退出而不是静默返回 0 篇。"""

        def boom(_s, _e, **_k):
            raise RuntimeError("upstream unreachable")

        for name in self.SOURCES:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as tmp:
                _, _, error = self._run_fetch(name, window_side_effect=boom, tmpdir=tmp)
                self.assertIsInstance(
                    error, SystemExit, f"{name}: 全部窗口失败时必须 SystemExit"
                )
                self.assertIn("上游不可用", str(error))

    def test_failed_windows_do_not_advance_watermark(self):
        """契约 3：有窗口失败时不得推进水位线，否则失败区间会被下次运行永久跳过。"""

        def boom(_s, _e, **_k):
            raise RuntimeError("upstream unreachable")

        for name in self.SOURCES:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as tmp:
                _, advanced, _ = self._run_fetch(name, window_side_effect=boom, tmpdir=tmp)
                self.assertFalse(
                    advanced["crawl"], f"{name}: 抓取失败时不得推进 last_crawl_at"
                )
                self.assertFalse(advanced["seen"], f"{name}: 抓取失败时不得保存 seen 状态")

    def test_failed_windows_still_write_output(self):
        """契约 1 的补充：即使全窗口失败也要落盘，保证下游拿到确定性的输入。"""

        def boom(_s, _e, **_k):
            raise RuntimeError("upstream unreachable")

        for name in self.SOURCES:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as tmp:
                out, _, _ = self._run_fetch(name, window_side_effect=boom, tmpdir=tmp)
                self.assertTrue(os.path.exists(out), f"{name}: 失败时也应写出空数组")


class CleanupOrderContractTest(unittest.TestCase):
    """契约：cleanup 必须排在同步成功之后，否则「只删不补」会逐日削空表。"""

    def test_cleanup_runs_after_sync_in_all_entrypoints(self):
        for name in ("arxiv", "biorxiv", "medrxiv", "chemrxiv"):
            with self.subTest(source=name):
                text = (SRC / "maintain" / f"{name}.py").read_text(encoding="utf-8")
                cleanup_at = text.index("cleanup_backend(")
                run_at = text.index('run_step("Maintain')
                self.assertGreater(
                    cleanup_at,
                    run_at,
                    f"{name}.py: cleanup_backend 必须在 run_step 之后，"
                    "否则抓取失败时会先删旧数据却补不上新数据",
                )


class NoArxivFallbackTest(unittest.TestCase):
    """契约 4：非 arXiv 源解析不出表名时必须报错，不得静默落到 arxiv_papers。"""

    @classmethod
    def setUpClass(cls):
        for p in (str(SRC), str(SRC / "maintain")):
            if p not in sys.path:
                sys.path.insert(0, p)

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("SUPABASE_PAPERS_TABLE", "DPR_DISABLE_DOTENV")}
        os.environ.pop("SUPABASE_PAPERS_TABLE", None)
        os.environ["DPR_DISABLE_DOTENV"] = "1"

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_sync_resolve_papers_table_refuses_arxiv_fallback(self):
        mod = _load_module("sync_fallback_mod", SRC / "maintain" / "sync.py")
        config_patch = patch.object(mod, 'load_config', return_value={'supabase': {'papers_table': 'arxiv_papers'}})
        config_patch.start()
        self.addCleanup(config_patch.stop)
        self.assertEqual(
            mod.resolve_papers_table("", "arxiv"),
            "arxiv_papers",
            "arXiv 应保持历史默认，不受影响",
        )
        for backend in ("medrxiv", "biorxiv", "chemrxiv"):
            with self.subTest(backend=backend):
                self.assertEqual(
                    mod.resolve_papers_table("", backend),
                    "",
                    f"{backend} 解析不出表名时必须返回空，而不是 arxiv_papers",
                )

    def test_cleanup_config_raises_for_unresolved_non_arxiv_backend(self):
        mod = _load_module("cleanup_fallback_mod", SRC / "maintain" / "cleanup.py")
        config_patch = patch.object(mod, 'load_config', return_value={'supabase': {'papers_table': 'arxiv_papers'}})
        config_patch.start()
        self.addCleanup(config_patch.stop)
        cfg = mod.resolve_supabase_config(
            backend_key="arxiv", url="https://example.supabase.co", papers_table="", schema=""
        )
        self.assertEqual(cfg["papers_table"], "arxiv_papers")

        with self.assertRaises(SystemExit) as ctx:
            mod.resolve_supabase_config(
                backend_key="medrxiv", url="https://example.supabase.co", papers_table="", schema=""
            )
        self.assertIn("拒绝回退到 arxiv_papers", str(ctx.exception))

        cfg = mod.resolve_supabase_config(
            backend_key="medrxiv",
            url="https://example.supabase.co",
            papers_table="medrxiv_papers",
            schema="",
        )
        self.assertEqual(cfg["papers_table"], "medrxiv_papers", "显式传表名时应正常工作")


class InitZeroResultGuardTest(unittest.TestCase):
    """契约：preprint 的 init 脚本要和 init_arxiv 一样做零结果前置检查。"""

    def test_preprint_inits_have_zero_result_guard(self):
        for name in ("biorxiv", "medrxiv", "chemrxiv"):
            with self.subTest(source=name):
                text = (SRC / "maintain" / f"init_{name}.py").read_text(encoding="utf-8")
                self.assertIn(
                    "count_raw_rows",
                    text,
                    f"init_{name}.py 缺少零结果前置检查，零篇时会把 sync 拉起来然后崩",
                )
                self.assertIn("已跳过 Supabase 同步", text)

    def test_preprint_inits_pass_explicit_papers_table(self):
        """契约 4 的配套：三个 preprint init 必须像 11 个会议 init 那样显式传表名，
        不依赖 SUPABASE_PAPERS_TABLE 环境变量，避免漏配时解析失败或写错表。"""
        for name in ("biorxiv", "medrxiv", "chemrxiv"):
            with self.subTest(source=name):
                text = (SRC / "maintain" / f"init_{name}.py").read_text(encoding="utf-8")
                self.assertIn('"--papers-table",', text, f"init_{name}.py 未显式传 --papers-table")
                self.assertIn(f'"{name}_papers",', text, f"init_{name}.py 的表名不正确")


if __name__ == "__main__":
    unittest.main()
