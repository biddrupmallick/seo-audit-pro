"""
Generate plain-language written content for each PDF report section using Ollama.
All content is based strictly on data passed in — no fabrication.
"""
from typing import Dict, List, Optional
from analyzers.ollama_client import ask


def _ask(prompt: str, max_tokens: int = 150) -> str:
    return ask(prompt.strip(), max_tokens=max_tokens, temperature=0.3)


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting markers Ollama sometimes outputs."""
    import re
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # [text](url) → text
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    return text.strip()


def calculate_presence_score(
    website: str,
    rating: Optional[float],
    review_count: Optional[int],
    email: str,
    phone: str,
    socials: Dict[str, str],
) -> int:
    score = 0
    if website:                                     score += 20
    if review_count and int(review_count) >= 100:   score += 15
    elif review_count and int(review_count) >= 20:  score += 10
    if rating:
        r = float(rating)
        if r >= 4.5:   score += 15
        elif r >= 4.0: score += 10
        elif r >= 3.0: score += 5
    if email: score += 10
    if phone: score += 10
    active = sum(1 for v in socials.values() if v)
    score += min(active * 5, 20)
    return min(score, 100)


def generate_report_content(
    business_name: str,
    owner_name: str,
    rating: Optional[float],
    review_count: Optional[int],
    reviews_text: str,
    top_praise: str,
    top_complaints: str,
    website: str,
    phone: str,
    email: str,
    address: str,
    socials: Dict[str, str],
    competitors: List[Dict],
    presence_score: int,
    load_speed: Optional[str],
    mobile_friendly: Optional[bool],
) -> Dict[str, str]:
    """
    Generate all Ollama-written sections for the niche report.
    Returns a dict of section_key -> written text.
    """
    has_website      = bool(website)
    has_reviews_text = bool(reviews_text and reviews_text.strip())
    has_praise       = bool(top_praise)
    active_socials   = [p.capitalize() for p, url in socials.items() if url]
    missing_socials  = [p.capitalize() for p, url in socials.items() if not url]

    # Competitor summary string
    comp_summary = ""
    if competitors:
        comp_summary = ", ".join([
            f"{c.get('name','?')} ({c.get('rating','?')}★, {c.get('reviews','?')} reviews)"
            for c in competitors[:3]
        ])

    # Determine competitor position
    position = "unknown"
    if competitors and rating:
        comp_ratings = [float(c["rating"]) for c in competitors[:3] if c.get("rating")]
        if comp_ratings:
            avg = sum(comp_ratings) / len(comp_ratings)
            position = "ahead of" if float(rating) >= avg else "behind"

    # Issues list for pain points + action plan
    issues = []
    if not has_website:
        issues.append("no website")
    if not email:
        issues.append("no public email address")
    if not active_socials:
        issues.append("no social media presence")
    if review_count is not None and int(review_count) < 20:
        issues.append(f"only {review_count} reviews")
    if rating is not None and float(rating) < 4.0:
        issues.append(f"rating of {rating} stars")

    content: Dict[str, str] = {}

    # ── Cover: one sentence overall position ─────────────────────────────
    content["cover_summary"] = _ask(f"""
Write exactly ONE sentence summarising this business's online presence.
Be direct and specific. Plain language only. No jargon.

Business: {business_name}
Presence score: {presence_score}/100
Rating: {rating or 'no rating'} stars, {review_count or 0} reviews
Has website: {'yes' if has_website else 'no'}
Active on: {', '.join(active_socials) if active_socials else 'no social media'}

One sentence only:""")

    # ── Page 2: Visibility ────────────────────────────────────────────────
    content["visibility"] = _ask(f"""
Write 2 sentences for a business owner about how easy it is for customers to find them online.
Plain language only. No technical terms.

Business: {business_name}
Address on file: {'yes' if address else 'no'}
Phone on file: {'yes' if phone else 'no'}
Has website: {'yes' if has_website else 'no'}

2 sentences only:""")

    # ── Page 3: Reviews ───────────────────────────────────────────────────
    if has_reviews_text and has_praise:
        content["reviews"] = _ask(f"""
Write 2-3 sentences about this business's customer reviews for the owner.
Plain language. Positive tone. If there are complaints, frame them as opportunities.
Never embarrass the owner.

Business: {business_name}
Rating: {rating} stars from {review_count} reviews
What customers praise: {top_praise}
What customers complain about: {top_complaints or 'nothing significant'}

2-3 sentences only:""")
    elif rating:
        content["reviews"] = _ask(f"""
Write 2 sentences about this business's rating for the owner.
We have a rating but no detailed review text to analyse.
Plain language only.

Business: {business_name}
Rating: {rating} stars from {review_count} reviews

2 sentences only:""")
    else:
        content["reviews"] = _ask(f"""
Write 2 sentences telling this business owner they have no Google reviews yet.
Be encouraging. Frame it as an opportunity, not a failure.
Plain language only.

Business: {business_name}

2 sentences only:""")

    # ── Page 4: Competitors ───────────────────────────────────────────────
    content["competitors"] = _ask(f"""
Write 2-3 sentences comparing this business to its nearest competitors.
Plain language. Use real numbers.
If ahead — acknowledge it and show opportunity to grow further.
If behind — be encouraging and frame as opportunity to improve.

Business: {business_name}
Rating: {rating or '?'}★, {review_count or 0} reviews
Nearest competitors: {comp_summary or 'no competitor data found nearby'}
Position: {position} competitors

2-3 sentences only:""")

    # ── Page 5: Reachability ──────────────────────────────────────────────
    content["reachability"] = _ask(f"""
Write 2 sentences about how easy it is for customers to contact this business.
Plain language. Be specific about what is missing.

Business: {business_name}
Website: {'found' if has_website else 'missing'}
Phone: {'found' if phone else 'missing'}
Email: {'found' if email else 'missing'}
Social media: {', '.join(active_socials) if active_socials else 'none found'}

2 sentences only:""")

    # ── Page 6: Website (only if has website) ────────────────────────────
    if has_website:
        content["website"] = _ask(f"""
Write 2 sentences about this business's website for the owner.
Plain language only. No technical terms.
If slow — explain customers leave. If not mobile friendly — explain phone users can't use it.

Business: {business_name}
Load speed: {load_speed or 'not measured'}
Mobile friendly: {'yes' if mobile_friendly else 'no' if mobile_friendly is not None else 'not measured'}

2 sentences only:""")

    # ── Page 7: Pain points ───────────────────────────────────────────────
    content["pain_points"] = _strip_markdown(_ask(f"""
List 3-5 specific things that are costing this business customers right now.
Each on its own line starting with a dash (-).
Plain language. Business consequences only. No technical terms.
Base this ONLY on the data below. Do not invent issues.
Output ONLY the list items. No intro sentence.

Business: {business_name}
Known issues: {', '.join(issues) if issues else 'none major'}
Missing social platforms: {', '.join(missing_socials[:4]) if missing_socials else 'none'}
Competitors ahead: {'yes' if position == 'behind' else 'no'}

List only (3-5 items, each starting with -):""", max_tokens=220))

    # ── Page 8: Action plan ───────────────────────────────────────────────
    content["action_plan"] = _strip_markdown(_ask(f"""
Write exactly 3 priority actions for this business owner to improve their online presence.
Number them 1, 2, 3. Most impactful first. Each action on its own line.
Plain language. Specific and actionable. Each item 1-2 sentences max.
Output ONLY the 3 numbered items. No intro sentence. No extra text.

Business: {business_name}
Known issues: {', '.join(issues) if issues else 'none major'}
Missing social platforms: {', '.join(missing_socials[:3]) if missing_socials else 'none'}
Position vs competitors: {position}

3 numbered actions only:""", max_tokens=280))

    return content
