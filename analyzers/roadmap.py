"""
Generate a 90-day SEO roadmap from audit findings using Ollama.
"""
import json
import urllib.request
from typing import Dict, Any


def _ollama(prompt: str, max_tokens: int = 700) -> str:
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
            timeout=120,
        )
        return json.loads(r.read())["response"].strip()
    except Exception as e:
        return f"[Ollama error: {e}]"


ROADMAP_KEYS = [
    "MONTH1_TITLE", "MONTH1_ACTION1", "MONTH1_ACTION2", "MONTH1_ACTION3", "MONTH1_OUTCOME",
    "MONTH2_TITLE", "MONTH2_ACTION1", "MONTH2_ACTION2", "MONTH2_ACTION3", "MONTH2_OUTCOME",
    "MONTH3_TITLE", "MONTH3_ACTION1", "MONTH3_ACTION2", "MONTH3_ACTION3", "MONTH3_OUTCOME",
    "QUICK_WIN",
]


def generate_roadmap(
    domain: str,
    scores: Dict,
    local_seo: Dict,
    trust_signals: Dict,
    competitor_gap: Dict,
    lead_score: Dict,
) -> Dict[str, Any]:
    issues = []
    for cat, label in [
        ("technical", "Technical SEO"),
        ("onpage", "On-Page SEO"),
        ("local_seo", "Local SEO"),
        ("performance", "Performance"),
        ("conversion", "Conversion"),
    ]:
        s = scores.get(cat, 100)
        if s < 70:
            issues.append(f"{label} score: {s}/100")

    if local_seo.get("review_gap", 0) > 20:
        issues.append(f"Review gap: {local_seo['review_gap']} reviews behind nearest competitor")
    if trust_signals.get("missing"):
        issues.append(f"Missing trust signals: {', '.join(trust_signals['missing'][:3])}")
    if competitor_gap.get("available") and competitor_gap.get("WEAKNESS_1"):
        issues.append(f"Competitor weakness to exploit: {competitor_gap['WEAKNESS_1']}")

    issues_text = "\n".join(f"- {i}" for i in issues[:7]) or "- General SEO improvement needed"
    tier = lead_score.get("tier", "")

    raw = _ollama(f"""You are an SEO strategist writing a 90-day action plan for {domain}.

Audit findings:
{issues_text}
Lead tier: {tier}

Respond with EXACTLY these labeled lines:

MONTH1_TITLE: [short title, e.g. "Technical Foundations"]
MONTH1_ACTION1: [specific action starting with a verb]
MONTH1_ACTION2: [specific action]
MONTH1_ACTION3: [specific action]
MONTH1_OUTCOME: [expected result by end of month 1]

MONTH2_TITLE: [short title]
MONTH2_ACTION1: [specific action]
MONTH2_ACTION2: [specific action]
MONTH2_ACTION3: [specific action]
MONTH2_OUTCOME: [expected result by end of month 2]

MONTH3_TITLE: [short title]
MONTH3_ACTION1: [specific action]
MONTH3_ACTION2: [specific action]
MONTH3_ACTION3: [specific action]
MONTH3_OUTCOME: [expected result by end of month 3]

QUICK_WIN: [one action doable in 48 hours for immediate impact]

Only output these labeled lines. Be specific to the findings.""",
        max_tokens=600,
    )

    result: Dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        for key in ROADMAP_KEYS:
            if line.startswith(f"{key}:"):
                result[key] = line.replace(f"{key}:", "").strip()
                break

    return result
