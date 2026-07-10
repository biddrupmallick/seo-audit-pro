"""
Aggregate and analyse review text across 100+ businesses using Ollama.
Groups by category + state for niche-level insights.
"""
import json
import urllib.request
from typing import List, Dict, Any


def _ollama(prompt: str, max_tokens: int = 800) -> str:
    try:
        payload = json.dumps({
            "model": "llama3.1",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": max_tokens},
        }).encode()
        r = urllib.request.urlopen(
            urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            ),
            timeout=120,
        )
        return json.loads(r.read())["response"].strip()
    except Exception as e:
        return f"[Ollama error: {e}]"


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
            parsed = {}
            for line in raw.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    parsed[k.strip()] = v.strip()
        else:
            parsed = {}

        results[key] = {
            "category": cat,
            "state": state,
            "business_count": biz_count,
            "avg_rating": avg_rating,
            "avg_reviews": avg_reviews,
            "has_review_text": bool(combined_text),
            "analysis": parsed,
        }

    return results
