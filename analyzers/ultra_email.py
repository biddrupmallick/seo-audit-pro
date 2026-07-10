"""
Ultra-short 2-sentence cold email generator.
Uses a single Ollama call to write a template, then fills in
per-business variables programmatically — fast for 100+ businesses.
"""
import json
import urllib.request
from typing import List, Dict, Any


def _ollama(prompt: str, max_tokens: int = 400) -> str:
    try:
        payload = json.dumps({
            "model": "llama3.1",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.5, "num_predict": max_tokens},
        }).encode()
        r = urllib.request.urlopen(
            urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            ),
            timeout=60,
        )
        return json.loads(r.read())["response"].strip()
    except Exception as e:
        return f"[Ollama error: {e}]"


def _generate_template(category: str, state: str, analysis: Dict) -> Dict[str, str]:
    """Generate one email template with placeholders for the whole niche."""
    praise = analysis.get("TOP_PRAISE", "quality service")
    complaint = analysis.get("TOP_COMPLAINTS", "online visibility")
    differentiator = analysis.get("DIFFERENTIATORS", "review count and online presence")

    raw = _ollama(f"""Write a 2-sentence cold email for a local SEO agency reaching out to {category} business owners{f' in {state}' if state else ''}.

Context about this niche:
- Customers praise: {praise}
- Common pain: {complaint}
- What separates winners: {differentiator}

Use these EXACT placeholders (keep the brackets):
[OWNER] = owner first name
[BUSINESS] = business name
[COMPETITOR] = nearest competitor name
[DISTANCE] = distance in miles
[THEIR_REVIEWS] = competitor review count
[MY_REVIEWS] = client review count

Rules:
- Sentence 1: Specific local pain using the placeholders (mention competitor + distance + review gap)
- Sentence 2: One clear low-commitment ask
- Max 2 sentences total — no exceptions
- No fluff, no "I hope this finds you well"
- End with a question

Write SUBJECT: on one line, then BODY: on the next line. Nothing else.""",
        max_tokens=200,
    )

    subject = ""
    body = ""
    for line in raw.splitlines():
        if line.startswith("SUBJECT:"):
            subject = line.replace("SUBJECT:", "").strip()
        elif line.startswith("BODY:"):
            body = line.replace("BODY:", "").strip()
        elif body and line.strip():
            body += " " + line.strip()

    if not subject:
        subject = "[OWNER], [COMPETITOR] ([DISTANCE] mi away) is outranking [BUSINESS] on Google"
    if not body:
        body = (
            "[OWNER], [COMPETITOR] just [DISTANCE] miles away has [THEIR_REVIEWS] reviews vs your [MY_REVIEWS] "
            "— that gap is exactly why they rank above [BUSINESS] when locals search for " + category.lower() + ". "
            "I put together a free 5-minute audit showing how to close it — want me to send it over?"
        )

    return {"subject": subject, "body": body}


def fill_email(template: Dict[str, str], business: Dict) -> Dict[str, str]:
    """Fill template placeholders with per-business data."""
    owner = (business.get("owner_name") or "").split()[0] if business.get("owner_name") else "there"
    biz_name = business.get("name", "your business")
    my_reviews = str(business.get("reviews") or "few")

    competitors = business.get("nearest_competitors", [])
    if competitors:
        comp = competitors[0]
        comp_name = comp.get("name", "a nearby competitor")
        distance = str(comp.get("distance_miles", "?"))
        their_reviews = str(comp.get("reviews") or "more")
    else:
        comp_name = "a nearby competitor"
        distance = "?"
        their_reviews = "more"

    def replace(text: str) -> str:
        return (text
                .replace("[OWNER]", owner)
                .replace("[BUSINESS]", biz_name)
                .replace("[COMPETITOR]", comp_name)
                .replace("[DISTANCE]", distance)
                .replace("[THEIR_REVIEWS]", their_reviews)
                .replace("[MY_REVIEWS]", my_reviews))

    return {
        "subject": replace(template["subject"]),
        "body": replace(template["body"]),
    }


def generate_ultra_emails(businesses: List[Dict], category: str, state: str, analysis: Dict) -> List[Dict]:
    """
    Generate 2-sentence emails for all businesses.
    One Ollama call for the template, then fill per business — fast.
    """
    template = _generate_template(category, state, analysis)
    results = []
    for biz in businesses:
        email = fill_email(template, biz)
        results.append({
            "name": biz.get("name", ""),
            "owner_name": biz.get("owner_name", ""),
            "website": biz.get("website", ""),
            "subject": email["subject"],
            "body": email["body"],
            "nearest_competitor": biz.get("nearest_competitors", [{}])[0].get("name", "") if biz.get("nearest_competitors") else "",
            "distance": biz.get("nearest_competitors", [{}])[0].get("distance_miles", "") if biz.get("nearest_competitors") else "",
        })
    return results
