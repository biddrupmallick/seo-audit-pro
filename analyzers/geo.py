import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from crawler.spider import CrawledPage


STAT_PATTERN = re.compile(r"\b\d+(\.\d+)?\s*(%|percent|million|billion|thousand)\b", re.IGNORECASE)
AUTHOR_PATTERNS = [
    re.compile(r"\bby\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b"),
    re.compile(r"\bauthor[:\s]+[A-Z][a-z]", re.IGNORECASE),
    re.compile(r"\bwritten\s+by\b", re.IGNORECASE),
    re.compile(r'class=["\'][^"\']*author[^"\']*["\']', re.IGNORECASE),
    re.compile(r'itemprop=["\']author["\']', re.IGNORECASE),
]

DATE_PATTERNS = [
    re.compile(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}\b", re.IGNORECASE),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r'class=["\'][^"\']*date[^"\']*["\']', re.IGNORECASE),
    re.compile(r'itemprop=["\']datePublished["\']', re.IGNORECASE),
]

CITE_PATTERNS = re.compile(r"\baccording\s+to\b|\bsource[s]?:|\bcited?\s+by\b|\breferences?\b|\bstudies?\s+show\b", re.IGNORECASE)


def analyze_page_geo(html: str, url: str, brand_name: str = "") -> Dict[str, Any]:
    """Analyze a single page for GEO (Generative Engine Optimization) signals."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return {"url": url, "geo_score": 0, "signals": []}

    signals = []
    geo_score = 0
    page_text = soup.get_text(" ", strip=True)
    html_str = str(soup)

    # 1. Author byline
    has_author = any(p.search(html_str) for p in AUTHOR_PATTERNS)
    if has_author:
        signals.append("Has author byline (E-E-A-T signal)")
        geo_score += 15

    # 2. Publication date
    has_date = any(p.search(html_str) for p in DATE_PATTERNS)
    if has_date:
        signals.append("Has publication/update date (freshness signal)")
        geo_score += 10

    # 3. Statistics and data
    stat_matches = STAT_PATTERN.findall(page_text)
    if len(stat_matches) >= 2:
        signals.append(f"Contains {len(stat_matches)} statistical data point(s)")
        geo_score += min(15, len(stat_matches) * 3)

    # 4. Citation/source references
    if CITE_PATTERNS.search(page_text):
        signals.append("References external sources/citations")
        geo_score += 10

    # 5. FAQ content
    faq_present = False
    for heading in soup.find_all(["h2", "h3"]):
        text = heading.get_text(strip=True).lower()
        if "faq" in text or "frequently asked" in text:
            faq_present = True
    if soup.find("details") or faq_present:
        signals.append("Has FAQ content")
        geo_score += 10

    # 6. Clear page purpose (topic focus)
    h1_tags = soup.find_all("h1")
    has_clear_topic = len(h1_tags) == 1 and len(h1_tags[0].get_text(strip=True)) > 10
    if has_clear_topic:
        signals.append("Has single clear H1 (clear topic focus)")
        geo_score += 10

    # 7. Structured content (headings hierarchy)
    h2_count = len(soup.find_all("h2"))
    h3_count = len(soup.find_all("h3"))
    if h2_count >= 2:
        signals.append(f"Well-structured content with {h2_count} H2 sections")
        geo_score += min(10, h2_count * 2)

    # 8. Brand name mentioned
    if brand_name and brand_name.lower() in page_text.lower():
        signals.append(f"Brand name '{brand_name}' mentioned in content")
        geo_score += 10

    # 9. Content length (longer, more comprehensive content)
    word_count = len(page_text.split())
    if word_count >= 500:
        signals.append(f"Substantial content ({word_count} words)")
        geo_score += min(10, (word_count // 200))

    # 10. Social proof / reviews
    review_patterns = re.compile(r"\breview[s]?\b|\btestimoni[a-z]+\b|\brating[s]?\b|\bstar[s]?\b", re.IGNORECASE)
    if review_patterns.search(page_text):
        signals.append("Contains social proof/review content")
        geo_score += 5

    # 11. Lists and structured answers (good for AI summarization)
    ul_count = len(soup.find_all("ul"))
    ol_count = len(soup.find_all("ol"))
    if ul_count + ol_count >= 2:
        signals.append(f"Contains {ul_count + ol_count} list(s) for structured information")
        geo_score += 5

    geo_score = min(100, geo_score)

    return {
        "url": url,
        "geo_score": geo_score,
        "signals": signals,
        "has_author": has_author,
        "has_date": has_date,
        "stat_count": len(stat_matches),
        "word_count": len(page_text.split()),
        "h2_count": h2_count,
        "has_faq": faq_present,
    }


def analyze_geo(pages: List[CrawledPage]) -> Dict[str, Any]:
    """Analyze GEO readiness across all pages."""
    html_pages = [p for p in pages if p.html and 200 <= p.status_code < 300]

    if not html_pages:
        return {
            "score": 0,
            "total_pages": 0,
            "page_results": [],
            "has_about_page": False,
            "has_contact_page": False,
            "brand_name": "",
            "summary": {
                "avg_geo_score": 0,
                "pages_with_author_byline": 0,
                "pages_with_statistics": 0,
                "high_geo_readiness_pages": 0,
            },
        }

    # Try to infer brand name from domain
    try:
        parsed = urlparse(html_pages[0].url)
        domain = parsed.netloc.replace("www.", "")
        brand_name = domain.split(".")[0].capitalize()
    except Exception:
        brand_name = ""

    # Check for about and contact pages
    all_urls_lower = [p.url.lower() for p in html_pages]
    has_about_page = any("about" in u for u in all_urls_lower)
    has_contact_page = any("contact" in u for u in all_urls_lower)

    page_results = []
    for page in html_pages:
        result = analyze_page_geo(page.html, page.url, brand_name)
        page_results.append(result)

    total = len(page_results)
    avg_score = sum(r["geo_score"] for r in page_results) / total
    pages_with_author = [r for r in page_results if r["has_author"]]
    pages_with_stats = [r for r in page_results if r["stat_count"] >= 2]
    pages_with_faq = [r for r in page_results if r["has_faq"]]
    high_geo_pages = [r for r in page_results if r["geo_score"] >= 50]

    # Bonus for site-level E-E-A-T
    if has_about_page:
        avg_score = min(100, avg_score + 5)
    if has_contact_page:
        avg_score = min(100, avg_score + 5)

    return {
        "score": round(avg_score, 1),
        "total_pages": total,
        "brand_name": brand_name,
        "has_about_page": has_about_page,
        "has_contact_page": has_contact_page,
        "page_results": sorted(page_results, key=lambda x: x["geo_score"], reverse=True),
        "summary": {
            "avg_geo_score": round(avg_score, 1),
            "has_about_page": has_about_page,
            "has_contact_page": has_contact_page,
            "pages_with_author_byline": len(pages_with_author),
            "pages_with_statistics": len(pages_with_stats),
            "pages_with_faq": len(pages_with_faq),
            "high_geo_readiness_pages": len(high_geo_pages),
        },
    }
