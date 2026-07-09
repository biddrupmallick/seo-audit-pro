import re
from typing import List, Dict, Any
from collections import Counter
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from crawler.spider import CrawledPage
from config import TITLE_MIN_LENGTH, TITLE_MAX_LENGTH, META_DESC_MAX_LENGTH

# Stop words for title-starts-with-keyword check
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "as", "be", "was", "are",
    "this", "that", "your", "our", "we", "my", "its",
}


def _url_has_only_ids(url: str) -> bool:
    """Return True if URL slug appears to be only numeric IDs or random strings."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return False
    segments = [s for s in path.split("/") if s]
    if not segments:
        return False
    last_segment = segments[-1]
    # If last segment is purely numeric
    if re.match(r"^\d+$", last_segment):
        return True
    # If last segment looks like a UUID/hash (hex, long strings of numbers)
    if re.match(r"^[0-9a-f\-]{8,}$", last_segment, re.IGNORECASE):
        return True
    return False


def _count_internal_links(soup: BeautifulSoup, base_domain: str) -> int:
    """Count internal links on the page."""
    count = 0
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        if href.startswith("http"):
            parsed = urlparse(href)
            link_domain = parsed.netloc.lstrip("www.")
            base = base_domain.lstrip("www.")
            if link_domain == base or link_domain.endswith("." + base):
                count += 1
        else:
            count += 1
    return count


def _first_paragraph_word_count(soup: BeautifulSoup) -> int:
    """Return word count of first non-empty paragraph."""
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text:
            return len(re.findall(r"\b\w+\b", text))
    return 0


def _title_starts_with_keyword(title: str) -> bool:
    """Return True if the title starts with a non-stop word."""
    if not title:
        return False
    words = title.split()
    if not words:
        return False
    first_word = words[0].lower().strip("\"'.,!?:;")
    return first_word not in STOP_WORDS


def extract_onpage_data(html: str, url: str) -> Dict[str, Any]:
    """Extract on-page SEO elements from HTML."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return {}

    # Title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Meta description
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = ""
    if meta_desc_tag and meta_desc_tag.get("content"):
        meta_desc = meta_desc_tag["content"].strip()

    # Canonical
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical = ""
    if canonical_tag and canonical_tag.get("href"):
        canonical = canonical_tag["href"].strip()

    # H1 tags
    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]

    # H2 tags
    h2_tags = [h.get_text(strip=True) for h in soup.find_all("h2")]

    # H3 tags
    h3_tags = [h.get_text(strip=True) for h in soup.find_all("h3")]

    # Meta robots
    robots_tag = soup.find("meta", attrs={"name": "robots"})
    robots = ""
    if robots_tag and robots_tag.get("content"):
        robots = robots_tag["content"].strip()

    # OG tags
    og_title = ""
    og_desc = ""
    og_tag = soup.find("meta", property="og:title")
    if og_tag:
        og_title = og_tag.get("content", "")
    og_desc_tag = soup.find("meta", property="og:description")
    if og_desc_tag:
        og_desc = og_desc_tag.get("content", "")

    # NEW: Keyword in URL check
    url_has_only_ids = _url_has_only_ids(url)

    # NEW: Internal link count
    parsed_url = urlparse(url)
    base_domain = parsed_url.netloc
    internal_link_count = _count_internal_links(soup, base_domain)

    # NEW: First paragraph length
    first_para_word_count = _first_paragraph_word_count(soup)
    first_para_too_long = first_para_word_count > 150

    # NEW: Title starts with keyword
    title_starts_with_keyword = _title_starts_with_keyword(title)

    return {
        "url": url,
        "title": title,
        "title_length": len(title),
        "meta_description": meta_desc,
        "meta_description_length": len(meta_desc),
        "canonical": canonical,
        "h1_tags": h1_tags,
        "h1_count": len(h1_tags),
        "h2_tags": h2_tags,
        "h2_count": len(h2_tags),
        "h3_tags": h3_tags,
        "robots": robots,
        "og_title": og_title,
        "og_description": og_desc,
        "url_has_only_ids": url_has_only_ids,
        "internal_link_count": internal_link_count,
        "first_para_word_count": first_para_word_count,
        "first_para_too_long": first_para_too_long,
        "title_starts_with_keyword": title_starts_with_keyword,
    }


def analyze_onpage(pages: List[CrawledPage]) -> Dict[str, Any]:
    """Analyze on-page SEO issues."""
    html_pages = [p for p in pages if p.html and 200 <= p.status_code < 300]

    page_data = []
    for page in html_pages:
        data = extract_onpage_data(page.html, page.url)
        if data:
            page_data.append(data)

    # Missing title
    missing_title = [d for d in page_data if not d["title"]]

    # Title too short
    title_too_short = [
        d for d in page_data
        if d["title"] and d["title_length"] < TITLE_MIN_LENGTH
    ]

    # Title too long
    title_too_long = [
        d for d in page_data
        if d["title"] and d["title_length"] > TITLE_MAX_LENGTH
    ]

    # Duplicate titles
    title_counter = Counter(d["title"] for d in page_data if d["title"])
    duplicate_titles = [
        {"title": title, "count": count, "urls": [d["url"] for d in page_data if d["title"] == title]}
        for title, count in title_counter.items()
        if count > 1
    ]

    # Missing meta description
    missing_meta_desc = [d for d in page_data if not d["meta_description"]]

    # Meta description too long
    meta_desc_too_long = [
        d for d in page_data
        if d["meta_description"] and d["meta_description_length"] > META_DESC_MAX_LENGTH
    ]

    # Duplicate meta descriptions
    meta_counter = Counter(d["meta_description"] for d in page_data if d["meta_description"])
    duplicate_meta_descs = [
        {"meta_description": desc, "count": count, "urls": [d["url"] for d in page_data if d["meta_description"] == desc]}
        for desc, count in meta_counter.items()
        if count > 1
    ]

    # Missing H1
    missing_h1 = [d for d in page_data if d["h1_count"] == 0]

    # Multiple H1s
    multiple_h1 = [d for d in page_data if d["h1_count"] > 1]

    # Missing H2
    missing_h2 = [d for d in page_data if d["h2_count"] == 0]

    # Missing canonical
    missing_canonical = [d for d in page_data if not d["canonical"]]

    # Pages with noindex
    noindex_pages = [d for d in page_data if "noindex" in d["robots"].lower()]

    # NEW: Pages with only ID/number in URL slug
    url_only_ids = [d for d in page_data if d.get("url_has_only_ids", False)]

    # NEW: Pages with first paragraph too long (>150 words)
    first_para_too_long_pages = [d for d in page_data if d.get("first_para_too_long", False)]

    # NEW: Average internal links
    total_internal = sum(d.get("internal_link_count", 0) for d in page_data)
    avg_internal_links = round(total_internal / len(page_data), 1) if page_data else 0.0

    # NEW: Pages where title does not start with keyword
    title_not_starting_keyword = [d for d in page_data if d["title"] and not d.get("title_starts_with_keyword", True)]

    total = len(page_data)
    score = 100.0
    if total > 0:
        score -= (len(missing_title) / total) * 20
        score -= (len(title_too_long) / total) * 8
        score -= (len(title_too_short) / total) * 5
        score -= (len(duplicate_titles) / max(1, len(title_counter))) * 10
        score -= (len(missing_meta_desc) / total) * 15
        score -= (len(meta_desc_too_long) / total) * 5
        score -= (len(duplicate_meta_descs) / max(1, len(meta_counter))) * 8
        score -= (len(missing_h1) / total) * 15
        score -= (len(multiple_h1) / total) * 5
        score -= (len(missing_h2) / total) * 9
        score -= (len(url_only_ids) / total) * 3
        score -= (len(first_para_too_long_pages) / total) * 2
    score = max(0.0, min(100.0, score))

    return {
        "score": round(score, 1),
        "total_html_pages": total,
        "page_data": page_data,
        "missing_title": missing_title,
        "title_too_short": title_too_short,
        "title_too_long": title_too_long,
        "duplicate_titles": duplicate_titles,
        "missing_meta_description": missing_meta_desc,
        "meta_description_too_long": meta_desc_too_long,
        "duplicate_meta_descriptions": duplicate_meta_descs,
        "missing_h1": missing_h1,
        "multiple_h1": multiple_h1,
        "missing_h2": missing_h2,
        "missing_canonical": missing_canonical,
        "noindex_pages": noindex_pages,
        "url_only_ids": url_only_ids,
        "first_para_too_long_pages": first_para_too_long_pages,
        "title_not_starting_keyword": title_not_starting_keyword,
        "summary": {
            "missing_title": len(missing_title),
            "title_too_short": len(title_too_short),
            "title_too_long": len(title_too_long),
            "duplicate_titles": len(duplicate_titles),
            "missing_meta_description": len(missing_meta_desc),
            "meta_description_too_long": len(meta_desc_too_long),
            "duplicate_meta_descriptions": len(duplicate_meta_descs),
            "missing_h1": len(missing_h1),
            "multiple_h1": len(multiple_h1),
            "missing_h2": len(missing_h2),
            "missing_canonical": len(missing_canonical),
            "noindex_pages": len(noindex_pages),
            "url_only_ids": len(url_only_ids),
            "first_para_too_long": len(first_para_too_long_pages),
            "avg_internal_links": avg_internal_links,
            "title_not_starting_keyword": len(title_not_starting_keyword),
        },
    }
