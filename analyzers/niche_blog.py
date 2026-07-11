"""
Generate full blog posts from niche review analysis using Ollama.
Three formats: research post, case study, tips post.
"""
from typing import Dict, Any

from analyzers.ollama_client import ask


def _ollama(prompt: str, max_tokens: int = 1500) -> str:
    return ask(prompt, max_tokens=max_tokens, temperature=0.6)


def _build_context(category: str, state: str, biz_count: int,
                   avg_rating: float, avg_reviews: int,
                   analysis: Dict) -> str:
    a = analysis
    return f"""
Niche: {category}
Location: {state or 'USA'}
Businesses analysed: {biz_count}
Average rating: {avg_rating}★
Average review count: {avg_reviews}

Key findings from {biz_count} businesses:
- Top praise themes: {a.get('TOP_PRAISE', 'not available')}
- Top complaints: {a.get('TOP_COMPLAINTS', 'not available')}
- Staff patterns: {a.get('STAFF_PATTERNS', 'not available')}
- Most mentioned services: {a.get('SERVICE_KEYWORDS', 'not available')}
- What separates top from average: {a.get('DIFFERENTIATORS', 'not available')}
- Customer language: {a.get('CUSTOMER_LANGUAGE', 'not available')}
- Key insight: {a.get('KEY_INSIGHT', 'not available')}
""".strip()


def generate_blog_posts(
    category: str,
    state: str,
    biz_count: int,
    avg_rating: float,
    avg_reviews: int,
    analysis: Dict,
) -> Dict[str, Any]:
    """Generate 3 blog post formats. Returns dict with title + content for each."""
    ctx = _build_context(category, state, biz_count, avg_rating, avg_reviews, analysis)
    loc = f"in {state}" if state else "across the US"

    # ── Format 1: Research / Data Post ──────────────────────────────────────
    research = _ollama(f"""You are an expert content writer for a local SEO agency.

Write a compelling, data-driven blog post using this research:
{ctx}

Requirements:
- Title must start with "We Analysed" and include the number {biz_count} and location
- 600-800 words
- Structure: Intro → 4-5 key findings (each with a subheading) → Conclusion with CTA
- Use specific numbers from the data (ratings, review counts, percentages)
- Write in first-person plural ("We found...", "Our research shows...")
- End with a call to action for business owners to get a free audit
- Do NOT use placeholder text — write the full post

Write the complete blog post now:""", max_tokens=1200)

    # ── Format 2: Case Study ────────────────────────────────────────────────
    case_study = _ollama(f"""You are an expert content writer for a local SEO agency.

Write a case study blog post using this research:
{ctx}

Requirements:
- Title about why {category} businesses {loc} lose customers to nearby competitors
- 500-700 words
- Structure: The problem → The data → 3 specific patterns we found → What winning businesses do differently → Action steps
- Focus on the competitive/proximity angle — businesses losing to competitors nearby
- Include specific stats from the data
- End with a free audit CTA
- Write the complete post, no placeholders

Write the complete case study now:""", max_tokens=1100)

    # ── Format 3: Tips / Listicle ───────────────────────────────────────────
    tips = _ollama(f"""You are an expert content writer for a local SEO agency.

Write a tips listicle blog post using this research:
{ctx}

Requirements:
- Title: "X Things Every 5-Star {category} Does (Based on {biz_count} Real Customer Reviews)"
  where X is 5, 6, or 7
- 400-600 words
- Format: Short intro → numbered list (each tip has a bold title + 2-3 sentences) → short outro with CTA
- Each tip must be directly backed by the review data
- Use real customer language/quotes where possible
- Easy to skim, share on social media
- Write the complete post, no placeholders

Write the complete listicle now:""", max_tokens=900)

    return {
        "research_post": {
            "format": "Research / Data Post",
            "icon": "📊",
            "content": research,
            "word_count": len(research.split()),
        },
        "case_study": {
            "format": "Case Study",
            "icon": "🔍",
            "content": case_study,
            "word_count": len(case_study.split()),
        },
        "tips_post": {
            "format": "Tips / Listicle",
            "icon": "✅",
            "content": tips,
            "word_count": len(tips.split()),
        },
    }
