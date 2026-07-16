"""
Scrape a business website for contact email and social media profile URLs.
Checks homepage + common contact pages. Fast — regex only, no AI.
"""
import re
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

import httpx

CONTACT_PATHS = ["/contact", "/contact-us", "/about", "/about-us", "/reach-us", "/get-in-touch"]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-z]{2,}(?=[\s,;\"'\)<>\]|]|$)")

IGNORE_DOMAINS = {
    "example.com", "sentry.io", "wixpress.com", "squarespace.com",
    "wordpress.com", "shopify.com", "gmail.com", "yahoo.com",
    "hotmail.com", "outlook.com", "noreply", "no-reply",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOAuditBot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}

# Social media platforms — pattern → column name
# Order matters: more specific patterns first
SOCIAL_PLATFORMS = [
    ("facebook.com/",          "facebook"),
    ("instagram.com/",         "instagram"),
    ("twitter.com/",           "twitter"),
    ("x.com/",                 "twitter"),   # X = Twitter, same column
    ("linkedin.com/company/",  "linkedin"),
    ("linkedin.com/in/",       "linkedin"),
    ("youtube.com/",           "youtube"),
    ("tiktok.com/",            "tiktok"),
    ("pinterest.com/",         "pinterest"),
    ("yelp.com/biz/",          "yelp"),
]

# URL fragments to exclude (share buttons, login pages, etc.)
SOCIAL_EXCLUDE_RE = re.compile(
    r'(sharer|share\?|login|signup|intent/tweet|accounts\.google|'
    r'youtube\.com/watch|youtube\.com/embed|pinterest\.com/pin)',
    re.I,
)

SOCIAL_PLATFORMS_ALL = ["facebook", "instagram", "twitter", "linkedin", "youtube", "tiktok", "pinterest", "yelp"]


def _is_valid_email(email: str, site_domain: str) -> bool:
    local, _, domain = email.partition("@")
    if any(ig in domain.lower() or ig in local.lower() for ig in IGNORE_DOMAINS):
        return False
    return True


def _extract_emails_from_html(html: str, site_domain: str) -> List[str]:
    mailto_emails = re.findall(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html)
    all_emails = EMAIL_RE.findall(html)
    seen = set()
    result = []
    for email in (mailto_emails + all_emails):
        email = email.lower().strip(".,;")
        if email not in seen and _is_valid_email(email, site_domain):
            seen.add(email)
            result.append(email)
    return result


def _extract_socials_from_html(html: str, site_domain: str) -> Dict[str, str]:
    """Extract social media profile URLs from HTML. Returns {platform: url}."""
    found: Dict[str, str] = {}

    # Find all href values
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)

    for href in hrefs:
        href = href.strip()
        if not href.startswith("http"):
            continue
        if SOCIAL_EXCLUDE_RE.search(href):
            continue
        # Don't pick up links back to the same domain
        try:
            link_domain = urlparse(href).netloc.lower().replace("www.", "")
            if link_domain == site_domain:
                continue
        except Exception:
            continue

        for pattern, platform in SOCIAL_PLATFORMS:
            if platform in found:
                continue
            if pattern in href.lower():
                found[platform] = href
                break

    return found


def _fetch(client: httpx.Client, url: str) -> str:
    try:
        r = client.get(url, timeout=8, follow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return r.text
    except Exception:
        pass
    return ""


def scrape_website_contact_info(website_url: str) -> Dict:
    """
    Fetch homepage + contact pages.
    Returns {email, facebook, instagram, twitter, linkedin, youtube, tiktok, pinterest, yelp}
    """
    empty = {"email": "", **{p: "" for p in SOCIAL_PLATFORMS_ALL}}

    try:
        parsed = urlparse(website_url)
        site_domain = parsed.netloc.lower().replace("www.", "")
        base = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return empty

    emails: List[str] = []
    socials: Dict[str, str] = {}
    seen_emails: set = set()

    with httpx.Client(headers=HEADERS, verify=False) as client:
        # Always scrape homepage
        html = _fetch(client, website_url)
        if html:
            for e in _extract_emails_from_html(html, site_domain):
                if e not in seen_emails:
                    seen_emails.add(e)
                    emails.append(e)
            socials.update(_extract_socials_from_html(html, site_domain))

        # Contact/about pages — stop email search once found, but keep going for socials
        for path in CONTACT_PATHS:
            if emails and len(socials) >= len(SOCIAL_PLATFORMS_ALL):
                break
            url = urljoin(base, path)
            html = _fetch(client, url)
            if html:
                if not emails:
                    for e in _extract_emails_from_html(html, site_domain):
                        if e not in seen_emails:
                            seen_emails.add(e)
                            emails.append(e)
                new_socials = _extract_socials_from_html(html, site_domain)
                for k, v in new_socials.items():
                    if k not in socials:
                        socials[k] = v

    return {
        "email":     emails[0] if emails else "",
        "facebook":  socials.get("facebook",  ""),
        "instagram": socials.get("instagram", ""),
        "twitter":   socials.get("twitter",   ""),
        "linkedin":  socials.get("linkedin",  ""),
        "youtube":   socials.get("youtube",   ""),
        "tiktok":    socials.get("tiktok",    ""),
        "pinterest": socials.get("pinterest", ""),
        "yelp":      socials.get("yelp",      ""),
    }


def get_best_contact_email(website_url: str) -> str:
    """Return the single best contact email found on the website, or empty string."""
    info = scrape_website_contact_info(website_url)
    return info["email"]


def enrich_businesses_with_website_emails(businesses: list) -> list:
    """Add website_email field to each business dict by scraping their website."""
    for biz in businesses:
        website = (biz.get("website") or "").strip()
        if not website:
            biz["website_email"] = ""
            continue
        if not website.startswith(("http://", "https://")):
            website = "https://" + website
        try:
            biz["website_email"] = get_best_contact_email(website)
        except Exception:
            biz["website_email"] = ""
    return businesses
