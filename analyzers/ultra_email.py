"""
Per-business cold email generator using Ollama.
One unique email per business — feels hand-written, not spammy.
"""
import re
from typing import List, Dict, Any

from analyzers.ollama_client import ask


def _ollama(prompt: str, max_tokens: int = 300) -> str:
    return ask(prompt, max_tokens=max_tokens, temperature=0.8)


def _enforce_two_sentences(text: str) -> str:
    """Hard-trim to exactly 2 sentences no matter what."""
    # Collapse all whitespace/newlines into single spaces
    text = re.sub(r'\s+', ' ', text).strip()
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text)
    # Filter out empty fragments
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return text
    result = " ".join(sentences[:2])
    if result[-1] not in ".!?":
        result += "."
    return result


def _build_prompt(biz: Dict, analysis: Dict) -> str:
    _parts = (biz.get("owner_name") or "").split()
    owner_first = _parts[0] if _parts else "there"
    biz_name = biz.get("name") or "your business"
    category = biz.get("category") or "local business"
    rating = biz.get("rating") or ""
    my_reviews = biz.get("reviews") or 0

    # City from address
    address = biz.get("address") or ""
    city = ""
    if address:
        parts = address.split(",")
        if len(parts) >= 2:
            city = parts[-2].strip()

    # Nearest competitor data
    competitors = biz.get("nearest_competitors") or []
    comp = competitors[0] if competitors else {}
    comp_name = comp.get("name") or ""
    comp_distance = comp.get("distance_miles") or ""
    comp_reviews = comp.get("reviews") or ""
    comp_rating = comp.get("rating") or ""

    # Review analysis insights
    praise = analysis.get("TOP_PRAISE") or "quality service"
    pain = analysis.get("TOP_COMPLAINTS") or "online visibility"
    differentiator = analysis.get("DIFFERENTIATORS") or "review count and online presence"
    opportunity = analysis.get("OPPORTUNITY") or ""

    # Build context block
    context_parts = []
    if city:
        context_parts.append(f"City: {city}")
    if rating:
        context_parts.append(f"Their Google rating: {rating}★ ({my_reviews} reviews)")
    if comp_name:
        comp_info = f"Nearest competitor: {comp_name}"
        if comp_distance:
            comp_info += f" ({comp_distance} miles away)"
        if comp_reviews:
            comp_info += f" with {comp_reviews} reviews"
        if comp_rating:
            comp_info += f" and {comp_rating}★"
        context_parts.append(comp_info)
    context_parts.append(f"What customers in this niche praise: {praise}")
    context_parts.append(f"Common pain in this niche: {pain}")
    context_parts.append(f"What separates winners: {differentiator}")
    if opportunity:
        context_parts.append(f"Key opportunity: {opportunity}")

    context = "\n".join(f"- {p}" for p in context_parts)

    review_gap = ""
    if comp_reviews and my_reviews:
        try:
            gap = int(comp_reviews) - int(my_reviews)
            if gap > 0:
                review_gap = f"{comp_name} has {gap} more reviews than {biz_name}."
        except Exception:
            pass

    return f"""You are a professional cold email copywriter for a local SEO agency.

Write a cold outreach email to {owner_first}, the owner of {biz_name} ({category}).

Business context:
{context}
{f"Review gap note: {review_gap}" if review_gap else ""}

Rules (follow strictly — violations will be rejected):
- EXACTLY 2 sentences in the BODY. Not 1. Not 3. Exactly 2.
- Sentence 1: One hyper-local observation using real numbers (competitor name, distance, review gap). Do NOT start with "I".
- Sentence 2: One soft call to action ending with a question mark.
- No third sentence. Stop after the question mark.
- Sound like a real human, not a template
- No buzzwords: no "leverage", "optimize", "synergy", "digital presence"
- No compliments, no "I hope this finds you well"
- No mention of being an AI

Output format — two lines only:
SUBJECT: (one compelling subject line, max 8 words, no clickbait)
BODY: (exactly 2 sentences)"""


def _generate_email_for_business(biz: Dict, analysis: Dict) -> Dict[str, str]:
    prompt = _build_prompt(biz, analysis)
    raw = _ollama(prompt, max_tokens=200)

    subject = ""
    body = ""
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("SUBJECT:"):
            subject = line[8:].strip()
        elif line.upper().startswith("BODY:"):
            body = line[5:].strip()
        elif body and line:
            body += " " + line

    # Fallbacks
    _parts = (biz.get("owner_name") or "").split()
    owner_first = _parts[0] if _parts else "there"
    biz_name = biz.get("name") or "your business"
    competitors = biz.get("nearest_competitors") or []
    comp = competitors[0] if competitors else {}
    comp_name = comp.get("name") or "a nearby competitor"
    comp_distance = comp.get("distance_miles") or "?"
    comp_reviews = comp.get("reviews") or "more"
    my_reviews = biz.get("reviews") or "fewer"

    # Truncate long competitor names for email readability
    comp_name_short = comp_name.split("|")[0].strip() if "|" in comp_name else comp_name
    if len(comp_name_short) > 40:
        comp_name_short = comp_name_short[:37] + "..."

    if not subject:
        subject = f"Quick question about {biz_name}"

    if not body:
        try:
            gap = int(comp_reviews) - int(my_reviews)
        except Exception:
            gap = 0

        if gap > 0:
            # Competitor has more reviews — client is behind
            body = (
                f"{comp_name_short}, just {comp_distance} miles away, already has {gap} more Google reviews "
                f"than {biz_name} — and that gap sends local customers their way first. "
                f"I put together a short plan to close it in 60 days — want me to send it over, {owner_first}?"
            )
        else:
            # Client is ahead — frame as protecting their lead
            body = (
                f"{biz_name} already leads {comp_name_short} on Google reviews, but the businesses "
                f"that hold that lead long-term are the ones actively managing their online presence. "
                f"I spotted a few quick wins on your profile — want me to share them, {owner_first}?"
            )

    body = _enforce_two_sentences(body)

    return {"subject": subject, "body": body}


def generate_ultra_emails(businesses: List[Dict], category: str, state: str, analysis: Dict) -> List[Dict]:
    """
    Generate one unique cold email per business using Ollama.
    Each email is written fresh with that business's real data.
    """
    results = []
    for biz in businesses:
        email = _generate_email_for_business(biz, analysis)

        owner_email = biz.get("owner_email", "")
        website_email = biz.get("website_email", "")
        competitors = biz.get("nearest_competitors") or []
        comp = competitors[0] if competitors else {}

        results.append({
            "name": biz.get("name", ""),
            "owner_name": biz.get("owner_name", ""),
            "owner_email": owner_email,
            "website_email": website_email,
            "contact_email": owner_email or website_email,
            "website": biz.get("website", ""),
            "subject": email["subject"],
            "body": email["body"],
            "nearest_competitor": comp.get("name", ""),
            "distance": comp.get("distance_miles", ""),
        })

    return results
