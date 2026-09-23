"""从论文 PDF 提取有明确边界的原文摘要，不生成或猜测摘要。"""

import re

import requests


def extract_abstract_text(text: str) -> str:
    start = re.search(r"(?im)^\s*abstract\s*(?:[:.—–]\s*|\n)", text)
    if not start:
        return ""
    tail = text[start.end():]
    end = re.search(r"(?m)^\s*1(?:\.\s*|\s+)(?=[A-Z])", tail)
    if not end:
        return ""
    raw = tail[:end.start()]
    note = re.search(r"(?m)^\s*[†‡*]\s*(?:Work|Equal|Corresponding|These authors)\b", raw)
    if note:
        raw = raw[:note.start()]
    raw = re.sub(r"(https?):\s*//\s*", r"\1://", raw)
    raw = re.sub(r"(https?://\S*[/_-])[ \t]*\n[ \t]*", r"\1", raw)
    abstract = re.sub(r"\s+", " ", raw).strip()
    # 缺边界、扫描件或明显混入全文时留空，交由人工核查。
    return abstract if 200 <= len(abstract) <= 6000 else ""


def extract_pdf_abstract(content: bytes) -> str:
    import fitz

    with fitz.open(stream=content, filetype="pdf") as doc:
        text = "\n".join(
            doc[i].get_text(flags=fitz.TEXTFLAGS_TEXT | fitz.TEXT_DEHYPHENATE)
            for i in range(min(2, len(doc)))
        )
    return extract_abstract_text(text)


def fetch_pdf_abstract(url: str) -> str:
    # 只在网页确实缺摘要时使用；限制下载大小，避免异常 PDF 占用过多内存。
    with requests.get(url, timeout=30, stream=True) as response:
        response.raise_for_status()
        chunks = []
        size = 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 32 * 1024 * 1024:
                raise ValueError("PDF exceeds 32 MiB")
            chunks.append(chunk)
    content = b"".join(chunks)
    if not content.startswith(b"%PDF"):
        raise ValueError("Response is not a PDF")
    return extract_pdf_abstract(content)
