from typing import List, Dict, Any
from urllib.parse import urlparse
from crawler.spider import CrawledPage
from config import SLOW_PAGE_THRESHOLD, REDIRECT_CHAIN_THRESHOLD


def analyze_technical(pages: List[CrawledPage]) -> Dict[str, Any]:
    """Analyze technical SEO issues."""
    issues_4xx = []
    issues_5xx = []
    redirect_chains = []
    http_pages = []
    slow_pages = []
    error_pages = []

    for page in pages:
        url = page.url

        # 4xx errors
        if 400 <= page.status_code < 500:
            issues_4xx.append({
                "url": url,
                "status_code": page.status_code,
                "final_url": page.final_url,
            })

        # 5xx errors
        elif 500 <= page.status_code < 600:
            issues_5xx.append({
                "url": url,
                "status_code": page.status_code,
            })

        # Connection errors
        elif page.status_code == 0 and page.error:
            error_pages.append({
                "url": url,
                "error": page.error,
            })

        # Long redirect chains
        if len(page.redirect_chain) >= REDIRECT_CHAIN_THRESHOLD:
            redirect_chains.append({
                "url": url,
                "chain_length": len(page.redirect_chain),
                "chain": page.redirect_chain + [page.final_url or url],
            })

        # HTTP (non-SSL) pages
        parsed = urlparse(url)
        if parsed.scheme == "http":
            http_pages.append({"url": url})

        # Slow pages
        if page.response_time > SLOW_PAGE_THRESHOLD and page.status_code > 0:
            slow_pages.append({
                "url": url,
                "response_time": page.response_time,
            })

    total_pages = len(pages)
    crawled_ok = sum(1 for p in pages if 200 <= p.status_code < 300)

    # Calculate score (100 = perfect, deductions for issues)
    score = 100.0
    if total_pages > 0:
        score -= (len(issues_4xx) / total_pages) * 30
        score -= (len(issues_5xx) / total_pages) * 20
        score -= (len(redirect_chains) / total_pages) * 10
        score -= (len(http_pages) / total_pages) * 15
        score -= (len(slow_pages) / total_pages) * 15
        score -= (len(error_pages) / total_pages) * 10
    score = max(0.0, min(100.0, score))

    return {
        "score": round(score, 1),
        "total_pages": total_pages,
        "crawled_ok": crawled_ok,
        "issues_4xx": issues_4xx,
        "issues_5xx": issues_5xx,
        "redirect_chains": redirect_chains,
        "http_pages": http_pages,
        "slow_pages": slow_pages,
        "error_pages": error_pages,
        "summary": {
            "broken_pages": len(issues_4xx),
            "server_errors": len(issues_5xx),
            "long_redirect_chains": len(redirect_chains),
            "http_only_pages": len(http_pages),
            "slow_pages": len(slow_pages),
            "connection_errors": len(error_pages),
        },
    }
