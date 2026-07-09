import re
from typing import List, Dict, Any
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from crawler.spider import CrawledPage

# Date patterns for content freshness detection
DATE_PATTERNS = [
    re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b"),
    re.compile(r"\b\d{4}[\/\-]\d{2}[\/\-]\d{2}\b"),
    re.compile(r"\b(?:published|updated|posted|last\s+modified|date)[\s:]+\w+\s+\d+", re.IGNORECASE),
    re.compile(r"datetime=\"\d{4}-\d{2}-\d{2}\"", re.IGNORECASE),
]


def _extract_body_text(soup: BeautifulSoup) -> str:
    """Extract main body text, excluding nav/header/footer heuristically."""
    # Remove nav, header, footer, aside, script, style elements
    for tag in soup.find_all(["nav", "header", "footer", "aside", "script", "style", "noscript"]):
        tag.decompose()

    # Try to find main content area
    main = soup.find("main") or soup.find(id=re.compile(r"main|content|body|article", re.IGNORECASE))
    if main:
        return main.get_text(" ", strip=True)

    # Try article tag
    article = soup.find("article")
    if article:
        return article.get_text(" ", strip=True)

    # Fall back to body
    body = soup.find("body")
    if body:
        return body.get_text(" ", strip=True)

    return soup.get_text(" ", strip=True)


def _count_words(text: str) -> int:
    """Count words in text."""
    return len(re.findall(r"\b\w+\b", text))


def _avg_sentence_length(text: str) -> float:
    """Calculate average words per sentence."""
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if not sentences:
        return 0.0
    lengths = [len(re.findall(r"\b\w+\b", s)) for s in sentences]
    return round(sum(lengths) / len(lengths), 1)


def _avg_paragraph_length(soup: BeautifulSoup) -> float:
    """Calculate average paragraph length in words."""
    paragraphs = soup.find_all("p")
    if not paragraphs:
        return 0.0
    lengths = [_count_words(p.get_text(strip=True)) for p in paragraphs if p.get_text(strip=True)]
    if not lengths:
        return 0.0
    return round(sum(lengths) / len(lengths), 1)


def _first_paragraph_length(soup: BeautifulSoup) -> int:
    """Return word count of the first paragraph."""
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text:
            return _count_words(text)
    return 0


def _count_links(soup: BeautifulSoup, base_domain: str) -> tuple:
    """Return (internal_links, external_links) counts."""
    internal = 0
    external = 0
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        if href.startswith("http"):
            parsed = urlparse(href)
            link_domain = parsed.netloc.lstrip("www.")
            base = base_domain.lstrip("www.")
            if link_domain == base or link_domain.endswith("." + base):
                internal += 1
            else:
                external += 1
        else:
            internal += 1
    return internal, external


def _has_authority_links(soup: BeautifulSoup) -> bool:
    """Check for outbound links to authority domains (wikipedia, gov, edu)."""
    for a in soup.find_all("a", href=True):
        href = a["href"].strip().lower()
        if "wikipedia.org" in href or ".gov" in href or ".edu" in href:
            return True
    return False


def _has_fresh_content(html: str, soup: BeautifulSoup) -> bool:
    """Check if page has date patterns indicating fresh content."""
    # Check for <time> elements
    if soup.find("time"):
        return True
    # Check for datetime attributes
    for tag in soup.find_all(attrs={"datetime": True}):
        return True
    # Check text for date patterns
    text = soup.get_text(" ", strip=True)[:2000]
    for pattern in DATE_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _count_images(soup: BeautifulSoup) -> int:
    """Count img tags."""
    return len(soup.find_all("img"))


def _count_videos(soup: BeautifulSoup) -> int:
    """Count video tags and iframe embeds that look like video."""
    count = len(soup.find_all("video"))
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "").lower()
        if any(v in src for v in ["youtube.com", "youtu.be", "vimeo.com", "wistia.com", "loom.com", "dailymotion.com"]):
            count += 1
    return count


def _check_duplicate_content(page_data: List[Dict]) -> List[Dict]:
    """Detect near-duplicate content based on title and first 200 chars of content."""
    from collections import defaultdict

    # Group by title
    title_groups = defaultdict(list)
    for d in page_data:
        title = d.get("title", "").strip().lower()
        if title:
            title_groups[title].append(d["url"])

    # Group by first 200 chars of content
    content_groups = defaultdict(list)
    for d in page_data:
        snippet = d.get("content_snippet", "").strip().lower()[:200]
        if len(snippet) > 50:
            content_groups[snippet].append(d["url"])

    duplicates = []
    seen_groups = set()

    for title, urls in title_groups.items():
        if len(urls) > 1:
            key = ("title", title[:30])
            if key not in seen_groups:
                seen_groups.add(key)
                duplicates.append({
                    "type": "duplicate_title",
                    "title": title[:80],
                    "urls": urls[:10],
                })

    for snippet, urls in content_groups.items():
        if len(urls) > 1:
            key = ("content", snippet[:30])
            if key not in seen_groups:
                seen_groups.add(key)
                duplicates.append({
                    "type": "duplicate_content",
                    "title": snippet[:80],
                    "urls": urls[:10],
                })

    return duplicates[:20]


def analyze_content(pages: List[CrawledPage]) -> Dict[str, Any]:
    """Analyze content quality across all pages."""
    html_pages = [p for p in pages if p.html and 200 <= p.status_code < 300]

    if not html_pages:
        return {
            "score": 0.0,
            "page_results": [],
            "summary": {
                "avg_word_count": 0,
                "thin_content_pages": 0,
                "pages_with_video": 0,
                "avg_internal_links": 0.0,
                "avg_images_per_page": 0.0,
                "pages_with_fresh_content": 0,
            },
            "thin_content_pages": [],
            "duplicate_content_groups": [],
        }

    page_results = []

    for page in html_pages:
        url = page.url
        html = page.html or ""

        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            continue

        # Get base domain for link counting
        parsed_url = urlparse(url)
        base_domain = parsed_url.netloc

        body_text = _extract_body_text(BeautifulSoup(html, "lxml"))
        word_count = _count_words(body_text)

        # First paragraph length
        first_para_words = _first_paragraph_length(soup)

        # Sentence/paragraph metrics
        avg_sentence_len = _avg_sentence_length(body_text)
        avg_para_len = _avg_paragraph_length(soup)

        # Link counts
        internal_links, external_links = _count_links(soup, base_domain)

        # Authority links
        has_authority_links = _has_authority_links(soup)

        # Media counts
        image_count = _count_images(soup)
        video_count = _count_videos(soup)
        has_video = video_count > 0

        # Fresh content
        has_fresh_content = _has_fresh_content(html, soup)

        # Title
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Content snippet (first 200 chars of body text)
        content_snippet = body_text[:200] if body_text else ""

        page_result = {
            "url": url,
            "title": title,
            "word_count": word_count,
            "is_thin": word_count < 300,
            "avg_sentence_length": avg_sentence_len,
            "avg_paragraph_length": avg_para_len,
            "first_paragraph_words": first_para_words,
            "internal_links": internal_links,
            "external_links": external_links,
            "has_authority_links": has_authority_links,
            "image_count": image_count,
            "video_count": video_count,
            "has_video": has_video,
            "has_fresh_content": has_fresh_content,
            "content_snippet": content_snippet,
        }
        page_results.append(page_result)

    total = len(page_results)
    if total == 0:
        return {
            "score": 0.0,
            "page_results": [],
            "summary": {
                "avg_word_count": 0,
                "thin_content_pages": 0,
                "pages_with_video": 0,
                "avg_internal_links": 0.0,
                "avg_images_per_page": 0.0,
                "pages_with_fresh_content": 0,
            },
            "thin_content_pages": [],
            "duplicate_content_groups": [],
        }

    avg_word_count = round(sum(r["word_count"] for r in page_results) / total)
    thin_pages = [r for r in page_results if r["is_thin"]]
    pages_with_video = sum(1 for r in page_results if r["has_video"])
    avg_internal_links = round(sum(r["internal_links"] for r in page_results) / total, 1)
    avg_images = round(sum(r["image_count"] for r in page_results) / total, 1)
    fresh_pages = sum(1 for r in page_results if r["has_fresh_content"])

    # Duplicate content detection
    duplicate_groups = _check_duplicate_content(page_results)

    # Score calculation
    score = 100.0
    thin_ratio = len(thin_pages) / total
    score -= thin_ratio * 30  # Penalize thin content heavily
    if avg_word_count < 300:
        score -= 20
    elif avg_word_count < 500:
        score -= 10
    if len(duplicate_groups) > 0:
        score -= min(20, len(duplicate_groups) * 5)
    if avg_images < 1:
        score -= 5
    if fresh_pages == 0:
        score -= 5
    score = round(max(0.0, min(100.0, score)), 1)

    thin_content_list = [
        {"url": r["url"], "word_count": r["word_count"]}
        for r in thin_pages
    ]

    return {
        "score": score,
        "page_results": page_results,
        "summary": {
            "avg_word_count": avg_word_count,
            "thin_content_pages": len(thin_pages),
            "pages_with_video": pages_with_video,
            "avg_internal_links": avg_internal_links,
            "avg_images_per_page": avg_images,
            "pages_with_fresh_content": fresh_pages,
        },
        "thin_content_pages": thin_content_list[:30],
        "duplicate_content_groups": duplicate_groups,
    }
