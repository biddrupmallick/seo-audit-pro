import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from crawler.spider import CrawledPage

# CTA keyword patterns for button/link text
CTA_KEYWORDS = re.compile(
    r"\b(get\s+started|contact\s+us|buy\s+now|sign\s+up|book\s+now|schedule|request\s+a?\s*(?:quote|demo|call|appointment)?|"
    r"free\s+trial|get\s+quote|try\s+(?:it\s+)?free|start\s+free|learn\s+more|shop\s+now|order\s+now|"
    r"subscribe|download|claim|join\s+(?:now|free|us)?|register|apply\s+(?:now)?|get\s+(?:access|started|your|a\s+free)?|"
    r"call\s+(?:us|now|today)?|talk\s+to\s+(?:us|an\s+expert|a\s+specialist)?|speak\s+to|consult|"
    r"hire\s+(?:us)?|work\s+with\s+(?:us)?|partner\s+with\s+(?:us)?|get\s+in\s+touch|reach\s+out|"
    r"add\s+to\s+cart|checkout|purchase|upgrade|start\s+(?:now|today)|watch\s+(?:demo|video)|"
    r"see\s+(?:plans|pricing|how\s+it\s+works)|compare\s+plans|view\s+pricing|explore)\b",
    re.IGNORECASE,
)

# Trust signals
TRUST_PATTERNS = re.compile(
    r"\b(testimonial[s]?|review[s]?|rating[s]?|star[s]?|client[s]?|customer[s]?|"
    r"trusted\s+by|as\s+seen\s+in|featured\s+in|award[s]?|certified|certification[s]?|"
    r"accredited|accreditation|guarantee[d]?|money.back|satisfaction|years\s+of\s+experience|"
    r"case\s+stud(?:y|ies)|success\s+stor(?:y|ies)|partner[s]?|logo[s]?|badge[s]?|"
    r"verified|secure|ssl|trust\s+badge|bbb|better\s+business\s+bureau|iso\s+certified|"
    r"google\s+partner|expert[s]?|specialist[s]?|professional[s]?|licensed|insured)\b",
    re.IGNORECASE,
)

# Urgency signals
URGENCY_PATTERNS = re.compile(
    r"\b(limited\s+time|today\s+only|expires?|expiring|hurry|act\s+now|last\s+chance|"
    r"don.t\s+miss|only\s+\d+\s+left|limited\s+(?:spots?|seats?|availability|offer|stock)|"
    r"ends?\s+(?:soon|today|\w+\s+\d+)|offer\s+ends?|sale\s+ends?|while\s+supplies\s+last|"
    r"flash\s+sale|24\s*[\-\/]\s*hour[s]?|countdown|deadline)\b",
    re.IGNORECASE,
)

# Value proposition
VALUE_PATTERNS = re.compile(
    r"\b(guarantee[d]?|free|save|best|#1|number\s+one|award|certified|award.winning|"
    r"top.rated|highest.rated|most\s+popular|recommended|proven|trusted|risk.free|"
    r"no\s+obligation|no\s+contract|cancel\s+anytime|no\s+credit\s+card)\b",
    re.IGNORECASE,
)

# Social proof patterns
SOCIAL_PROOF_PATTERNS = re.compile(
    r"\b(testimonial[s]?|case\s+stud(?:y|ies)|customer[s]?|client[s]?|review[s]?|"
    r"\d+\s*[\+]?\s*(?:customer[s]?|client[s]?|user[s]?|member[s]?|review[s]?|star[s]?)|"
    r"over\s+\d+|more\s+than\s+\d+|trusted\s+by\s+\d+|join\s+\d+|"
    r"social\s+proof|star\s+rating|five.star|4\.?\d\s*out\s*of\s*5|rated\s+\d)\b",
    re.IGNORECASE,
)

# Contact info patterns
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
PHONE_PATTERN = re.compile(
    r"(\+?1?\s*[\(\-\.]?\d{3}[\)\-\.\s]\s*\d{3}[\-\.\s]\d{4}|\(\d{3}\)\s*\d{3}[\-\.]\d{4}|\b\d{3}[\-\.]\d{3}[\-\.]\d{4}\b)",
    re.IGNORECASE,
)


def _get_cta_elements(soup: BeautifulSoup) -> List[str]:
    """Find CTA button/link texts."""
    cta_texts = []
    # Check buttons
    for btn in soup.find_all(["button", "a"]):
        text = btn.get_text(strip=True)
        if text and CTA_KEYWORDS.search(text):
            if text not in cta_texts:
                cta_texts.append(text[:80])
    # Also check input[type=submit] and input[type=button]
    for inp in soup.find_all("input", type=re.compile(r"^(submit|button)$", re.IGNORECASE)):
        val = inp.get("value", "")
        if val and CTA_KEYWORDS.search(val):
            if val not in cta_texts:
                cta_texts.append(val[:80])
    return cta_texts


def _cta_above_fold(html: str, cta_texts: List[str]) -> bool:
    """Heuristic: check if any CTA appears in first 20% of HTML."""
    if not cta_texts or not html:
        return False
    cutoff = max(500, len(html) // 5)
    top_html = html[:cutoff].lower()
    return any(t.lower() in top_html for t in cta_texts)


def _has_contact_info_in_header(soup: BeautifulSoup) -> bool:
    """Check if phone or email is visible in header/nav area."""
    header = soup.find("header")
    nav = soup.find("nav")
    for section in [header, nav]:
        if section:
            section_text = section.get_text(" ", strip=True)
            if PHONE_PATTERN.search(section_text) or EMAIL_PATTERN.search(section_text):
                return True
    return False


def _find_trust_signals(soup: BeautifulSoup, page_text: str) -> List[str]:
    """Find trust signals present on the page."""
    found = []
    # Check for star rating elements
    stars = soup.find_all(class_=re.compile(r"star|rating|review", re.IGNORECASE))
    if stars:
        found.append("Star ratings / review elements")

    # Check for testimonials section
    testimonial_section = soup.find(
        lambda tag: tag.name in ["section", "div", "article"] and
        re.search(r"testimonial|review|client.say|customer.say|what.people.say", tag.get("class", [""])[0] if tag.get("class") else "", re.IGNORECASE)
    )
    if testimonial_section:
        found.append("Testimonials section")

    # Check page text for trust keywords
    matches = TRUST_PATTERNS.findall(page_text)
    unique_matches = list(set(m.lower() for m in matches))[:5]
    for m in unique_matches:
        signal = m.strip()
        if signal and signal not in [f.lower() for f in found]:
            found.append(signal.title())

    return found[:8]


def analyze_page_conversion(page: CrawledPage) -> Dict[str, Any]:
    """Analyze a single page for conversion optimization signals."""
    url = page.url
    html = page.html or ""

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return {
            "url": url,
            "conversion_score": 0,
            "has_cta": False,
            "cta_count": 0,
            "cta_texts": [],
            "has_trust_signals": False,
            "trust_signals_found": [],
            "has_form": False,
            "has_social_proof": False,
            "has_urgency": False,
            "has_contact_info": False,
            "signals": [],
        }

    page_text = soup.get_text(" ", strip=True)

    # CTA detection
    cta_texts = _get_cta_elements(soup)
    has_cta = len(cta_texts) > 0
    cta_count = len(cta_texts)

    # Trust signals
    trust_signals_found = _find_trust_signals(soup, page_text)
    has_trust_signals = len(trust_signals_found) > 0

    # Form presence
    forms = soup.find_all("form")
    has_form = len(forms) > 0

    # Social proof
    has_social_proof = bool(SOCIAL_PROOF_PATTERNS.search(page_text))

    # Urgency signals
    has_urgency = bool(URGENCY_PATTERNS.search(page_text))

    # Contact info in header
    has_contact_info = _has_contact_info_in_header(soup)
    if not has_contact_info:
        # Also check if phone/email visible anywhere near top
        top_text = page_text[:500]
        has_contact_info = bool(PHONE_PATTERN.search(top_text) or EMAIL_PATTERN.search(top_text))

    # CTA above fold
    cta_above = _cta_above_fold(html, cta_texts)

    # Score calculation (0-100)
    score = 0
    if has_cta:
        score += 25
        if cta_above:
            score += 10
        if cta_count >= 2:
            score += 5
    if has_trust_signals:
        score += 20
    if has_form:
        score += 15
    if has_social_proof:
        score += 15
    if has_urgency:
        score += 5
    if has_contact_info:
        score += 5
    # Value proposition check
    if VALUE_PATTERNS.search(page_text[:2000]):
        score += 5

    score = min(100, score)

    # Human-readable signals list
    signals = []
    if has_cta:
        signals.append(f"{cta_count} CTA button(s) found")
    if cta_above:
        signals.append("CTA visible above fold")
    if has_trust_signals:
        signals.append("Trust signals present")
    if has_form:
        signals.append(f"{len(forms)} form(s) detected")
    if has_social_proof:
        signals.append("Social proof present")
    if has_urgency:
        signals.append("Urgency messaging present")
    if has_contact_info:
        signals.append("Contact info visible")
    if not has_cta:
        signals.append("No CTA detected")
    if not has_trust_signals:
        signals.append("No trust signals")

    return {
        "url": url,
        "conversion_score": score,
        "has_cta": has_cta,
        "cta_count": cta_count,
        "cta_texts": cta_texts[:10],
        "has_trust_signals": has_trust_signals,
        "trust_signals_found": trust_signals_found,
        "has_form": has_form,
        "has_social_proof": has_social_proof,
        "has_urgency": has_urgency,
        "has_contact_info": has_contact_info,
        "signals": signals,
    }


def analyze_conversion(pages: List[CrawledPage]) -> Dict[str, Any]:
    """Analyze conversion optimization signals across all pages."""
    html_pages = [p for p in pages if p.html and 200 <= p.status_code < 300]

    if not html_pages:
        return {
            "score": 0.0,
            "page_results": [],
            "summary": {
                "avg_conversion_score": 0,
                "pages_with_cta": 0,
                "pages_with_trust_signals": 0,
                "pages_with_forms": 0,
                "pages_with_social_proof": 0,
                "high_conversion_pages": 0,
                "low_conversion_pages": 0,
            },
            "pages_missing_cta": [],
            "pages_missing_trust": [],
        }

    page_results = []
    for page in html_pages:
        result = analyze_page_conversion(page)
        page_results.append(result)

    total = len(page_results)
    avg_score = sum(r["conversion_score"] for r in page_results) / total if total > 0 else 0
    pages_with_cta = sum(1 for r in page_results if r["has_cta"])
    pages_with_trust = sum(1 for r in page_results if r["has_trust_signals"])
    pages_with_forms = sum(1 for r in page_results if r["has_form"])
    pages_with_social = sum(1 for r in page_results if r["has_social_proof"])
    high_conversion = sum(1 for r in page_results if r["conversion_score"] >= 60)
    low_conversion = sum(1 for r in page_results if r["conversion_score"] < 30)

    pages_missing_cta = [
        {"url": r["url"], "title": r["url"].split("/")[-1] or r["url"]}
        for r in page_results if not r["has_cta"]
    ]

    pages_missing_trust = [
        {"url": r["url"], "conversion_score": r["conversion_score"]}
        for r in page_results if not r["has_trust_signals"]
    ]

    # Sort page results by score descending
    sorted_results = sorted(page_results, key=lambda x: x["conversion_score"], reverse=True)

    overall_score = round(avg_score, 1)

    return {
        "score": overall_score,
        "page_results": sorted_results,
        "summary": {
            "avg_conversion_score": round(avg_score),
            "pages_with_cta": pages_with_cta,
            "pages_with_trust_signals": pages_with_trust,
            "pages_with_forms": pages_with_forms,
            "pages_with_social_proof": pages_with_social,
            "high_conversion_pages": high_conversion,
            "low_conversion_pages": low_conversion,
        },
        "pages_missing_cta": pages_missing_cta[:30],
        "pages_missing_trust": pages_missing_trust[:30],
    }
