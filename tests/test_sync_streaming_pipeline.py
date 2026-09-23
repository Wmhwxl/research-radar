import importlib.util
import json
import pathlib
import sys
import unittest
from unittest.mock import patch, Mock


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class SyncStreamingPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("sync_stream_mod", src_dir / "maintain" / "sync.py")

    def test_configure_local_embedding_runtime_reserves_upload_cpus(self):
        with patch.object(self.mod.os, "cpu_count", return_value=64):
            with patch.object(self.mod, "torch") as mock_torch:
                embed_cpus, reserved = self.mod.configure_local_embedding_runtime(2)

        self.assertEqual(embed_cpus, 62)
        self.assertEqual(reserved, 2)
        mock_torch.set_num_threads.assert_called_once_with(62)
        mock_torch.set_num_interop_threads.assert_called_once()

    def test_stream_embed_and_upsert_submits_chunks_incrementally(self):
        rows = [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}]
        upload_calls = []

        def fake_iter(*args, **kwargs):
            del args, kwargs
            yield ([{"id": "p1"}, {"id": "p2"}], 384)
            yield ([{"id": "p3"}], 384)

        def fake_upsert(**kwargs):
            upload_calls.append([row["id"] for row in kwargs["rows"]])

        with patch.object(self.mod, "iter_embedded_row_chunks", side_effect=fake_iter):
            with patch.object(self.mod, "upsert_papers", side_effect=fake_upsert):
                dim = self.mod.stream_embed_and_upsert(
                    rows=rows,
                    url="https://example.supabase.co",
                    service_key="service-key",
                    table="neurips_openreview_papers",
                    schema="public",
                    model_name="BAAI/bge-small-en-v1.5",
                    devices=["cpu"],
                    embed_batch_size=16,
                    embed_chunk_size=2,
                    embed_max_length=0,
                    embed_local_only=True,
                    upload_workers=1,
                    max_pending_upload_chunks=1,
                    upsert_batch_size=200,
                    upsert_timeout=120,
                    upsert_retries=3,
                    upsert_retry_wait=1.0,
                )

        self.assertEqual(dim, 384)
        self.assertEqual(upload_calls, [["p1", "p2"], ["p3"]])

    def test_upsert_groups_optional_fields_without_clearing_existing_pdf(self):
        rows = [{"id": "a", "pdf_url": "https://example.org/a.pdf"},
                {"id": "b"}, {"id": "c", "pdf_url": "https://example.org/c.pdf"}]
        with patch.object(self.mod.requests, "post", return_value=Mock(status_code=201)) as post:
            self.mod.upsert_papers(url="https://example.org", service_key="test", table="papers",
                                   rows=rows, batch_size=100, retries=0)
        payloads = [json.loads(call.kwargs['data']) for call in post.call_args_list]
        self.assertEqual(len(payloads), 2)
        self.assertEqual(sorted(r['id'] for batch in payloads for r in batch), ['a', 'b', 'c'])
        for batch in payloads:
            self.assertEqual(len({frozenset(row) for row in batch}), 1)
        row_b = next(row for batch in payloads for row in batch if row['id'] == 'b')
        self.assertNotIn('pdf_url', row_b)


if __name__ == "__main__":
    unittest.main()
