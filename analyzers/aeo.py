import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from crawler.spider import CrawledPage


QUESTION_STARTERS = re.compile(
    r"^(who|what|when|where|why|how|which|can|does|do|is|are|will|should|could|would)\b",
    re.IGNORECASE,
)

DEFINITION_PATTERNS = [
    re.compile(r"\bis\s+a\s+(type|kind|form|example|method|way)\b", re.IGNORECASE),
    re.compile(r"\brefers?\s+to\b", re.IGNORECASE),
    re.compile(r"\bdefined?\s+as\b", re.IGNORECASE),
    re.compile(r"\bmeans?\s+that\b", re.IGNORECASE),
    re.compile(r"\bknown\s+as\b", re.IGNORECASE),
]

STAT_PATTERNS = re.compile(
    r"\b\d+(\.\d+)?\s*(%|percent|million|billion|thousand|k\b)",
    re.IGNORECASE,
)


def analyze_page_aeo(html: str, url: str) -> Dict[str, Any]:
    """Analyze a single page for AEO signals."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return {"url": url, "aeo_score": 0, "signals": []}

    signals = []
    aeo_score = 0

    # 1. FAQ sections via <details> elements
    details_count = len(soup.find_all("details"))
    if details_count > 0:
        signals.append(f"Has {details_count} <details> FAQ element(s)")
        aeo_score += min(20, details_count * 5)

    # 2. FAQ schema present
    has_faq_schema = False
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                items = [data]
                if "@graph" in data:
                    items = data["@graph"]
                for item in items:
                    schema_type = item.get("@type", "")
                    if isinstance(schema_type, list):
                        schema_type = " ".join(schema_type)
                    if "FAQ" in schema_type or "faq" in schema_type.lower():
                        has_faq_schema = True
        except Exception:
            pass
    if has_faq_schema:
        signals.append("Has FAQPage structured data")
        aeo_score += 25

    # 3. Question-based headings
    question_headings = []
    for heading in soup.find_all(["h2", "h3", "h4"]):
        text = heading.get_text(strip=True)
        if QUESTION_STARTERS.match(text) or text.endswith("?"):
            question_headings.append(text)
    if question_headings:
        signals.append(f"Has {len(question_headings)} question-based heading(s)")
        aeo_score += min(20, len(question_headings) * 4)

    # 4. FAQ headings (H2/H3 containing "FAQ" or "frequently asked")
    faq_headings = []
    for heading in soup.find_all(["h2", "h3"]):
        text = heading.get_text(strip=True).lower()
        if "faq" in text or "frequently asked" in text or "common question" in text:
            faq_headings.append(heading.get_text(strip=True))
    if faq_headings:
        signals.append(f"Has {len(faq_headings)} FAQ section heading(s)")
        aeo_score += min(15, len(faq_headings) * 8)

    # 5. Definition-style content (featured snippet eligibility)
    page_text = soup.get_text(" ", strip=True)
    definition_count = sum(1 for p in DEFINITION_PATTERNS if p.search(page_text))
    if definition_count >= 2:
        signals.append("Contains definition-style content (good for featured snippets)")
        aeo_score += 15

    # 6. Numbered lists / step-by-step content (HowTo signals)
    ol_tags = soup.find_all("ol")
    numbered_list_items = sum(len(ol.find_all("li")) for ol in ol_tags)
    if numbered_list_items >= 3:
        signals.append(f"Has numbered list with {numbered_list_items} items (HowTo signal)")
        aeo_score += min(15, numbered_list_items)

    # 7. HowTo or step-related headings
    howto_headings = []
    for heading in soup.find_all(["h2", "h3"]):
        text = heading.get_text(strip=True).lower()
        if any(kw in text for kw in ["how to", "step by step", "steps to", "guide to", "tutorial"]):
            howto_headings.append(heading.get_text(strip=True))
    if howto_headings:
        signals.append(f"Has {len(howto_headings)} HowTo-style heading(s)")
        aeo_score += min(10, len(howto_headings) * 5)

    # 8. Table of contents (good for long-form answers)
    toc_indicators = soup.find_all(class_=re.compile(r"toc|table.of.contents|contents", re.IGNORECASE))
    if toc_indicators:
        signals.append("Has table of contents")
        aeo_score += 10

    # 9. Concise answer paragraphs (short paragraphs under headings)
    concise_answers = 0
    for heading in soup.find_all(["h2", "h3"]):
        next_sib = heading.find_next_sibling()
        if next_sib and next_sib.name == "p":
            text = next_sib.get_text(strip=True)
            if 40 < len(text) < 300:
                concise_answers += 1
    if concise_answers >= 2:
        signals.append(f"Has {concise_answers} concise answer paragraph(s) below headings")
        aeo_score += min(10, concise_answers * 3)

    aeo_score = min(100, aeo_score)

    return {
        "url": url,
        "aeo_score": aeo_score,
        "signals": signals,
        "question_headings": question_headings[:10],
        "faq_headings": faq_headings,
        "has_faq_schema": has_faq_schema,
        "has_details_elements": details_count > 0,
        "numbered_list_items": numbered_list_items,
        "howto_headings": howto_headings[:5],
    }


def analyze_aeo(pages: List[CrawledPage]) -> Dict[str, Any]:
    """Analyze AEO readiness across all pages."""
    html_pages = [p for p in pages if p.html and 200 <= p.status_code < 300]

    page_results = []
    for page in html_pages:
        result = analyze_page_aeo(page.html, page.url)
        page_results.append(result)

    total = len(page_results)
    if total == 0:
        return {
            "score": 0,
            "total_pages": 0,
            "page_results": [],
            "summary": {
                "avg_aeo_score": 0,
                "pages_with_faq_content": 0,
                "pages_with_question_headings": 0,
                "pages_with_howto_content": 0,
                "high_aeo_readiness_pages": 0,
            },
        }

    avg_score = sum(r["aeo_score"] for r in page_results) / total
    pages_with_faq = [r for r in page_results if r["faq_headings"] or r["has_faq_schema"] or r["has_details_elements"]]
    pages_with_questions = [r for r in page_results if r["question_headings"]]
    pages_with_howto = [r for r in page_results if r["howto_headings"]]
    high_aeo_pages = [r for r in page_results if r["aeo_score"] >= 50]

    return {
        "score": round(avg_score, 1),
        "total_pages": total,
        "page_results": sorted(page_results, key=lambda x: x["aeo_score"], reverse=True),
        "summary": {
            "avg_aeo_score": round(avg_score, 1),
            "pages_with_faq_content": len(pages_with_faq),
            "pages_with_question_headings": len(pages_with_questions),
            "pages_with_howto_content": len(pages_with_howto),
            "high_aeo_readiness_pages": len(high_aeo_pages),
        },
    }
