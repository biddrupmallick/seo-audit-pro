from typing import List, Dict, Any
from bs4 import BeautifulSoup
from crawler.spider import CrawledPage
from config import SLOW_PAGE_THRESHOLD, LARGE_PAGE_THRESHOLD


def count_resources(html: str) -> Dict[str, int]:
    """Count CSS, JS, and image resources in a page."""
    try:
        soup = BeautifulSoup(html, "lxml")
        css_count = len(soup.find_all("link", rel="stylesheet"))
        js_count = len(soup.find_all("script", src=True))
        img_count = len(soup.find_all("img"))
        return {"css": css_count, "js": js_count, "images": img_count, "total": css_count + js_count + img_count}
    except Exception:
        return {"css": 0, "js": 0, "images": 0, "total": 0}


def analyze_performance(pages: List[CrawledPage]) -> Dict[str, Any]:
    """Analyze performance metrics across all pages."""
    valid_pages = [p for p in pages if p.status_code > 0 and not p.error]
    html_pages = [p for p in pages if p.html and 200 <= p.status_code < 300]

    if not valid_pages:
        return {
            "score": 0,
            "total_pages": 0,
            "summary": {
                "avg_response_time": 0,
                "max_response_time": 0,
                "min_response_time": 0,
                "slow_pages": 0,
                "avg_page_size_kb": 0,
                "total_crawled_size_mb": 0,
                "large_pages": 0,
                "avg_images_per_page": 0,
                "resource_heavy_pages": 0,
            },
            "slow_pages": [],
            "large_pages": [],
        }

    response_times = [p.response_time for p in valid_pages if p.response_time > 0]
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0
    max_response_time = max(response_times) if response_times else 0
    min_response_time = min(response_times) if response_times else 0

    slow_pages = []
    for p in valid_pages:
        if p.response_time > SLOW_PAGE_THRESHOLD:
            slow_pages.append({
                "url": p.url,
                "response_time": p.response_time,
                "severity": "critical" if p.response_time > 6 else "warning",
            })

    page_sizes = [p.page_size for p in valid_pages if p.page_size > 0]
    avg_page_size = sum(page_sizes) / len(page_sizes) if page_sizes else 0
    total_crawled_size = sum(page_sizes)

    large_pages = []
    for p in valid_pages:
        if p.page_size > LARGE_PAGE_THRESHOLD:
            large_pages.append({
                "url": p.url,
                "page_size": p.page_size,
                "page_size_kb": round(p.page_size / 1024, 1),
                "severity": "critical" if p.page_size > LARGE_PAGE_THRESHOLD * 2 else "warning",
            })

    # Resource analysis for HTML pages
    resource_heavy_pages = []
    page_resource_data = []
    for p in html_pages:
        resources = count_resources(p.html)
        entry = {
            "url": p.url,
            "resources": resources,
            "response_time": p.response_time,
            "page_size_kb": round(p.page_size / 1024, 1),
        }
        page_resource_data.append(entry)
        if resources["total"] > 50:
            resource_heavy_pages.append(entry)

    total_images = sum(r["resources"]["images"] for r in page_resource_data)
    avg_images_per_page = total_images / len(page_resource_data) if page_resource_data else 0

    # Score calculation
    score = 100.0
    if valid_pages:
        pct_slow = len(slow_pages) / len(valid_pages)
        pct_large = len(large_pages) / len(valid_pages)
        score -= pct_slow * 35
        score -= pct_large * 20
        if avg_response_time > 3:
            score -= 20
        elif avg_response_time > 2:
            score -= 10
        elif avg_response_time > 1:
            score -= 5
        score -= min(15, len(resource_heavy_pages) * 3)
    score = max(0.0, min(100.0, score))

    return {
        "score": round(score, 1),
        "total_pages": len(valid_pages),
        "slow_pages": slow_pages,
        "large_pages": large_pages,
        "resource_heavy_pages": resource_heavy_pages,
        "page_resource_data": page_resource_data,
        "summary": {
            "avg_response_time": round(avg_response_time, 3),
            "max_response_time": round(max_response_time, 3),
            "min_response_time": round(min_response_time, 3),
            "slow_pages": len(slow_pages),
            "avg_page_size_kb": round(avg_page_size / 1024, 1),
            "total_crawled_size_mb": round(total_crawled_size / (1024 * 1024), 2),
            "large_pages": len(large_pages),
            "avg_images_per_page": round(avg_images_per_page, 1),
            "resource_heavy_pages": len(resource_heavy_pages),
        },
    }
