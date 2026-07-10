"""
Analyze competitor negative reviews to find their weaknesses
and turn them into client opportunities.
"""
import json
import urllib.request
from typing import List, Dict, Any


def _ollama(prompt: str, max_tokens: int = 500) -> str:
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
            timeout=90,
        )
        return json.loads(r.read())["response"].strip()
    except Exception as e:
        return f"[Ollama error: {e}]"


def analyze_competitor_gap(competitors: List[Dict], category: str) -> Dict[str, Any]:
    """Analyze competitor reviews to find weaknesses and opportunities."""
    all_reviews = []
    for comp in competitors:
        rt = (comp.get("reviews_text") or "").strip()
        if rt:
            all_reviews.append(f"[{comp.get('name', 'Competitor')}]: {rt}")

    if not all_reviews:
        return {"available": False}

    combined = "\n\n".join(all_reviews[:5])

    raw = _ollama(f"""You are analyzing customer reviews for {category} businesses to find competitor weaknesses.

Here are reviews from nearby competitors:
{combined}

Respond with EXACTLY these labeled lines:

WEAKNESS_1: [most common complaint across competitors, 1 sentence]
WEAKNESS_2: [second most common complaint, 1 sentence]
WEAKNESS_3: [third complaint, 1 sentence]
OPPORTUNITY_1: [how client wins customers from weakness 1, 1 sentence]
OPPORTUNITY_2: [how client wins customers from weakness 2, 1 sentence]
OPPORTUNITY_3: [how client wins customers from weakness 3, 1 sentence]
EMAIL_HOOK: [one compelling cold email sentence mentioning a specific competitor weakness]
HEADLINE: [short punchy report headline, e.g. "Competitors Keep Losing Customers Over Wait Times"]

Only output these 8 labeled lines. Nothing else.""",
        max_tokens=400,
    )

    result: Dict[str, Any] = {
        "available": True,
        "competitor_count": len(all_reviews),
    }
    keys = ["WEAKNESS_1", "WEAKNESS_2", "WEAKNESS_3",
            "OPPORTUNITY_1", "OPPORTUNITY_2", "OPPORTUNITY_3",
            "EMAIL_HOOK", "HEADLINE"]
    for line in raw.splitlines():
        for key in keys:
            if line.startswith(f"{key}:"):
                result[key] = line.replace(f"{key}:", "").strip()
                break

    return result
