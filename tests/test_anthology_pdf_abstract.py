from unittest.mock import MagicMock, patch

import fitz
import pytest

from src.maintain.fetchers import fetch_acl_anthology as anthology


def test_extract_pdf_abstract_stops_at_numbered_section():
    from src.maintain.pdf_abstract import extract_abstract_text
    body = 'This paper studies language models and presents a reproducible evaluation. ' * 5
    text = 'Paper title\nAuthors\nAbstract\n' + body + '\n1\nIntroduction\nNot part of abstract.'
    assert extract_abstract_text(text) == body.strip()


def test_extract_pdf_abstract_rejects_missing_boundary():
    from src.maintain.pdf_abstract import extract_abstract_text
    assert extract_abstract_text('Abstract\n' + 'Long body text. ' * 100) == ''
    assert extract_abstract_text('Title\n1 Introduction\nMain text.') == ''


def test_extract_excludes_author_note_and_repairs_wrapped_url():
    from src.maintain.pdf_abstract import extract_abstract_text
    body = 'We present an evaluation of language models. ' * 6
    text = 'Abstract\n' + body + 'Code: https://github.com/\nteam/project\n†Work was done elsewhere.\n1\nMotivation\nBody.'
    assert extract_abstract_text(text) == body + 'Code: https://github.com/team/project'


def test_extract_real_pdf_bytes():
    from src.maintain.pdf_abstract import extract_pdf_abstract
    body = 'We evaluate language models on carefully controlled tasks. ' * 5
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(50, 50, 550, 700),
                            'Paper\nAbstract\n' + body + '\n1 Introduction\nBody text.', fontsize=11)
        content = doc.tobytes()
    assert extract_pdf_abstract(content) == body.strip()


def test_pdf_download_rejects_html_response():
    from src.maintain import pdf_abstract
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [b'<!DOCTYPE html>Login page']
    with patch.object(pdf_abstract.requests, 'get', return_value=response):
        with pytest.raises(ValueError, match='not a PDF'):
            pdf_abstract.fetch_pdf_abstract('https://example.org/paper.pdf')


def test_anthology_missing_web_abstract_falls_back_to_pdf():
    page = '''<meta name="citation_title" content="Paper">
    <meta name="citation_pdf_url" content="https://aclanthology.org/2025.emnlp-main.1.pdf">'''
    with patch.object(anthology, '_get', return_value=page), \
         patch.object(anthology, 'fetch_pdf_abstract', create=True, return_value='PDF abstract.') as fetch:
        row = anthology.fetch_anthology_paper('https://aclanthology.org/2025.emnlp-main.1/',
                                              source_label='EMNLP-2025-Main', primary_category='EMNLP')
    assert row['abstract'] == 'PDF abstract.'
    fetch.assert_called_once()


def test_anthology_existing_abstract_does_not_download_pdf():
    page = '<meta name="citation_title" content="Paper"><div id="abstract">Abstract Official text.</div>'
    with patch.object(anthology, '_get', return_value=page), \
         patch.object(anthology, 'fetch_pdf_abstract', create=True) as fetch:
        row = anthology.fetch_anthology_paper('https://aclanthology.org/2025.emnlp-main.1/',
                                              source_label='EMNLP-2025-Main', primary_category='EMNLP')
    assert row['abstract'] == 'Official text.'
    fetch.assert_not_called()
