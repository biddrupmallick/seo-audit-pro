import re
from typing import Dict, Any, List

from analyzers.ollama_client import chat

OLLAMA_MODEL = "llama3.1"

SYSTEM_PROMPT = """You are a world-class digital growth specialist with 15 years of hands-on experience across:

SEO: You have deep knowledge of Google's ranking algorithms, Core Web Vitals, technical SEO, crawl optimization, link architecture, and content strategy. You have helped 300+ businesses recover from Google penalties and achieve page 1 rankings.

LOCAL SEO: You specialize in helping local and small businesses dominate their geographic area in Google Maps, Local Pack results, and "near me" searches. You know exactly how NAP consistency, LocalBusiness schema, Google Business Profile optimization, and review signals work together.

GEO (Generative Engine Optimization): You are an expert in optimizing content to be cited by AI systems like ChatGPT, Perplexity, Google AI Overviews, and Bing Copilot. You understand E-E-A-T, entity authority, citation-worthy content structures, and how AI models select sources.

AEO (Answer Engine Optimization): You specialize in winning featured snippets, People Also Ask boxes, voice search results, and zero-click positions. You know exactly how to structure FAQ content, definition blocks, numbered lists, and concise answers to trigger these positions.

CONVERSION OPTIMIZATION: You have increased conversion rates for 200+ websites. You understand CTA psychology, trust signal placement, above-the-fold optimization, form design, social proof positioning, and urgency triggers that turn visitors into leads.

BUSINESS DEVELOPMENT: You know how to identify quick revenue opportunities from audit data and frame recommendations in terms of business impact — lost customers, missed revenue, competitive disadvantage.

Your writing style: Direct, confident, specific. You never give generic advice. Every recommendation references the actual data from the audit. You think in terms of business outcomes, not just technical fixes.

Output ONLY in the exact format requested. No extra text outside the format."""


def _ask_raw(prompt: str, max_tokens: int = 300) -> str:
    try:
        return chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.6,
        )
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
