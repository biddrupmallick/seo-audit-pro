"""
Aggregate and analyse review text across 100+ businesses using Ollama.
Groups by category + state for niche-level insights.
"""
from typing import List, Dict, Any

from analyzers.ollama_client import ask


def _ollama(prompt: str, max_tokens: int = 800) -> str:
    return ask(prompt, max_tokens=max_tokens, temperature=0.4)


def analyze_reviews_batch(businesses: List[Dict]) -> Dict[str, Any]:
    """
    Aggregate all review_text by category+state and extract niche insights.
    Returns structured analysis.
    """
    # Group by category + state
    groups: Dict[str, Dict] = {}
    for biz in businesses:
        cat = (biz.get("category") or "Business").strip()
        state = (biz.get("state") or "").strip()
        key = f"{cat} | {state}" if state else cat

        if key not in groups:
            groups[key] = {
                "category": cat,
                "state": state,
                "businesses": [],
                "all_reviews": [],
                "ratings": [],
                "review_counts": [],
            }
        groups[key]["businesses"].append(biz.get("name", ""))
        if biz.get("reviews_text"):
            groups[key]["all_reviews"].append(biz["reviews_text"])
        if biz.get("rating"):
            groups[key]["ratings"].append(float(biz["rating"]))
        if biz.get("reviews"):
            try:
                groups[key]["review_counts"].append(int(biz["reviews"]))
            except Exception:
                pass

    results = {}
    for key, grp in groups.items():
        cat = grp["category"]
        state = grp["state"]
        biz_count = len(grp["businesses"])
        avg_rating = round(sum(grp["ratings"]) / len(grp["ratings"]), 1) if grp["ratings"] else None
        avg_reviews = int(sum(grp["review_counts"]) / len(grp["review_counts"])) if grp["review_counts"] else None
        combined_text = "\n\n---\n\n".join(grp["all_reviews"][:30])  # cap at 30 to stay within context

        if combined_text:
            prompt = f"""You are a market research analyst specialising in local business SEO.

I collected reviews from {biz_count} {cat} businesses{f' in {state}' if state else ''}.
Average rating: {avg_rating}★  |  Average review count: {avg_reviews}

REVIEW SAMPLES:
{combined_text[:6000]}

Analyse these reviews and respond in EXACTLY this format:

TOP_PRAISE: [3 most common things customers praise, comma-separated]
TOP_COMPLAINTS: [3 most common complaints, comma-separated]
STAFF_PATTERNS: [behaviours or traits mentioned about staff, comma-separated]
SERVICE_KEYWORDS: [top 5 services customers actually mention, comma-separated]
DIFFERENTIATORS: [what separates 5-star from 3-star businesses in this niche, one sentence]
RESPONSE_RATE: [is owner responding to reviews? yes/no/partial]
CUSTOMER_LANGUAGE: [3-5 exact words/phrases customers use repeatedly, in quotes]
KEY_INSIGHT: [single most surprising or actionable finding from these reviews, one sentence]"""

            raw = _ollama(prompt, max_tokens=500)
        else:
            # No review text — infer from rating, review count, and category
            rating_label = (
                "very high (4.5+)" if (avg_rating or 0) >= 4.5
                else "good (4.0–4.4)" if (avg_rating or 0) >= 4.0
                else "average (3.5–3.9)" if (avg_rating or 0) >= 3.5
                else "below average (under 3.5)"
            )
            prompt = f"""You are a market research analyst specialising in local business SEO.

I have {biz_count} {cat} businesses{f' in {state}' if state else ''} with no review text available.
Average rating: {avg_rating}★ ({rating_label})  |  Average review count: {avg_reviews}

Based on your knowledge of {cat} businesses with a {rating_label} rating, infer likely customer sentiment.

Respond in EXACTLY this format:

TOP_PRAISE: [3 most likely things customers praise for a {cat} business with this rating, comma-separated]
TOP_COMPLAINTS: [3 most likely complaints for a {cat} business with this rating, comma-separated]
STAFF_PATTERNS: [typical staff behaviours mentioned for {cat} businesses at this rating level, comma-separated]
SERVICE_KEYWORDS: [top 5 services customers typically mention for {cat} businesses, comma-separated]
DIFFERENTIATORS: [what typically separates 5-star from 3-star {cat} businesses, one sentence]
RESPONSE_RATE: [typical owner response rate for {cat} businesses at this rating: yes/no/partial]
CUSTOMER_LANGUAGE: [3-5 words/phrases customers commonly use for {cat} businesses, in quotes]
KEY_INSIGHT: [single most actionable insight for a {cat} business at {avg_rating}★ to improve, one sentence]"""

            raw = _ollama(prompt, max_tokens=500)

        parsed = {}
        for line in raw.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                parsed[k.strip()] = v.strip()

        results[key] = {
            "category": cat,
            "state": state,
            "business_count": biz_count,
            "avg_rating": avg_rating,
            "avg_reviews": avg_reviews,
            "has_review_text": bool(combined_text),
            "inferred": not bool(combined_text),
            "analysis": parsed,
        }

    return results
