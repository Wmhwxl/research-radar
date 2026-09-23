"""官方会议 program 备用源：稳定 ID、详情补全和旧年份名单检测。"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import re
import time
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests


def title_key(title: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", title).casefold())


def program_paper_id(conference: str, year: int, title: str) -> str:
    # 同一年份的 program 与正式论文集复用 ID，避免来源切换时重复入库。
    digest = hashlib.sha256(title_key(title).encode("utf-8")).hexdigest()[:24]
    return f"{conference.lower()}-{year}-{digest}"


def get_html(url: str) -> str:
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            if not response.encoding or response.encoding.lower() == "iso-8859-1":
                response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except requests.RequestException as exc:
            if attempt == 2 or (exc.response is not None and exc.response.status_code == 404):
                raise
            time.sleep(attempt + 1)
    raise RuntimeError(f"Could not fetch {url}")


def _record(conference: str, year: int, title: str, authors: list[str], url: str) -> dict:
    return {
        "id": program_paper_id(conference, year, title), "title": title, "authors": authors,
        "source": f"{conference}-{year}-Accepted-Program", "abstract": "", "pdf_url": "",
        "link": url, "primary_category": f"{conference}-{year}", "categories": [f"{conference}-{year}"],
        # Program 未提供出版日期时按年份占位，正式论文集接管后更新。
        "published": f"{year}-01-01T00:00:00+00:00",
    }


def parse_eccv_program(html: str, year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    for node in soup.select("tr"):
        link = node.find("a", href=re.compile(rf"^/virtual/{year}/poster/\d+/?$"))
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        author_node = node.select_one(".indented i")
        authors = [a.strip() for a in author_node.get_text(" ", strip=True).split("⋅") if a.strip()] if author_node else []
        if not title or not authors:
            raise ValueError("ECCV program paper missing title/authors")
        row = _record("ECCV", year, title, authors, urljoin("https://eccv.ecva.net", link["href"]))
        row["source_paper_id"] = link["href"].rstrip("/").rsplit("/", 1)[-1]
        keyword_node = node.select_one(".elc-keywords")
        if keyword_node:
            row["categories"] += [k.strip() for k in keyword_node.get_text(" ", strip=True).split(";") if k.strip()]
        session = node.select_one(".elc-where")
        row["session"] = session.get_text(" ", strip=True) if session else ""
        if year == 2026:
            row["published"] = "2026-09-08T00:00:00+00:00"
        previous = result.get(row["id"])
        if previous and set(previous["authors"]) != set(authors):
            raise ValueError(f"ECCV title collision: {title}")
        result[row["id"]] = row
    return list(result.values())


def parse_eccv_detail(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    abstract = soup.select_one(".abstract-text-inner") or soup.select_one(".abstract-content")
    pdf = next((a for a in soup.select("a[href]") if a.get_text(" ", strip=True).casefold() == "paper pdf"), None)
    return {"abstract": abstract.get_text(" ", strip=True) if abstract else "",
            "pdf_url": urljoin(url, pdf["href"]) if pdf else ""}


def fetch_eccv_program(year: int, *, workers: int = 8) -> list[dict]:
    rows = parse_eccv_program(get_html(f"https://eccv.ecva.net/Conferences/{year}/AcceptedPapers"), year)
    if not rows:
        raise ValueError(f"ECCV {year}: official program has no papers")
    def enrich(row):
        try:
            detail = parse_eccv_detail(get_html(row["link"]), row["link"])
            if not detail["abstract"]:
                print(f"[WARN] ECCV detail missing abstract: {row['link']}", flush=True)
            return dict(row, **detail)
        except requests.RequestException as exc:
            print(f"[WARN] ECCV detail unavailable: {row['link']}: {type(exc).__name__}", flush=True)
            return row
    result = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for future in as_completed([pool.submit(enrich, row) for row in rows]):
            result.append(future.result())
            if len(result) % 100 == 0 or len(result) == len(rows):
                print(f"[ECCV program] {len(result)}/{len(rows)}", flush=True)
    return sorted(result, key=lambda row: row["id"])


def parse_emnlp_program(html: str, year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    url = f"https://{year}.emnlp.org/program/main_papers/"
    rows = {}
    for node in soup.select(".page__content li"):
        title, authors = node.find("strong"), node.find("em")
        if not title or not authors:
            continue
        row = _record("EMNLP", year, title.get_text(" ", strip=True),
                      [a.strip() for a in authors.get_text(" ", strip=True).split(",") if a.strip()], url)
        if not row["title"] or not row["authors"]:
            continue
        previous = rows.get(row["id"])
        if previous and set(previous["authors"]) != set(row["authors"]):
            raise ValueError(f"EMNLP title collision: {row['title']}")
        rows[row["id"]] = row
    return list(rows.values())


def reject_stale_program(rows: list[dict], previous_titles: list[str]) -> None:
    if not rows or not previous_titles:
        raise ValueError("Cannot verify program year without current and previous lists")
    previous = {title_key(t) for t in previous_titles}
    overlap = sum(title_key(row["title"]) in previous for row in rows)
    if overlap / len(rows) >= 0.8:
        raise ValueError(f"Program repeats previous year: {overlap}/{len(rows)} titles; refusing import")


def fetch_emnlp_program(year: int) -> list[dict]:
    rows = parse_emnlp_program(get_html(f"https://{year}.emnlp.org/program/main_papers/"), year)
    previous = BeautifulSoup(get_html(f"https://aclanthology.org/volumes/{year - 1}.emnlp-main/"), "html.parser")
    pattern = re.compile(rf"^/{year - 1}\.emnlp-main\.[1-9]\d*/?$")
    titles = [a.get_text(" ", strip=True) for a in previous.select("a[href]") if pattern.match(a["href"])]
    reject_stale_program(rows, titles)
    old = {title_key(t) for t in titles}
    return [row for row in rows if title_key(row["title"]) not in old]
