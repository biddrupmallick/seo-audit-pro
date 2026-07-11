"""
Scrape a business website for contact email addresses.
Checks homepage + common contact pages. Fast — regex only, no AI.
"""
import re
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx

CONTACT_PATHS = ["/contact", "/contact-us", "/about", "/about-us", "/reach-us", "/get-in-touch"]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-z]{2,}(?=[\s,;\"'\)<>\]|]|$)")

# Domains to ignore (generic/noreply addresses)
IGNORE_DOMAINS = {
    "example.com", "sentry.io", "wixpress.com", "squarespace.com",
    "wordpress.com", "shopify.com", "gmail.com", "yahoo.com",
    "hotmail.com", "outlook.com", "noreply", "no-reply",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOAuditBot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}


def _is_valid_email(email: str, site_domain: str) -> bool:
    local, _, domain = email.partition("@")
    if any(ig in domain.lower() or ig in local.lower() for ig in IGNORE_DOMAINS):
        return False
    if local.lower() in ("info", "noreply", "no-reply", "admin", "webmaster", "support", "hello", "contact"):
        # Generic but still usable — allow them (user can filter)
        pass
    return True


def _extract_emails_from_html(html: str, site_domain: str) -> List[str]:
    # Prefer mailto: links first (most reliable)
    mailto_emails = re.findall(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html)
    # Also scan plain text
    all_emails = EMAIL_RE.findall(html)

    seen = set()
    result = []
    for email in (mailto_emails + all_emails):
        email = email.lower().strip(".,;")
        if email not in seen and _is_valid_email(email, site_domain):
            seen.add(email)
            result.append(email)
    return result


def _fetch(client: httpx.Client, url: str) -> str:
    try:
        r = client.get(url, timeout=8, follow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return r.text
    except Exception:
        pass
    return ""


def scrape_website_emails(website_url: str) -> List[str]:
    """
    Fetch homepage + contact pages and return all found email addresses.
    First email is the best candidate (usually in mailto: link near the top).
    """
    try:
        parsed = urlparse(website_url)
        site_domain = parsed.netloc.lower().replace("www.", "")
        base = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return []

    emails: List[str] = []
    seen: set = set()

    with httpx.Client(headers=HEADERS, verify=False) as client:
        # Homepage first
        html = _fetch(client, website_url)
        if html:
            for e in _extract_emails_from_html(html, site_domain):
                if e not in seen:
                    seen.add(e)
                    emails.append(e)

        # Contact pages — stop once we have a direct email
        for path in CONTACT_PATHS:
            if emails:
                break
            url = urljoin(base, path)
            html = _fetch(client, url)
            if html:
                for e in _extract_emails_from_html(html, site_domain):
                    if e not in seen:
                        seen.add(e)
                        emails.append(e)

    return emails


def get_best_contact_email(website_url: str) -> str:
    """Return the single best contact email found on the website, or empty string."""
    emails = scrape_website_emails(website_url)
    return emails[0] if emails else ""


def enrich_businesses_with_website_emails(businesses: list) -> list:
    """
    Add website_email field to each business dict by scraping their website.
    Skips businesses that already have an owner_email.
    """
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
