"""
Find pages with missing/weak meta descriptions and rewrite with Ollama.
"""
from typing import List, Dict, Any

from bs4 import BeautifulSoup
from crawler.spider import CrawledPage
from analyzers.ollama_client import ask


def _ollama(prompt: str, max_tokens: int = 100) -> str:
    return ask(prompt, max_tokens=max_tokens, temperature=0.5)


def _parse_page(html: str) -> Dict[str, str]:
    try:
        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("title")
        h1_tag = soup.find("h1")
        meta_tag = soup.find("meta", attrs={"name": "description"})
        return {
            "title": title_tag.get_text(strip=True) if title_tag else "",
            "h1": h1_tag.get_text(strip=True) if h1_tag else "",
            "meta": (meta_tag.get("content") or "").strip() if meta_tag else "",
        }
    except Exception:
        return {"title": "", "h1": "", "meta": ""}


def generate_meta_rewrites(pages: List[CrawledPage], domain: str, max_rewrites: int = 3) -> Dict[str, Any]:
    """Rewrite top pages with missing or weak meta descriptions."""
    html_pages = [p for p in pages if p.html and 200 <= p.status_code < 300]

    candidates = []
    for page in html_pages:
        info = _parse_page(page.html)
        meta = info["meta"]
        if not meta or len(meta) < 50:
            candidates.append({
                "url": page.url,
                "current_meta": meta,
                "title": info["title"],
                "h1": info["h1"],
                "issue": "missing" if not meta else "too short",
            })

    if not candidates:
        return {"available": False, "rewrites": [], "missing_count": 0}

    # Homepage first
    base = f"https://{domain}"
    candidates.sort(key=lambda x: 0 if x["url"].rstrip("/") in (base, base.replace("https://", "http://")) else 1)

    rewrites = []
    for c in candidates[:max_rewrites]:
        new_meta = _ollama(
            f"""Write a compelling meta description for this webpage.

URL: {c['url']}
Title: {c['title'] or 'Not set'}
H1: {c['h1'] or 'Not set'}

Rules:
- 140-155 characters
- Clear benefit + call to action
- No keyword stuffing
- Output ONLY the meta description, no quotes, no explanation.""",
            max_tokens=80,
        ).strip("\"' ")
        if len(new_meta) > 160:
            new_meta = new_meta[:157] + "..."
        rewrites.append({
            "url": c["url"],
            "issue": c["issue"],
            "before": c["current_meta"] or "(none)",
            "after": new_meta,
            "title": c["title"],
        })

    return {
        "available": True,
        "missing_count": len(candidates),
        "rewrites": rewrites,
    }
