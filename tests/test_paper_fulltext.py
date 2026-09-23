import importlib.util
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
spec = importlib.util.spec_from_file_location(
    "fulltext_generator", Path(__file__).resolve().parents[1] / "src/6.generate_docs.py"
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)
FULLTEXT = "# Introduction\n" + "Actual paper body and proof. " * 150


def test_invalid_cache_is_replaced_by_real_fulltext(tmp_path, monkeypatch):
    target = tmp_path / "paper.txt"
    target.write_text("")
    fetch = Mock(return_value=FULLTEXT)
    monkeypatch.setattr(generator, "fetch_paper_markdown_via_jina", fetch)
    assert (
        generator.ensure_text_content("https://arxiv.org/pdf/2510.17595v1", str(target))
        == FULLTEXT
    )
    assert target.read_text() == FULLTEXT
    fetch.assert_called_once()
    generator.ensure_text_content("https://arxiv.org/pdf/2510.17595v1", str(target))
    fetch.assert_called_once()


def test_error_response_is_not_published_as_fulltext(tmp_path, monkeypatch):
    target = tmp_path / "paper.txt"
    monkeypatch.setattr(
        generator,
        "fetch_paper_markdown_via_jina",
        lambda _: "<html>Access denied</html>" * 100,
    )
    response = Mock(content=b"<html>not a pdf</html>")
    monkeypatch.setattr(generator.requests, "get", lambda *a, **k: response)
    with pytest.raises(ValueError):
        generator.ensure_text_content("https://arxiv.org/pdf/2510.17595v1", str(target))
    assert not target.exists()


def test_withdrawn_pdf_notice_is_not_a_paper(tmp_path, monkeypatch):
    notice = (
        "Title: arXiv\nWarning: Target URL returned error 404\nThis version has been withdrawn and is unavailable\n"
        + "navigation " * 200
    )
    assert not generator.is_usable_paper_text(notice)
    monkeypatch.setattr(generator, "fetch_paper_markdown_via_jina", lambda _: notice)
    monkeypatch.setattr(
        generator.requests, "get", lambda *a, **k: Mock(status_code=404)
    )
    with pytest.raises(generator.PaperFulltextUnavailable):
        generator.ensure_text_content(
            "https://arxiv.org/pdf/2509.26073v2", str(tmp_path / "paper.txt")
        )
