import re
from typing import Dict, Any
import ollama

OLLAMA_MODEL = "llama3.2"

SYSTEM_PROMPT = """You are a world-class SEO consultant with 15+ years of experience specializing in:
- Technical SEO & Core Web Vitals
- Local SEO for small and medium businesses
- AEO (Answer Engine Optimization) for featured snippets and voice search
- GEO (Generative Engine Optimization) for AI search engines like ChatGPT and Perplexity
- Conversion Rate Optimization (CRO)

Your job is to write professional, specific, and actionable audit recommendations for business owners.
Always explain the BUSINESS IMPACT first, then give EXACT steps to fix each issue.
Be direct, confident, and encouraging. Write in plain English — no jargon without explanation.
Keep each recommendation concise but impactful. Never use generic advice."""


def _markdown_to_html(text: str) -> str:
    """Convert basic markdown to HTML for clean report rendering."""
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Bullet points
    text = re.sub(r'^\s*[\*\-]\s+', '• ', text, flags=re.MULTILINE)
    # Numbered lists keep as-is
    return text


def _ask(prompt: str, max_tokens: int = 500) -> str:
    """Send a prompt to Ollama and return the response text."""
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            options={"num_predict": max_tokens, "temperature": 0.7},
        )
        return _markdown_to_html(response["message"]["content"].strip())
    except Exception as e:
        return f"AI recommendation unavailable: {e}"


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
    """Generate AI-powered recommendations using local Llama model via Ollama."""

    overall_score = scores.get("overall_score", 0)
    grade = scores.get("grade", "F")
    cat_scores = scores.get("category_scores", {})

    # Build issue summary for context
    issues = []
    tech_s = technical.get("summary", {})
    if tech_s.get("broken_pages", 0):
        issues.append(f"{tech_s['broken_pages']} broken page(s) returning 404 errors")
    if tech_s.get("slow_pages", 0):
        issues.append(f"{tech_s['slow_pages']} slow page(s) taking over 3 seconds to load")

    op_s = onpage.get("summary", {})
    if op_s.get("missing_title", 0):
        issues.append(f"{op_s['missing_title']} page(s) missing title tags")
    if op_s.get("missing_h1", 0):
        issues.append(f"{op_s['missing_h1']} page(s) missing H1 headings")
    if op_s.get("missing_meta_description", 0):
        issues.append(f"{op_s['missing_meta_description']} page(s) missing meta descriptions")
    if op_s.get("title_too_long", 0):
        issues.append(f"{op_s['title_too_long']} title(s) exceeding 60 characters")

    local_s = local_seo.get("summary", {})
    missing_local = local_seo.get("missing_local_signals", [])

    aeo_s = aeo.get("summary", {})
    geo_s = geo.get("summary", {})
    conv_s = conversion.get("summary", {})
    content_s = content.get("summary", {})
    img_s = images.get("summary", {})

    results = {}

    # 1. Executive AI Summary
    exec_prompt = f"""Write a 3-paragraph executive summary for an SEO audit of {domain}.

Site stats:
- Pages crawled: {total_pages}
- Overall SEO health score: {overall_score}/100 (Grade {grade})
- Technical SEO: {cat_scores.get('technical', {}).get('score', 0)}/100
- On-Page SEO: {cat_scores.get('onpage', {}).get('score', 0)}/100
- Local SEO: {cat_scores.get('local_seo', {}).get('score', 0)}/100
- AEO Readiness: {cat_scores.get('aeo', {}).get('score', 0)}/100
- GEO Readiness: {cat_scores.get('geo', {}).get('score', 0)}/100
- Conversion: {cat_scores.get('conversion', {}).get('score', 0)}/100
- Content Quality: {cat_scores.get('content', {}).get('score', 0)}/100

Key issues found: {', '.join(issues[:5]) if issues else 'No major issues'}

Paragraph 1: Overall assessment and what the score means for their business.
Paragraph 2: The 2-3 biggest opportunities for improvement.
Paragraph 3: Encouraging closing with priority action.

Be specific to this domain. Do not use bullet points — write in flowing paragraphs."""

    results["executive_summary"] = _ask(exec_prompt, max_tokens=400)

    # 2. Local SEO recommendation (if weak)
    local_score = cat_scores.get("local_seo", {}).get("score", 100)
    if local_score < 70:
        local_prompt = f"""Write a Local SEO recommendation for {domain}.

Current Local SEO score: {local_score}/100
Missing signals: {', '.join(missing_local) if missing_local else 'None'}
Has contact page: {local_seo.get('has_contact_page', False)}
Has Google Maps: {local_seo.get('has_google_maps', False)}
Has LocalBusiness schema: {local_seo.get('has_local_business_schema', False)}
Has review schema: {local_seo.get('has_review_schema', False)}
Pages with phone number: {local_s.get('pages_with_phone', 0)}

Write 2-3 specific, actionable recommendations. Explain why each matters for local search rankings and customer trust. Give exact implementation steps."""

        results["local_seo"] = _ask(local_prompt, max_tokens=350)

    # 3. AEO recommendation (if weak)
    aeo_score = cat_scores.get("aeo", {}).get("score", 100)
    if aeo_score < 70:
        aeo_prompt = f"""Write an AEO (Answer Engine Optimization) recommendation for {domain}.

Current AEO score: {aeo_score}/100
Pages with FAQ content: {aeo_s.get('pages_with_faq_content', 0)} of {total_pages}
Pages with question headings: {aeo_s.get('pages_with_question_headings', 0)}
Pages with HowTo content: {aeo_s.get('pages_with_howto_content', 0)}

Explain what AEO means in simple terms, why it matters for getting found in Google featured snippets and voice search, and give 3 specific steps to improve their AEO score. Be practical."""

        results["aeo"] = _ask(aeo_prompt, max_tokens=350)

    # 4. GEO recommendation
    geo_score = cat_scores.get("geo", {}).get("score", 100)
    if geo_score < 80:
        geo_prompt = f"""Write a GEO (Generative Engine Optimization) recommendation for {domain}.

Current GEO score: {geo_score}/100
Has about page: {geo.get('has_about_page', False)}
Has contact page: {geo.get('has_contact_page', False)}
Pages with author byline: {geo_s.get('pages_with_author_byline', 0)}
Pages with statistics/data: {geo_s.get('pages_with_statistics', 0)}
Average GEO score per page: {geo_s.get('avg_geo_score', 0)}

Explain GEO in simple terms (optimizing for ChatGPT, Perplexity, Google AI Overviews), why it's the future of SEO, and give 3 specific steps to improve their chances of being cited by AI engines."""

        results["geo"] = _ask(geo_prompt, max_tokens=350)

    # 5. Conversion recommendation (if weak)
    conv_score = cat_scores.get("conversion", {}).get("score", 100)
    if conv_score < 75:
        conv_prompt = f"""Write a Conversion Optimization recommendation for {domain}.

Current conversion score: {conv_score}/100
Pages with clear CTA: {conv_s.get('pages_with_cta', 0)} of {total_pages}
Pages with trust signals: {conv_s.get('pages_with_trust_signals', 0)}
Pages with contact forms: {conv_s.get('pages_with_forms', 0)}
Pages with social proof: {conv_s.get('pages_with_social_proof', 0)}

Write 3 specific recommendations to improve conversion rate. Focus on practical changes that can be implemented quickly. Explain the revenue impact of each change."""

        results["conversion"] = _ask(conv_prompt, max_tokens=350)

    # 6. Content recommendation (if weak)
    content_score = cat_scores.get("content", {}).get("score", 100)
    if content_score < 75:
        content_prompt = f"""Write a Content Quality recommendation for {domain}.

Current content score: {content_score}/100
Average word count per page: {content_s.get('avg_word_count', 0)}
Thin content pages (under 300 words): {content_s.get('thin_content_pages', 0)}
Pages with video: {content_s.get('pages_with_video', 0)}
Average internal links per page: {content_s.get('avg_internal_links', 0)}

Write 2-3 specific content improvement recommendations. Explain how content quality directly impacts rankings and user trust."""

        results["content"] = _ask(content_prompt, max_tokens=300)

    # 7. Top priority action plan
    priority_prompt = f"""Create a prioritized 30-day action plan for {domain} based on this audit:

Overall score: {overall_score}/100 (Grade {grade})
Lowest scoring areas:
{chr(10).join([f'- {k}: {v.get("score", 0)}/100' for k, v in sorted(cat_scores.items(), key=lambda x: x[1].get("score", 0))[:4]])}

Write a clear Week 1, Week 2, Week 3-4 action plan with specific tasks.
Make it realistic for a small business owner to implement. Maximum 200 words."""

    results["action_plan"] = _ask(priority_prompt, max_tokens=300)

    return results
