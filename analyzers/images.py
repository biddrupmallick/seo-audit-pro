import asyncio
from typing import List, Dict, Any
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import httpx
from crawler.spider import CrawledPage
from config import USER_AGENT, REQUEST_TIMEOUT, LARGE_IMAGE_THRESHOLD


def extract_images(html: str, base_url: str) -> List[Dict[str, str]]:
    """Extract all images from a page."""
    try:
        soup = BeautifulSoup(html, "lxml")
        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "").strip()
            alt = img.get("alt", None)
            width = img.get("width", "")
            height = img.get("height", "")

            if not src:
                continue

            # Resolve relative URLs
            if not src.startswith(("http://", "https://", "data:")):
                src = urljoin(base_url, src)

            images.append({
                "src": src,
                "alt": alt,
                "width": width,
                "height": height,
                "page_url": base_url,
            })
        return images
    except Exception:
        return []


def analyze_images(pages: List[CrawledPage]) -> Dict[str, Any]:
    """Analyze image issues across all pages (synchronously)."""
    html_pages = [p for p in pages if p.html and 200 <= p.status_code < 300]

    all_images = []
    for page in html_pages:
        imgs = extract_images(page.html, page.url)
        all_images.extend(imgs)

    # Missing alt text (alt attribute completely absent)
    missing_alt = [img for img in all_images if img["alt"] is None]

    # Empty alt text (alt="" which may be intentional for decorative images)
    empty_alt = [img for img in all_images if img["alt"] is not None and img["alt"].strip() == ""]

    # External vs internal images
    internal_images = []
    external_images = []
    if html_pages:
        base_domain = urlparse(html_pages[0].url).netloc
        for img in all_images:
            parsed = urlparse(img["src"])
            if parsed.netloc and parsed.netloc != base_domain:
                external_images.append(img)
            elif not img["src"].startswith("data:"):
                internal_images.append(img)

    # Images without dimensions (potential layout shift)
    no_dimensions = [
        img for img in all_images
        if not img["width"] and not img["height"] and not img["src"].startswith("data:")
    ]

    # Data URIs (inline images - usually bad for performance)
    data_uri_images = [img for img in all_images if img["src"].startswith("data:")]

    # Per-page image stats
    page_image_stats = []
    for page in html_pages:
        imgs = extract_images(page.html, page.url)
        page_missing_alt = [i for i in imgs if i["alt"] is None]
        page_empty_alt = [i for i in imgs if i["alt"] is not None and i["alt"].strip() == ""]
        page_image_stats.append({
            "url": page.url,
            "total_images": len(imgs),
            "missing_alt": len(page_missing_alt),
            "empty_alt": len(page_empty_alt),
            "images_with_issues": len(page_missing_alt) + len(page_empty_alt),
        })

    total = len(all_images)
    score = 100.0
    if total > 0:
        pct_missing_alt = len(missing_alt) / total
        pct_no_dim = len(no_dimensions) / total
        score -= pct_missing_alt * 50
        score -= (len(empty_alt) / total) * 15
        score -= pct_no_dim * 15
        score -= min(20, len(data_uri_images) * 2)
    score = max(0.0, min(100.0, score))

    pages_with_issues = [s for s in page_image_stats if s["images_with_issues"] > 0]

    return {
        "score": round(score, 1),
        "total_images": total,
        "missing_alt_images": missing_alt[:100],  # Limit to avoid huge payloads
        "empty_alt_images": empty_alt[:50],
        "no_dimensions_images": no_dimensions[:50],
        "data_uri_images_count": len(data_uri_images),
        "external_images_count": len(external_images),
        "page_image_stats": page_image_stats,
        "pages_with_issues": pages_with_issues,
        "summary": {
            "total_images": total,
            "missing_alt": len(missing_alt),
            "empty_alt": len(empty_alt),
            "no_dimensions": len(no_dimensions),
            "data_uri_images": len(data_uri_images),
            "external_images": len(external_images),
            "pages_with_image_issues": len(pages_with_issues),
        },
    }
