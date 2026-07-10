"""
Lead Scoring — ranks how valuable a prospect is for outreach.
Higher score = more pain + more opportunity = better lead.
"""
from typing import Dict, Any, List


def calculate_lead_score(
    scores: Dict[str, Any],
    technical: Dict[str, Any],
    onpage: Dict[str, Any],
    performance: Dict[str, Any],
    local_seo: Dict[str, Any],
    conversion: Dict[str, Any],
    revenue_impact: Dict[str, Any],
    total_pages: int,
    gbp: Dict[str, Any] = None,
    keywords: Dict[str, Any] = None,
) -> Dict[str, Any]:

    points = 0
    signals = []      # what's driving the score up
    talking_points = []  # best cold email hooks
    quick_wins = []   # easiest things to fix = easiest wins to promise

    overall = scores.get("overall_score", 0)
    cat = scores.get("category_scores", {})

    # ── 1. SEO Score Gap (30 pts) ──────────────────────────────────────────
    # Lower score = more pain = better prospect
    if overall < 30:
        points += 30
        signals.append(f"Critical SEO health ({overall}/100) — site needs urgent attention")
        talking_points.append(f"Their overall SEO score is only {overall}/100 — well below the industry average of 65")
    elif overall < 50:
        points += 22
        signals.append(f"Poor SEO health ({overall}/100)")
        talking_points.append(f"Their SEO score of {overall}/100 means they're leaving traffic on the table every day")
    elif overall < 65:
        points += 14
        signals.append(f"Below-average SEO ({overall}/100)")
        talking_points.append(f"With a score of {overall}/100, targeted fixes could move them into the top 30%")
    elif overall < 80:
        points += 6
        signals.append(f"Average SEO ({overall}/100) — moderate opportunity")
    else:
        signals.append(f"Good SEO ({overall}/100) — limited opportunity")

    # ── 2. Revenue Impact (25 pts) ─────────────────────────────────────────
    rev = revenue_impact or {}
    summary = rev.get("summary", {})
    monthly_low = summary.get("total_monthly_low", 0)
    monthly_high = summary.get("total_monthly_high", 0)

    if monthly_high >= 5000:
        points += 25
        signals.append(f"High revenue at risk: ${monthly_low:,}–${monthly_high:,}/mo")
        talking_points.append(f"Our audit found ${monthly_low:,}–${monthly_high:,}/month in estimated revenue leaks")
    elif monthly_high >= 2000:
        points += 18
        signals.append(f"Significant revenue at risk: ${monthly_low:,}–${monthly_high:,}/mo")
        talking_points.append(f"We identified ${monthly_low:,}–${monthly_high:,}/month in potential revenue being lost")
    elif monthly_high >= 500:
        points += 10
        signals.append(f"Moderate revenue at risk: ${monthly_low:,}–${monthly_high:,}/mo")
    else:
        points += 3

    # ── 3. Critical Issues (15 pts) ────────────────────────────────────────
    critical = scores.get("critical_issues", [])
    critical_count = len(critical)
    if critical_count >= 5:
        points += 15
        signals.append(f"{critical_count} critical issues found")
        talking_points.append(f"We found {critical_count} critical SEO issues — each one is costing them rankings")
    elif critical_count >= 3:
        points += 10
        signals.append(f"{critical_count} critical issues found")
    elif critical_count >= 1:
        points += 5

    # ── 4. Specific high-value gaps (20 pts) ───────────────────────────────
    gap_pts = 0
    gap_signals = []

    # Missing schema (easy win, high impact)
    schema_score = cat.get("schema", {}).get("score", 100)
    if schema_score < 40:
        gap_pts += 5
        gap_signals.append("no schema markup")
        quick_wins.append("Add schema markup — takes 1 hour, boosts CTR by up to 25%")

    # Technical issues (broken links, no HTTPS, etc.)
    tech_score = cat.get("technical", {}).get("score", 100)
    if tech_score < 50:
        gap_pts += 4
        gap_signals.append("major technical issues")
        quick_wins.append(f"Fix {len(technical.get('issues_4xx', []))} broken pages — hurting crawlability now")

    # No conversion optimization
    conv_score = cat.get("conversion", {}).get("score", 100)
    pages_no_cta = len(conversion.get("pages_missing_cta", []))
    if conv_score < 50 or pages_no_cta >= 5:
        gap_pts += 4
        gap_signals.append(f"{pages_no_cta} pages missing CTAs")
        quick_wins.append(f"Add CTAs to {pages_no_cta} pages — direct revenue fix, no SEO needed")

    # Slow performance
    perf_score = cat.get("performance", {}).get("score", 100)
    if perf_score < 50:
        gap_pts += 4
        gap_signals.append("slow page speed")
        quick_wins.append("Improve page speed — 53% of mobile users abandon pages that take 3+ seconds")

    # Local SEO missing
    local_score = cat.get("local_seo", {}).get("score", 100)
    if local_score < 50:
        gap_pts += 3
        gap_signals.append("weak local SEO")
        quick_wins.append("Fix local SEO signals — 72% of local searches result in a store visit within 5 miles")

    points += min(gap_pts, 20)
    if gap_signals:
        signals.append("Key gaps: " + ", ".join(gap_signals))

    # ── 5. GBP opportunity (5 pts) ─────────────────────────────────────────
    if gbp and gbp.get("available"):
        client = gbp.get("client", {})
        gbp_score = client.get("score", 100)
        rating = client.get("rating") or 0
        if gbp_score < 60:
            points += 5
            signals.append(f"GBP profile score only {gbp_score}/100")
            quick_wins.append("Optimise Google Business Profile — it's free and directly affects local search visibility")
        if rating and rating < 4.0:
            talking_points.append(f"Their Google rating is {rating}★ — we can help them build a review strategy to recover it")

    # ── 6. Keyword opportunity (5 pts) ─────────────────────────────────────
    if keywords:
        gap_kws = keywords.get("summary", {}).get("gap_keywords", 0)
        if gap_kws >= 10:
            points += 5
            signals.append(f"{gap_kws} keyword gaps found")
            talking_points.append(f"We found {gap_kws} keywords they rank for in body text but not in titles — easy ranking wins")
        elif gap_kws >= 5:
            points += 3

    # ── Classification ─────────────────────────────────────────────────────
    score = min(points, 100)

    if score >= 70:
        tier = "Hot Lead"
        tier_color = "#dc2626"
        tier_icon = "🔥"
        tier_desc = "High pain, high opportunity — prioritise for outreach this week"
    elif score >= 45:
        tier = "Warm Lead"
        tier_color = "#d97706"
        tier_icon = "⚡"
        tier_desc = "Clear opportunities — good prospect worth a personalised email"
    else:
        tier = "Nurture"
        tier_color = "#16a34a"
        tier_icon = "🌱"
        tier_desc = "Already performing well — low urgency, follow up in 3–6 months"

    # Top 3 talking points (deduplicate, pick best)
    top_talking_points = talking_points[:3]
    top_quick_wins = quick_wins[:3]

    return {
        "score": score,
        "tier": tier,
        "tier_color": tier_color,
        "tier_icon": tier_icon,
        "tier_desc": tier_desc,
        "signals": signals,
        "talking_points": top_talking_points,
        "quick_wins": top_quick_wins,
        "monthly_revenue_at_risk_low": monthly_low,
        "monthly_revenue_at_risk_high": monthly_high,
        "critical_issues_count": critical_count,
        "overall_seo_score": overall,
    }
