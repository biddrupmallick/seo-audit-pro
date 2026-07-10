import re
import asyncio
from typing import Dict, Any, List, Optional
import httpx
from bs4 import BeautifulSoup
import ollama

OLLAMA_MODEL      = "llama3.1"
AVAILABILITY_API  = "https://archive.org/wayback/available"
WB_BASE           = "https://web.archive.org/web"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


async def _get_snapshot_for_year(client: httpx.AsyncClient, domain: str, year: int) -> Optional[str]:
    """Return the closest snapshot timestamp for a given year using the fast availability API."""
    try:
        r = await client.get(
            AVAILABILITY_API,
            params={"url": domain, "timestamp": str(year)},
        )
        data = r.json()
        snap = data.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available") and snap.get("timestamp"):
            return snap["timestamp"]
    except Exception:
        pass
    return None


async def _get_snapshot_list(domain: str) -> List[str]:
    """Query year-by-year using the fast Availability API (no CDX timeouts)."""
    from datetime import datetime
    current_year = datetime.now().year
    years = list(range(2010, current_year + 1, 2))  # every 2 years
    years.append(current_year)

    async with httpx.AsyncClient(timeout=12, headers=_HEADERS) as client:
        results = await asyncio.gather(
            *[_get_snapshot_for_year(client, domain, y) for y in years],
            return_exceptions=True,
        )

    timestamps = []
    seen = set()
    for ts in results:
        if isinstance(ts, str) and ts and ts not in seen:
            seen.add(ts)
            timestamps.append(ts)

    return sorted(timestamps)


async def _fetch_html(domain: str, timestamp: str) -> Optional[str]:
    url = f"{WB_BASE}/{timestamp}/https://{domain}"
    try:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, headers=_HEADERS
        ) as client:
            r = await client.get(url)
            if r.status_code == 200:
                return r.text
    except Exception:
        pass
    return None


def _parse_snapshot(html: str, timestamp: str, domain: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    # Remove Wayback toolbar noise
    for tag in soup.find_all(id=re.compile(r"wm-ipp|playback", re.I)):
        tag.decompose()
    for tag in soup.find_all("div", class_=re.compile(r"wb-autocomplete|banner", re.I)):
        tag.decompose()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True)[:120] if title_tag else ""

    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")][:3]
    h2s = [h.get_text(strip=True) for h in soup.find_all("h2")][:8]

    meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    meta_desc = (meta.get("content", "") if meta else "")[:200]

    # Navigation items
    nav_items: List[str] = []
    for nav in soup.find_all(["nav", "header"]):
        for a in nav.find_all("a"):
            t = a.get_text(strip=True)
            if t and 2 < len(t) < 40:
                nav_items.append(t)
    nav_items = list(dict.fromkeys(nav_items))[:12]   # dedup, keep order

    # CTA buttons
    cta_texts: List[str] = []
    for el in soup.find_all(
        ["button", "a"],
        class_=re.compile(r"btn|cta|button|call|contact|get|start", re.I),
    ):
        t = el.get_text(strip=True)
        if t and len(t) < 60:
            cta_texts.append(t)
    cta_texts = list(dict.fromkeys(cta_texts))[:5]

    body = soup.find("body")
    word_count = len(body.get_text().split()) if body else 0

    # Internal page links (gives clue about site structure)
    page_links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if domain in href or (href.startswith("/") and not href.startswith("//")):
            if text and 2 < len(text) < 50:
                page_links.append(text)
    page_links = list(dict.fromkeys(page_links))[:15]

    year  = timestamp[:4]
    month = timestamp[4:6]

    return {
        "timestamp": timestamp,
        "date": f"{year}-{month}",
        "year": int(year),
        "title": title,
        "h1s": h1s,
        "h2s": h2s,
        "meta_description": meta_desc,
        "nav_items": nav_items,
        "cta_texts": cta_texts,
        "page_links": page_links,
        "word_count": word_count,
        "wayback_url": f"{WB_BASE}/{timestamp}/https://{domain}",
    }


def _select_timestamps(timestamps: List[str]) -> List[str]:
    """Pick up to 4 evenly-spaced timestamps across the full timeline."""
    if not timestamps:
        return []
    n = len(timestamps)
    if n <= 4:
        return timestamps
    indices = [0, n // 3, (2 * n) // 3, n - 1]
    return [timestamps[i] for i in sorted(set(indices))]


def _compare(snapshots: List[Dict]) -> Dict[str, Any]:
    if len(snapshots) < 2:
        return {}
    first, last = snapshots[0], snapshots[-1]
    years = last["year"] - first["year"]

    added_nav   = [x for x in last["nav_items"]  if x not in first["nav_items"]]
    removed_nav = [x for x in first["nav_items"] if x not in last["nav_items"]]
    added_pages   = [x for x in last["page_links"]  if x not in first["page_links"]]
    removed_pages = [x for x in first["page_links"] if x not in last["page_links"]]

    wc_first, wc_last = first["word_count"], last["word_count"]
    if wc_last > wc_first * 1.3:
        content_trend = "significantly expanded"
    elif wc_last < wc_first * 0.7:
        content_trend = "reduced"
    else:
        content_trend = "stayed roughly the same size"

    return {
        "years_tracked":   years,
        "earliest_date":   first["date"],
        "latest_date":     last["date"],
        "old_title":       first["title"],
        "new_title":       last["title"],
        "title_changed":   first["title"] != last["title"],
        "added_nav":       added_nav[:6],
        "removed_nav":     removed_nav[:6],
        "added_pages":     added_pages[:8],
        "removed_pages":   removed_pages[:8],
        "content_trend":   content_trend,
        "old_word_count":  wc_first,
        "new_word_count":  wc_last,
    }


def _ai_insights(domain: str, snapshots: List[Dict], diff: Dict) -> Dict[str, str]:
    if not snapshots:
        return {}
    first, last = snapshots[0], snapshots[-1]

    prompt = f"""You are analysing the Wayback Machine history of {domain} to help a consultant understand the client.

EARLIEST SNAPSHOT ({first['date']}):
Title: {first['title']}
H1s: {', '.join(first['h1s'])}
Navigation: {', '.join(first['nav_items'][:6])}
Headings: {', '.join(first['h2s'][:4])}

LATEST SNAPSHOT ({last['date']}):
Title: {last['title']}
H1s: {', '.join(last['h1s'])}
Navigation: {', '.join(last['nav_items'][:6])}
Headings: {', '.join(last['h2s'][:4])}

CHANGES DETECTED:
Added to nav: {', '.join(diff.get('added_nav', [])) or 'none'}
Removed from nav: {', '.join(diff.get('removed_nav', [])) or 'none'}
Content {diff.get('content_trend', 'unchanged')}.

Output EXACTLY this format (4 lines):
SUMMARY: [What this business does and how it has evolved in 1-2 sentences]
PIVOT: [What service or direction they moved away from, or "No clear pivot detected"]
OPPORTUNITY: [One specific SEO or content opportunity based on their history]
TALKING_POINT: [One insightful observation to open a sales conversation with this client]"""

    try:
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"num_predict": 220, "temperature": 0.5},
        )
        text = resp["message"]["content"].strip()
    except Exception:
        return {}

    result: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        for key in ("SUMMARY", "PIVOT", "OPPORTUNITY", "TALKING_POINT"):
            if line.startswith(f"{key}:"):
                result[key.lower()] = line[len(key) + 1:].strip()
    return result


async def analyze_wayback(domain: str) -> Dict[str, Any]:
    """
    Fetch historical snapshots from the Wayback Machine and extract business insights.
    Returns empty dict gracefully if the domain has no archived history.
    """
    # Clean domain
    domain = domain.replace("https://", "").replace("http://", "").rstrip("/")

    timestamps = await _get_snapshot_list(domain)
    if not timestamps:
        return {"available": False, "reason": "No Wayback Machine snapshots found for this domain."}

    selected = _select_timestamps(timestamps)
    total_found = len(timestamps)

    # Fetch all snapshots concurrently
    htmls = await asyncio.gather(*[_fetch_html(domain, ts) for ts in selected])

    snapshots: List[Dict] = []
    for ts, html in zip(selected, htmls):
        if html:
            snapshots.append(_parse_snapshot(html, ts, domain))

    if not snapshots:
        return {"available": False, "reason": "Snapshots found but could not be fetched."}

    diff     = _compare(snapshots)
    insights = _ai_insights(domain, snapshots, diff)

    return {
        "available":  True,
        "total_snapshots_found": total_found,
        "snapshots_analysed":    len(snapshots),
        "snapshots":  snapshots,
        "comparison": diff,
        "insights":   insights,
    }
