"""
Google Business Profile Audit
Scrapes GBP pages using Chrome headless (no API key required).
User provides the Google Maps URL for client + competitors.
"""
import re
import subprocess
import shutil
import json
from typing import Dict, Any, List, Optional

from bs4 import BeautifulSoup

CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]

def _find_chrome() -> Optional[str]:
    for p in CHROME_PATHS:
        import os
        if os.path.exists(p):
            return p
    return shutil.which("google-chrome") or shutil.which("chromium")

CHROME_BIN = _find_chrome()


def _fetch_dom(url: str) -> str:
    """Use Chrome headless to get the fully-rendered DOM of a Google Maps page."""
    if not CHROME_BIN:
        return ""
    try:
        result = subprocess.run(
            [
                CHROME_BIN,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--dump-dom",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception as e:
        print(f"[GBP] Chrome fetch failed for {url}: {e}")
        return ""


def _extract_rating(text: str) -> Optional[float]:
    m = re.search(r"\b([1-4]\.\d|5\.0|[1-5])\s*(?:stars?|★)", text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m = re.search(r'"ratingValue"\s*:\s*"?([0-9.]+)"?', text)
    if m:
        return float(m.group(1))
    return None


def _extract_review_count(text: str) -> Optional[int]:
    for pat in [
        r'"reviewCount"\s*:\s*"?(\d+)"?',
        r'([\d,]+)\s+(?:Google\s+)?reviews?',
        r'([\d,]+)\s+review',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def _parse_gbp(html: str, url: str) -> Dict[str, Any]:
    """Parse rendered GBP HTML into structured data."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Business name — look for og:title or h1 or JSON-LD
    name = ""
    og = soup.find("meta", property="og:title")
    if og:
        name = og.get("content", "").split("·")[0].strip()
    if not name:
        h1 = soup.find("h1")
        if h1:
            name = h1.get_text(strip=True)
    if not name:
        m = re.search(r'"name"\s*:\s*"([^"]{3,80})"', html)
        if m:
            name = m.group(1)

    # Rating
    rating = _extract_rating(text)
    if rating is None:
        rating = _extract_rating(html)

    # Review count
    review_count = _extract_review_count(text)
    if review_count is None:
        review_count = _extract_review_count(html)

    # Category — usually after the name in GBP
    category = ""
    m = re.search(r'"category"\s*:\s*"([^"]{3,80})"', html)
    if m:
        category = m.group(1)
    if not category:
        m = re.search(r'itemtype="https?://schema\.org/(\w+)"', html)
        if m:
            category = m.group(1)

    # Address
    address = ""
    addr_tag = soup.find("span", {"itemprop": "streetAddress"})
    if addr_tag:
        address = addr_tag.get_text(strip=True)
    if not address:
        m = re.search(r'"streetAddress"\s*:\s*"([^"]+)"', html)
        if m:
            address = m.group(1)
    if not address:
        # Try to find address pattern in text
        m = re.search(r'\d+\s+[A-Z][a-zA-Z\s]+(?:St|Ave|Rd|Blvd|Dr|Ln|Way|Ct|Pl)\b', text)
        if m:
            address = m.group(0)

    # Phone
    phone = ""
    phone_tag = soup.find("span", {"itemprop": "telephone"})
    if phone_tag:
        phone = phone_tag.get_text(strip=True)
    if not phone:
        m = re.search(r'"telephone"\s*:\s*"([^"]+)"', html)
        if m:
            phone = m.group(1)
    if not phone:
        m = re.search(r'(?:\+?[\d\s\-().]{10,20})', text)
        if m:
            phone = m.group(0).strip()

    # Website
    website = ""
    m = re.search(r'"url"\s*:\s*"(https?://(?!(?:www\.)?google)[^"]+)"', html)
    if m:
        website = m.group(1)

    # Hours — check for presence
    has_hours = bool(
        re.search(r'(Open|Closed|opens|closes|Monday|Tuesday|hours)', text, re.IGNORECASE)
        and re.search(r'\d{1,2}:\d{2}\s*(?:AM|PM)', text, re.IGNORECASE)
    )

    # Photos — look for photo count indicator
    has_photos = bool(re.search(r'photo|image|picture', text, re.IGNORECASE))
    photo_count = 0
    m = re.search(r'([\d,]+)\s+(?:photos?|images?)', text, re.IGNORECASE)
    if m:
        photo_count = int(m.group(1).replace(",", ""))

    # Description / About
    has_description = bool(re.search(r'"description"\s*:\s*"[^"]{20,}"', html))

    # Posts / Updates
    has_posts = bool(re.search(r'(?:post|update|news|offer|event)\b', text[:5000], re.IGNORECASE))

    # Q&A
    has_qa = bool(re.search(r'Q&A|question.*answer|ask.*question', text, re.IGNORECASE))

    # Services
    has_services = bool(re.search(r'services?\s*(?:offered|provided|listed)', text, re.IGNORECASE)
                       or re.search(r'"hasOfferCatalog"', html))

    return {
        "url": url,
        "name": name,
        "category": category,
        "rating": rating,
        "review_count": review_count,
        "address": address,
        "phone": phone,
        "website": website,
        "has_hours": has_hours,
        "has_photos": has_photos,
        "photo_count": photo_count,
        "has_description": has_description,
        "has_posts": has_posts,
        "has_qa": has_qa,
        "has_services": has_services,
        "raw_text_len": len(text),
    }


def _score_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Score a GBP profile out of 100 and list issues."""
    score = 0
    issues = []
    wins = []

    # Rating (25 pts)
    r = profile.get("rating")
    if r is None:
        issues.append({"severity": "high", "text": "No rating found — profile may be unclaimed or new"})
    elif r >= 4.5:
        score += 25
        wins.append(f"Excellent rating: {r}★")
    elif r >= 4.0:
        score += 18
        wins.append(f"Good rating: {r}★")
    elif r >= 3.5:
        score += 10
        issues.append({"severity": "medium", "text": f"Rating {r}★ is below 4.0 — actively seek more positive reviews"})
    else:
        score += 0
        issues.append({"severity": "high", "text": f"Low rating {r}★ — urgently address negative reviews"})

    # Review count (20 pts)
    rc = profile.get("review_count") or 0
    if rc >= 200:
        score += 20
        wins.append(f"Strong review volume: {rc} reviews")
    elif rc >= 50:
        score += 14
        wins.append(f"Decent review count: {rc} reviews")
    elif rc >= 10:
        score += 7
        issues.append({"severity": "medium", "text": f"Only {rc} reviews — aim for 50+ to build trust"})
    else:
        issues.append({"severity": "high", "text": f"Very few reviews ({rc}) — start a review generation campaign"})

    # Address (10 pts)
    if profile.get("address"):
        score += 10
        wins.append("Address listed")
    else:
        issues.append({"severity": "high", "text": "No address detected — verify NAP information is complete"})

    # Phone (10 pts)
    if profile.get("phone"):
        score += 10
        wins.append("Phone number listed")
    else:
        issues.append({"severity": "high", "text": "Phone number missing — customers can't call you"})

    # Website link (10 pts)
    if profile.get("website"):
        score += 10
        wins.append("Website linked")
    else:
        issues.append({"severity": "medium", "text": "No website link — add your website URL to drive traffic"})

    # Hours (10 pts)
    if profile.get("has_hours"):
        score += 10
        wins.append("Business hours listed")
    else:
        issues.append({"severity": "medium", "text": "Hours not found — add opening hours to reduce customer friction"})

    # Photos (5 pts)
    if profile.get("photo_count", 0) >= 20:
        score += 5
        wins.append(f"{profile['photo_count']} photos uploaded")
    elif profile.get("has_photos"):
        score += 3
        issues.append({"severity": "low", "text": "Add more photos — listings with 20+ photos get 35% more clicks"})
    else:
        issues.append({"severity": "medium", "text": "No photos detected — photos drive 42% more direction requests"})

    # Description (5 pts)
    if profile.get("has_description"):
        score += 5
        wins.append("Business description present")
    else:
        issues.append({"severity": "low", "text": "No business description — add a keyword-rich description (750 chars)"})

    # Posts (3 pts)
    if profile.get("has_posts"):
        score += 3
        wins.append("Active posts/updates detected")
    else:
        issues.append({"severity": "low", "text": "No posts found — post weekly offers/news to boost visibility"})

    # Q&A (2 pts)
    if profile.get("has_qa"):
        score += 2
        wins.append("Q&A section active")
    else:
        issues.append({"severity": "low", "text": "Seed your Q&A section with common customer questions"})

    return {
        **profile,
        "score": min(score, 100),
        "issues": issues,
        "wins": wins,
    }


def _compare_profiles(client: Dict, competitors: List[Dict]) -> Dict[str, Any]:
    """Build a side-by-side comparison table."""
    fields = [
        ("Rating", "rating", lambda v: f"{v}★" if v else "—"),
        ("Reviews", "review_count", lambda v: str(v) if v else "0"),
        ("Has Hours", "has_hours", lambda v: "✓" if v else "✗"),
        ("Has Photos", "has_photos", lambda v: "✓" if v else "✗"),
        ("Photo Count", "photo_count", lambda v: str(v) if v else "0"),
        ("Website Linked", "website", lambda v: "✓" if v else "✗"),
        ("Has Phone", "phone", lambda v: "✓" if v else "✗"),
        ("Has Description", "has_description", lambda v: "✓" if v else "✗"),
        ("Has Posts", "has_posts", lambda v: "✓" if v else "✗"),
        ("Profile Score", "score", lambda v: f"{v}/100"),
    ]

    rows = []
    for label, key, fmt in fields:
        client_val = client.get(key)
        comp_vals = [c.get(key) for c in competitors]
        rows.append({
            "label": label,
            "client": fmt(client_val),
            "competitors": [fmt(v) for v in comp_vals],
            "raw_client": client_val,
            "raw_competitors": comp_vals,
        })
    return {"rows": rows, "competitor_names": [c.get("name", c.get("url", "Competitor")) for c in competitors]}


def analyze_gbp(
    client_gbp_url: str,
    competitor_gbp_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Main entry point — scrape and audit GBP profiles."""
    if not CHROME_BIN:
        return {"available": False, "error": "Chrome not found — needed for GBP scraping"}

    # Fetch + parse client profile
    client_html = _fetch_dom(client_gbp_url)
    if not client_html:
        return {"available": False, "error": "Could not fetch client GBP page"}

    client_raw = _parse_gbp(client_html, client_gbp_url)
    client = _score_profile(client_raw)

    # Fetch + parse competitor profiles
    competitors = []
    for url in (competitor_gbp_urls or [])[:5]:
        html = _fetch_dom(url)
        if html:
            comp_raw = _parse_gbp(html, url)
            competitors.append(_score_profile(comp_raw))

    comparison = _compare_profiles(client, competitors) if competitors else {}

    return {
        "available": True,
        "client": client,
        "competitors": competitors,
        "comparison": comparison,
    }
