from typing import List, Dict, Any
from collections import Counter
from bs4 import BeautifulSoup
from crawler.spider import CrawledPage
from config import TITLE_MIN_LENGTH, TITLE_MAX_LENGTH, META_DESC_MAX_LENGTH


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
        },
    }
