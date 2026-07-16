"""
Scrape a business website for contact email and social media profile URLs.
- Email: fast httpx fetch (emails are usually in static HTML)
- Socials: Chrome headless --dump-dom for fully JS-rendered HTML
"""
import os
import re
import shutil
import subprocess
import tempfile
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

SOCIAL_PLATFORMS = [
    ("facebook.com/",         "facebook"),
    ("instagram.com/",        "instagram"),
    ("twitter.com/",          "twitter"),
    ("x.com/",                "twitter"),
    ("linkedin.com/company/", "linkedin"),
    ("linkedin.com/in/",      "linkedin"),
    ("youtube.com/",          "youtube"),
    ("tiktok.com/",           "tiktok"),
    ("pinterest.com/",        "pinterest"),
    ("yelp.com/biz/",         "yelp"),
]

SOCIAL_EXCLUDE_RE = re.compile(
    r'(sharer|share[/?]|login|signup|intent/tweet|accounts\.google|'
    r'youtube\.com/watch|youtube\.com/embed|pinterest\.com/pin|'
    r'facebook\.com/tr|facebook\.com/dialog|facebook\.com/plugins)',
    re.I,
)

SOCIAL_PLATFORMS_ALL = ["facebook", "instagram", "twitter", "linkedin", "youtube", "tiktok", "pinterest", "yelp"]

# Chrome binary locations
_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]


def _find_chrome() -> Optional[str]:
    for path in _CHROME_PATHS:
        if os.path.exists(path):
            return path
    return shutil.which("google-chrome") or shutil.which("chromium")


_CHROME = _find_chrome()


# ── Email helpers ─────────────────────────────────────────────────────────────

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


def _fetch_httpx(url: str) -> str:
    """Fast static HTML fetch via httpx."""
    try:
        with httpx.Client(headers=HEADERS, verify=False, timeout=10, follow_redirects=True) as client:
            r = client.get(url)
            if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
                return r.text
    except Exception:
        pass
    return ""


# ── Social helpers ────────────────────────────────────────────────────────────

def _fetch_rendered(url: str) -> str:
    """
    Use Chrome --dump-dom to get fully JS-rendered HTML.
    Falls back to httpx if Chrome is unavailable.
    """
    if _CHROME:
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as tmp:
                tmp_path = tmp.name

            result = subprocess.run(
                [
                    _CHROME,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--dump-dom",
                    f"--user-agent={HEADERS['User-Agent']}",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception as e:
            print(f"[website_email] Chrome dump-dom failed for {url}: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # Fallback to httpx
    return _fetch_httpx(url)


def _extract_socials_from_html(html: str, site_domain: str) -> Dict[str, str]:
    """
    Extract social media profile URLs from HTML.
    Catches href attributes, protocol-relative URLs, and URLs in JS strings.
    """
    found: Dict[str, str] = {}

    # Collect all URLs from multiple sources
    candidates = set()

    # 1. href attributes (http and protocol-relative)
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        href = href.strip()
        if href.startswith("//"):
            href = "https:" + href
        if href.startswith("http"):
            candidates.add(href)

    # 2. Any http/https URL anywhere in the HTML (catches JS strings, data attrs, etc.)
    for url in re.findall(r'https?://[^\s"\'<>\\\)]+', html):
        candidates.add(url.rstrip(".,;)>\"'"))

    # 3. Protocol-relative URLs in JS or data attributes
    for url in re.findall(r'["\']\/\/((?:www\.)?(?:facebook|instagram|twitter|x|linkedin|youtube|tiktok|pinterest|yelp)\.com\/[^\s"\'<>]+)', html, re.I):
        candidates.add("https://" + url.rstrip(".,;)>\"'"))

    for href in candidates:
        if SOCIAL_EXCLUDE_RE.search(href):
            continue
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


# ── Main function ─────────────────────────────────────────────────────────────

def scrape_website_contact_info(website_url: str) -> Dict:
    """
    Scrape homepage + contact pages for email and social media links.
    Email uses fast httpx; socials use Chrome headless for JS-rendered content.
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

    # Email — fast httpx pass over homepage + contact pages
    for url in [website_url] + [urljoin(base, p) for p in CONTACT_PATHS]:
        if emails:
            break
        html = _fetch_httpx(url)
        if html:
            for e in _extract_emails_from_html(html, site_domain):
                if e not in seen_emails:
                    seen_emails.add(e)
                    emails.append(e)

    # Socials — Chrome rendered pass over homepage (JS-rendered links)
    rendered_html = _fetch_rendered(website_url)
    if rendered_html:
        socials.update(_extract_socials_from_html(rendered_html, site_domain))

    # If still missing some socials, try contact/about pages too
    if len(socials) < len(SOCIAL_PLATFORMS_ALL):
        for path in ["/contact", "/about"]:
            if len(socials) >= len(SOCIAL_PLATFORMS_ALL):
                break
            html = _fetch_rendered(urljoin(base, path))
            if html:
                for k, v in _extract_socials_from_html(html, site_domain).items():
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
    info = scrape_website_contact_info(website_url)
    return info["email"]


def enrich_businesses_with_website_emails(businesses: list) -> list:
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
