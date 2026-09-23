import json
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from long_range_native import publish_native_reports


def test_existing_report_uses_native_sidebar_and_markdown_without_model(tmp_path):
    token = "20250910-20260909-aaaaaaaaaaaa"
    folder = tmp_path / "docs/long-range" / token
    folder.mkdir(parents=True)
    sidebar = tmp_path / "docs/_sidebar.md"
    sidebar.write_text("* [首页](/)\n* Daily Papers\n  * 旧日报\n* Conference Papers\n")
    paper = {
        "id": "2510.17595v1",
        "title": "ATSP test",
        "abstract": "Actual abstract",
        "score": 8,
        "reason": "实际评审理由",
        "evidence": "ATSP",
        "bucket": "core",
    }
    (folder / "a-core-1.json").write_text(json.dumps([paper]))
    manifest = {
        "start": "2025-09-10",
        "end_exclusive": "2026-09-10",
        "generated_at": "2026-09-10T00:00:00Z",
        "groups": [{"tag": "ATSP", "buckets": {"core": {"pages": ["a-core-1.json"]}}}],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with patch(
        "requests.sessions.Session.request", side_effect=AssertionError("禁止网络调用")
    ):
        publish_native_reports(tmp_path)
        before = sidebar.read_text()
        publish_native_reports(tmp_path)
    assert sidebar.read_text() == before
    assert "旧日报" in before and "* Conference Papers" in before
    assert "<!--dpr-date:20250910-20260909-->" in before
    assert 'href="#/20250910-20260909/2510.17595v1"' in before
    assert "index.html" not in before
    markdown = (tmp_path / "docs/20250910-20260909/2510.17595v1.md").read_text()
    assert markdown.startswith("---\n")
    assert "Actual abstract" in markdown and "实际评审理由" in markdown
    assert "query:ATSP" in markdown and "paper:待复核" not in markdown
    state = json.loads(
        (tmp_path / "docs/20250910-20260909/_daily_state.json").read_text()
    )
    assert len(state["papers"]) == 1
    assert {"kind": "query", "label": "ATSP"} in state["papers"][0]["tags"]
    assert (tmp_path / "docs/20250910-20260909/README.md").exists()
    meta = json.loads(
        (tmp_path / "docs/20250910-20260909/papers.meta.json").read_text()
    )
    assert len(meta["papers"]) == 1


def test_native_export_merges_topics_and_preserves_conference_and_user_document(
    tmp_path,
):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "_sidebar.md").write_text(
        "* Daily Papers\n* Conference Papers\n  * 我的会议\n"
    )
    for fingerprint, topic, bucket, score in [
        ("aaaaaaaaaaaa", "ATSP", "core", 8),
        ("bbbbbbbbbbbb", "RL", "review", 9),
    ]:
        folder = docs / "long-range" / ("20250910-20260909-" + fingerprint)
        folder.mkdir(parents=True)
        filename = f"a-{bucket}-1.json"
        (folder / filename).write_text(
            json.dumps(
                [
                    {
                        "id": "2510.17595v1",
                        "title": "ATSP",
                        "score": score,
                        "bucket": bucket,
                    }
                ]
            )
        )
        (folder / "manifest.json").write_text(
            json.dumps(
                {
                    "start": "2025-09-10",
                    "end_exclusive": "2026-09-10",
                    "generated_at": "2026-09-10",
                    "groups": [
                        {
                            "tag": topic,
                            "buckets": {
                                bucket: {"pages": [filename]},
                                "excluded": {"pages": ["must-not-be-read.json"]},
                            },
                        }
                    ],
                }
            )
        )
    publish_native_reports(tmp_path)
    page = docs / "20250910-20260909/2510.17595v1.md"
    assert "query:ATSP" in page.read_text() and "query:RL" in page.read_text()
    page.write_text("用户已有精读内容，不能覆盖")
    publish_native_reports(tmp_path)
    assert page.read_text() == "用户已有精读内容，不能覆盖"
    sidebar = (docs / "_sidebar.md").read_text()
    assert "* Conference Papers\n  * 我的会议" in sidebar
    assert sidebar.count('href="#/20250910-20260909/2510.17595v1"') == 1


def test_reject_unsafe_report_page_path(tmp_path):
    folder = tmp_path / "docs/long-range/a"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "start": "2025-09-10",
                "end_exclusive": "2026-09-10",
                "generated_at": "",
                "groups": [
                    {
                        "tag": "ATSP",
                        "buckets": {"core": {"pages": ["../../secret.private"]}},
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="无效回溯分页路径"):
        publish_native_reports(tmp_path)


def test_fulltext_option_fetches_pdf_markdown_at_native_chat_route(tmp_path):
    folder = tmp_path / "docs/long-range/report"
    folder.mkdir(parents=True)
    (folder / "a-core-1.json").write_text(
        json.dumps(
            [{"id": "2510.17595v1", "title": "ATSP", "score": 8, "bucket": "core"}]
        )
    )
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "start": "2025-09-10",
                "end_exclusive": "2026-09-10",
                "generated_at": "",
                "groups": [
                    {"tag": "ATSP", "buckets": {"core": {"pages": ["a-core-1.json"]}}}
                ],
            }
        )
    )
    from unittest.mock import Mock

    content = "# Introduction\n" + "Full proof, not an abstract. " * 100
    response = Mock(status_code=200, text=content)
    with patch("requests.get", return_value=response) as get:
        publish_native_reports(tmp_path, with_fulltext=True)
        get.assert_called_once()
    assert (
        tmp_path / "docs/20250910-20260909/2510.17595v1.txt"
    ).read_text() == content.strip()
