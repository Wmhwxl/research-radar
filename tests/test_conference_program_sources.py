from unittest.mock import patch

import pytest

from src.maintain.fetchers import fetch_cvf
from src.maintain.fetchers import fetch_acl_anthology as anthology


def test_eccv_falls_back_when_ecva_has_no_target_year():
    with patch.object(fetch_cvf, '_get', return_value=type('Response', (), {'text': '<html></html>'})()), \
         patch.object(fetch_cvf, 'fetch_eccv_program', create=True, return_value=[{'id': 'new'}]) as fallback:
        assert fetch_cvf.fetch_eccv(2026, 2) == [{'id': 'new'}]
    fallback.assert_called_once_with(2026, workers=2)


def test_ecva_year_must_be_directory_not_paper_number():
    html = '<dt class="ptitle"><a href="/papers/eccv_2024/html/2026_ECCV_paper.php">Old paper</a></dt>'
    assert fetch_cvf._parse_eccv_list(html, 2026) == []


def test_eccv_program_deduplicates_and_ignores_other_years():
    from src.maintain.conference_program import parse_eccv_program
    row = '<tr><td><a href="/virtual/2026/poster/123">New Paper</a><div class="indented"><i>Alice ⋅ Bob</i></div></td><td class="elc-keywords">Vision</td><td class="elc-where">Poster Session 1</td></tr>'
    rows = parse_eccv_program('<table>' + row * 2 + row.replace('/2026/', '/2024/') + '</table>', 2026)
    assert len(rows) == 1
    assert rows[0]['authors'] == ['Alice', 'Bob']
    assert 'Vision' in rows[0]['categories']


def test_eccv_detail_uses_paper_pdf_not_footer_proceedings():
    from src.maintain.conference_program import parse_eccv_detail
    html = '<div class="abstract-text-inner">Real abstract.</div><a href="https://media.eventhosts.cc/Conferences/ECCV2026/pdfs/42.pdf">Paper PDF</a><a href="https://example.org/2024.pdf">ECCV 2024 Proceedings</a>'
    result = parse_eccv_detail(html, 'https://eccv.ecva.net/virtual/2026/poster/123')
    assert result['abstract'] == 'Real abstract.'
    assert result['pdf_url'].endswith('/42.pdf')


def test_emnlp_rejects_recycled_previous_year_list():
    from src.maintain.conference_program import parse_emnlp_program, reject_stale_program
    html = '<section class="page__content"><li><strong>Old Paper</strong><em>Alice, Bob</em></li></section>'
    rows = parse_emnlp_program(html, 2026)
    with pytest.raises(ValueError, match='previous year'):
        reject_stale_program(rows, ['Old Paper'])


def test_emnlp_conflicting_duplicate_title_is_rejected():
    from src.maintain.conference_program import parse_emnlp_program
    html = '<section class="page__content"><li><strong>Same Paper</strong><em>Alice</em></li><li><strong>Same Paper</strong><em>Bob</em></li></section>'
    with pytest.raises(ValueError, match='collision'):
        parse_emnlp_program(html, 2026)


def test_program_and_proceedings_share_id():
    from src.maintain.conference_program import program_paper_id
    assert program_paper_id('EMNLP', 2026, 'New Paper!') == program_paper_id('emnlp', 2026, 'New paper')
    assert program_paper_id('ECCV', 2026, 'New Paper') != program_paper_id('ECCV', 2024, 'New Paper')


def test_emnlp_404_uses_verified_program_and_skips_missing_findings(tmp_path):
    import requests
    response = requests.Response()
    response.status_code = 404
    error = requests.HTTPError(response=response)
    target = tmp_path / 'papers.json'
    with patch.object(anthology, 'collect_volume_paper_urls', side_effect=error), \
         patch.object(anthology, 'fetch_emnlp_program', return_value=[{'id': 'verified-2026'}]) as fallback:
        anthology.fetch_anthology_conference(conference='EMNLP', year_end=2026, year_count=1,
            volume_specs=anthology.EMNLP_VOLUME_SPECS, output=str(target), workers=1)
    fallback.assert_called_once_with(2026)
    import json
    assert json.loads(target.read_text()) == [{'id': 'verified-2026'}]


def test_emnlp_stale_program_does_not_overwrite_output(tmp_path):
    target = tmp_path / 'papers.json'
    target.write_text('[{"id":"keep"}]')
    with patch.object(anthology, 'collect_volume_paper_urls', return_value=[]), \
         patch.object(anthology, 'fetch_emnlp_program', side_effect=ValueError('previous year')):
        with pytest.raises(ValueError, match='previous year'):
            anthology.fetch_anthology_conference(conference='EMNLP', year_end=2026, year_count=1,
                volume_specs=anthology.EMNLP_VOLUME_SPECS, output=str(target), workers=1)
    assert target.read_text() == '[{"id":"keep"}]'


def test_emnlp_formal_paper_reuses_program_id():
    from src.maintain.conference_program import program_paper_id
    html = '<meta name="citation_title" content="New Paper"><div id="abstract">Official abstract.</div>'
    with patch.object(anthology, '_get', return_value=html):
        row = anthology.fetch_anthology_paper('https://aclanthology.org/2026.emnlp-main.1/',
            source_label='EMNLP-2026-Main', primary_category='EMNLP-2026-Main')
    assert row['id'] == program_paper_id('EMNLP', 2026, 'New Paper')
    assert row['abstract'] == 'Official abstract.'


def test_eccv_formal_paper_reuses_program_id():
    from src.maintain.conference_program import program_paper_id
    entry = {'title': 'New Paper', 'detail_url': 'https://www.ecva.net/papers/eccv_2026/html/42.html',
             'pdf_url': 'https://www.ecva.net/papers/eccv_2026/papers/42.pdf'}
    with patch.object(fetch_cvf, '_fetch_detail', return_value={'abstract': 'Official abstract.', 'authors': ['Alice']}):
        row = fetch_cvf._build_paper(entry, 'ECCV', 2026, None)
    assert row['id'] == program_paper_id('ECCV', 2026, 'New Paper')
    assert row['pdf_url'] == entry['pdf_url']


def test_anthology_server_failure_does_not_switch_sources(tmp_path):
    import requests
    response = requests.Response()
    response.status_code = 503
    with patch.object(anthology, 'collect_volume_paper_urls', side_effect=requests.HTTPError(response=response)), \
         patch.object(anthology, 'fetch_emnlp_program') as fallback:
        with pytest.raises(requests.HTTPError):
            anthology.fetch_anthology_conference(conference='EMNLP', year_end=2026, year_count=1,
                volume_specs=anthology.EMNLP_VOLUME_SPECS, output=str(tmp_path / 'papers.json'), workers=1)
    fallback.assert_not_called()
