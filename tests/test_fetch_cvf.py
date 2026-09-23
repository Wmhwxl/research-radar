from src.maintain.fetchers.fetch_cvf import _parse_cvpr_list


def test_cvpr_pdf_after_author_sibling_and_no_cross_paper_leak():
    html = '''<dl>
    <dt class="ptitle"><a href="/first.html">First</a></dt>
    <dd>Alice, Bob</dd><dd><a href="/first.pdf">pdf</a></dd>
    <dt class="ptitle"><a href="/missing.html">Missing</a></dt><dd>Carol</dd>
    <dt class="ptitle"><a href="/last.html">Last</a></dt>
    <dd><a href="/last.pdf">pdf</a></dd></dl>'''
    rows = _parse_cvpr_list(html, 2026)
    assert [row['pdf_url'] for row in rows] == [
        'https://openaccess.thecvf.com/first.pdf', '',
        'https://openaccess.thecvf.com/last.pdf',
    ]
