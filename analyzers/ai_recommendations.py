import re
from typing import Dict, Any, List
import ollama

OLLAMA_MODEL = "llama3.2"

SYSTEM_PROMPT = """You are a senior SEO consultant writing a client audit report.
Output ONLY in the exact format requested. No extra text, no explanations outside the format.
Be specific, direct and concise. Every recommendation must be actionable."""


def _ask_raw(prompt: str, max_tokens: int = 300) -> str:
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            options={"num_predict": max_tokens, "temperature": 0.6},
        )
        return response["message"]["content"].strip()
    except Exception as e:
        return ""


def _parse_card(text: str) -> Dict[str, Any]:
    """Parse structured card format from AI output."""
    card = {"headline": "", "impact": "", "steps": []}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("HEADLINE:"):
            card["headline"] = line.replace("HEADLINE:", "").strip()
        elif line.startswith("IMPACT:"):
            card["impact"] = line.replace("IMPACT:", "").strip()
        elif line.startswith("STEP"):
            parts = line.split("|")
            if len(parts) >= 3:
                card["steps"].append({
                    "time": parts[1].strip(),
                    "action": parts[2].strip(),
                })
    return card


def _parse_verdict(text: str) -> Dict[str, str]:
    """Parse verdict format."""
    result = {"score_label": "", "verdict": "", "top_win": ""}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("VERDICT:"):
            result["verdict"] = line.replace("VERDICT:", "").strip()
        elif line.startswith("TOP_WIN:"):
            result["top_win"] = line.replace("TOP_WIN:", "").strip()
    return result


def _parse_action_plan(text: str) -> List[Dict[str, Any]]:
    """Parse week-by-week action plan."""
    weeks = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("WEEK"):
            parts = line.split("|")
            if len(parts) >= 3:
                weeks.append({
                    "label": parts[0].strip(),
                    "focus": parts[1].strip(),
                    "tasks": [t.strip() for t in parts[2:]],
                })
    return weeks


def _score_to_status(score: float) -> str:
    if score >= 70:
        return "good"
    elif score >= 40:
        return "warning"
    return "critical"


def _status_emoji(status: str) -> str:
    return {"critical": "🔴", "warning": "🟡", "good": "🟢"}.get(status, "🟡")


def generate_ai_recommendations(
    domain: str,
    total_pages: int,
    scores: Dict[str, Any],
    technical: Dict[str, Any],
    onpage: Dict[str, Any],
    schema: Dict[str, Any],
    aeo: Dict[str, Any],
    geo: Dict[str, Any],
    performance: Dict[str, Any],
    images: Dict[str, Any],
    local_seo: Dict[str, Any],
    conversion: Dict[str, Any],
    content: Dict[str, Any],
) -> Dict[str, Any]:

    overall_score = scores.get("overall_score", 0)
    grade = scores.get("grade", "F")
    cat_scores = scores.get("category_scores", {})

    def get_score(cat): return cat_scores.get(cat, {}).get("score", 0)

    tech_s    = technical.get("summary", {})
    op_s      = onpage.get("summary", {})
    local_s   = local_seo.get("summary", {})
    aeo_s     = aeo.get("summary", {})
    geo_s     = geo.get("summary", {})
    conv_s    = conversion.get("summary", {})
    content_s = content.get("summary", {})
    missing_local = local_seo.get("missing_local_signals", [])

    results = {}

    # ── 1. Verdict card (top of AI section) ──────────────────────────────────
    verdict_prompt = f"""Audit of {domain}: overall score {overall_score}/100 (Grade {grade}).
Scores — Technical:{get_score('technical')} OnPage:{get_score('onpage')} LocalSEO:{get_score('local_seo')} AEO:{get_score('aeo')} GEO:{get_score('geo')} Conversion:{get_score('conversion')}

Output EXACTLY this format (2 lines only):
VERDICT: [One punchy sentence — what the score means for their business]
TOP_WIN: [The single highest-impact action they should do this week]"""

    results["verdict"] = _parse_verdict(_ask_raw(verdict_prompt, 80))

    # ── 2. Recommendation cards for weak areas ────────────────────────────────
    cards = []

    # Local SEO
    local_score = get_score("local_seo")
    local_prompt = f"""Local SEO audit for {domain}. Score: {local_score}/100.
Missing: {', '.join(missing_local[:3]) if missing_local else 'none'}.
Has contact page: {local_seo.get('has_contact_page', False)}. Has Google Maps: {local_seo.get('has_google_maps', False)}. Has LocalBusiness schema: {local_seo.get('has_local_business_schema', False)}.

Output EXACTLY this format:
HEADLINE: [One punchy headline about their local SEO problem]
IMPACT: [One sentence — what this costs them in customers/revenue]
STEP 1 | [time e.g. 10 mins] | [exact action]
STEP 2 | [time] | [exact action]
STEP 3 | [time] | [exact action]"""

    card_data = _parse_card(_ask_raw(local_prompt, 150))
    if card_data["headline"]:
        cards.append({
            "category": "Local SEO",
            "icon": "📍",
            "score": local_score,
            "status": _score_to_status(local_score),
            "emoji": _status_emoji(_score_to_status(local_score)),
            **card_data,
        })

    # AEO
    aeo_score = get_score("aeo")
    if aeo_score < 75:
        aeo_prompt = f"""AEO audit for {domain}. Score: {aeo_score}/100.
FAQ pages: {aeo_s.get('pages_with_faq_content', 0)}/{total_pages}. Question headings: {aeo_s.get('pages_with_question_headings', 0)}. HowTo content: {aeo_s.get('pages_with_howto_content', 0)}.

Output EXACTLY this format:
HEADLINE: [One punchy headline about their AEO problem]
IMPACT: [One sentence — what featured snippets/voice search traffic they're missing]
STEP 1 | [time] | [exact action]
STEP 2 | [time] | [exact action]
STEP 3 | [time] | [exact action]"""

        card_data = _parse_card(_ask_raw(aeo_prompt, 150))
        if card_data["headline"]:
            cards.append({
                "category": "AEO",
                "icon": "💡",
                "score": aeo_score,
                "status": _score_to_status(aeo_score),
                "emoji": _status_emoji(_score_to_status(aeo_score)),
                **card_data,
            })

    # GEO
    geo_score = get_score("geo")
    if geo_score < 80:
        geo_prompt = f"""GEO (AI Search) audit for {domain}. Score: {geo_score}/100.
About page: {geo.get('has_about_page', False)}. Author bylines: {geo_s.get('pages_with_author_byline', 0)} pages. Stats/data: {geo_s.get('pages_with_statistics', 0)} pages.

Output EXACTLY this format:
HEADLINE: [One punchy headline about their AI search visibility problem]
IMPACT: [One sentence — what AI citation opportunities they're missing]
STEP 1 | [time] | [exact action]
STEP 2 | [time] | [exact action]
STEP 3 | [time] | [exact action]"""

        card_data = _parse_card(_ask_raw(geo_prompt, 150))
        if card_data["headline"]:
            cards.append({
                "category": "GEO / AI Search",
                "icon": "🌐",
                "score": geo_score,
                "status": _score_to_status(geo_score),
                "emoji": _status_emoji(_score_to_status(geo_score)),
                **card_data,
            })

    # Conversion
    conv_score = get_score("conversion")
    if conv_score < 80:
        conv_prompt = f"""Conversion audit for {domain}. Score: {conv_score}/100.
Pages with CTA: {conv_s.get('pages_with_cta', 0)}/{total_pages}. Forms: {conv_s.get('pages_with_forms', 0)}. Trust signals: {conv_s.get('pages_with_trust_signals', 0)}. Social proof: {conv_s.get('pages_with_social_proof', 0)}.

Output EXACTLY this format:
HEADLINE: [One punchy headline about their conversion problem]
IMPACT: [One sentence — what leads/sales they're losing right now]
STEP 1 | [time] | [exact action]
STEP 2 | [time] | [exact action]
STEP 3 | [time] | [exact action]"""

        card_data = _parse_card(_ask_raw(conv_prompt, 150))
        if card_data["headline"]:
            cards.append({
                "category": "Conversion",
                "icon": "🎯",
                "score": conv_score,
                "status": _score_to_status(conv_score),
                "emoji": _status_emoji(_score_to_status(conv_score)),
                **card_data,
            })

    # Technical (only if bad)
    tech_score = get_score("technical")
    if tech_score < 80:
        tech_prompt = f"""Technical SEO audit for {domain}. Score: {tech_score}/100.
Broken pages: {tech_s.get('broken_pages', 0)}. Slow pages: {tech_s.get('slow_pages', 0)}. Server errors: {tech_s.get('server_errors', 0)}.

Output EXACTLY this format:
HEADLINE: [One punchy headline about their technical problem]
IMPACT: [One sentence — how this is hurting their rankings right now]
STEP 1 | [time] | [exact action]
STEP 2 | [time] | [exact action]
STEP 3 | [time] | [exact action]"""

        card_data = _parse_card(_ask_raw(tech_prompt, 150))
        if card_data["headline"]:
            cards.append({
                "category": "Technical SEO",
                "icon": "⚙️",
                "score": tech_score,
                "status": _score_to_status(tech_score),
                "emoji": _status_emoji(_score_to_status(tech_score)),
                **card_data,
            })

    # On-Page (only if bad)
    onpage_score = get_score("onpage")
    if onpage_score < 80:
        onpage_prompt = f"""On-Page SEO audit for {domain}. Score: {onpage_score}/100.
Missing H1: {op_s.get('missing_h1', 0)}. Missing meta desc: {op_s.get('missing_meta_description', 0)}. Titles too long: {op_s.get('title_too_long', 0)}.

Output EXACTLY this format:
HEADLINE: [One punchy headline about their on-page problem]
IMPACT: [One sentence — how this affects their Google rankings]
STEP 1 | [time] | [exact action]
STEP 2 | [time] | [exact action]
STEP 3 | [time] | [exact action]"""

        card_data = _parse_card(_ask_raw(onpage_prompt, 150))
        if card_data["headline"]:
            cards.append({
                "category": "On-Page SEO",
                "icon": "📝",
                "score": onpage_score,
                "status": _score_to_status(onpage_score),
                "emoji": _status_emoji(_score_to_status(onpage_score)),
                **card_data,
            })

    # Sort: critical first, then warning, then good
    order = {"critical": 0, "warning": 1, "good": 2}
    cards.sort(key=lambda c: order.get(c["status"], 3))
    results["cards"] = cards

    # ── 3. 30-Day Action Plan ─────────────────────────────────────────────────
    lowest = sorted(cat_scores.items(), key=lambda x: x[1].get("score", 0))[:3]
    plan_prompt = f"""30-day action plan for {domain}. Overall score: {overall_score}/100.
Weakest areas: {', '.join([f'{k}({v.get("score",0)}/100)' for k,v in lowest])}.

Output EXACTLY this format (3 lines, one per week group):
WEEK 1 | Quick wins (1-2 hrs total) | [task 1] | [task 2] | [task 3]
WEEK 2 | Medium fixes (half day) | [task 1] | [task 2] | [task 3]
WEEK 3-4 | Strategic improvements | [task 1] | [task 2] | [task 3]"""

    results["action_plan"] = _parse_action_plan(_ask_raw(plan_prompt, 200))

    return results
