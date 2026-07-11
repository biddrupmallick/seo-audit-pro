"""
Audit trust signals from crawled pages.
"""
import re
from typing import List, Dict, Any

from bs4 import BeautifulSoup
from crawler.spider import CrawledPage

TRUST_BADGE_RE = re.compile(
    r"bbb\.org|trustpilot|ssl.*secure|norton.*secure|mcafee.*secure|verified.*business|google.*partner",
    re.I,
)
CHAT_RE = re.compile(
    r"intercom|drift\.com|tawk\.to|livechat|freshchat|zendesk|crisp\.chat|tidio",
    re.I,
)
TESTIMONIAL_RE = re.compile(
    r"testimonial|what.*customers.*say|what.*clients.*say|customer.*review|client.*review|success.*stor|case.*stud",
    re.I,
)
AWARD_RE = re.compile(
    r"\baward\b|\bcertif|\baccredit|\brecogni|featured in|as seen|winner|best of",
    re.I,
)
SOCIAL_PATTERNS = {
    "Facebook": r"facebook\.com/",
    "Instagram": r"instagram\.com/",
    "Twitter/X": r"twitter\.com/|x\.com/",
    "LinkedIn": r"linkedin\.com/",
    "YouTube": r"youtube\.com/",
    "TikTok": r"tiktok\.com/",
}

SCORE_MAP = {
    "ssl": 15,
    "privacy_policy": 10,
    "contact_page": 10,
    "about_page": 8,
    "testimonials": 12,
    "trust_badges": 8,
    "live_chat": 7,
    "awards_certs": 8,
    "has_social": 7,
    "faq": 8,
    "blog": 7,
}

LABELS = {
    "ssl": "SSL Certificate (HTTPS)",
    "privacy_policy": "Privacy Policy Page",
    "terms_of_service": "Terms of Service",
    "contact_page": "Contact Page",
    "about_page": "About Page",
    "testimonials": "Testimonials / Reviews Section",
    "awards_certs": "Awards & Certifications",
    "live_chat": "Live Chat Widget",
    "trust_badges": "Trust Badges (BBB, SSL seal, etc.)",
    "has_social": "Social Media Links",
    "faq": "FAQ Page",
    "blog": "Blog / Resources",
}


def analyze_trust_signals(pages: List[CrawledPage], domain: str) -> Dict[str, Any]:
    html_pages = [p for p in pages if p.html and 200 <= p.status_code < 300]
    if not html_pages:
        return {"score": 0, "present": [], "missing": list(LABELS.values()), "signals": {}, "social_media": {}}

    all_html = " ".join(p.html for p in html_pages[:10])
    all_html_lower = all_html.lower()
    all_text = ""
    urls = [p.url.lower() for p in pages]

    for page in html_pages[:10]:
        try:
            soup = BeautifulSoup(page.html, "lxml")
            all_text += " " + soup.get_text(" ", strip=True).lower()
        except Exception:
            pass

    sig: Dict[str, Any] = {}
    sig["ssl"] = any(p.url.startswith("https://") for p in html_pages[:5])
    sig["privacy_policy"] = (
        any("/privacy" in u for u in urls)
        or "privacy policy" in all_text
    )
    sig["terms_of_service"] = (
        any("/terms" in u or "/tos" in u for u in urls)
        or "terms of service" in all_text
        or "terms and conditions" in all_text
    )
    sig["contact_page"] = any("/contact" in u for u in urls)
    sig["about_page"] = any("/about" in u for u in urls)
    sig["testimonials"] = bool(TESTIMONIAL_RE.search(all_text))
    sig["awards_certs"] = bool(AWARD_RE.search(all_text))
    sig["live_chat"] = bool(CHAT_RE.search(all_html_lower))
    sig["trust_badges"] = bool(TRUST_BADGE_RE.search(all_html_lower))
    sig["faq"] = any("/faq" in u for u in urls) or "frequently asked" in all_text
    sig["blog"] = any("/blog" in u or "/news" in u or "/resources" in u for u in urls)

    social: Dict[str, bool] = {}
    for platform, pattern in SOCIAL_PATTERNS.items():
        social[platform] = bool(re.search(pattern, all_html_lower))
    sig["social_media"] = social
    sig["has_social"] = any(social.values())

    score = min(100, sum(v for k, v in SCORE_MAP.items() if sig.get(k)))
    present = [LABELS[k] for k in LABELS if sig.get(k)]
    missing = [LABELS[k] for k in LABELS if not sig.get(k)]

    return {
        "score": score,
        "signals": sig,
        "social_media": social,
        "present": present,
        "missing": missing,
        "summary": {"score": score, "present_count": len(present), "missing_count": len(missing)},
    }
