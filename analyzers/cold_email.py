from typing import Dict, Any, List

from analyzers.ollama_client import chat

OLLAMA_MODEL = "llama3.1"


def _top_issues(revenue_impact: Dict) -> List[Dict]:
    items = revenue_impact.get("items", [])
    return [i for i in items if i.get("severity") in ("critical", "warning")][:3]


def _build_context(
    domain: str,
    scores: Dict,
    revenue_impact: Dict,
    competitor: Dict,
    wayback: Dict,
    local_seo: Dict,
) -> str:
    overall  = scores.get("overall_score", 0)
    grade    = scores.get("grade", "?")
    cat_s    = scores.get("category_scores", {})

    def cs(cat): return int(cat_s.get(cat, {}).get("score", 0))

    issues = _top_issues(revenue_impact)
    ri_sum = revenue_impact.get("summary", {})

    lines = [
        f"DOMAIN: {domain}",
        f"OVERALL SCORE: {overall}/100 (Grade {grade})",
        f"MONTHLY REVENUE AT RISK: ${ri_sum.get('monthly_impact_low',0)}–${ri_sum.get('monthly_impact_high',0)}",
        "",
        "TOP ISSUES FOUND:",
    ]
    for i, issue in enumerate(issues, 1):
        lines.append(
            f"  {i}. {issue['headline']} "
            f"(${issue['monthly_impact_low']}–${issue['monthly_impact_high']}/mo impact)"
        )

    lines += [
        "",
        f"CATEGORY SCORES: Local SEO={cs('local_seo')}/100, "
        f"Conversion={cs('conversion')}/100, "
        f"On-Page={cs('onpage')}/100, "
        f"Technical={cs('technical')}/100",
    ]

    if competitor.get("available"):
        cmp = competitor.get("comparison", {})
        co_domain = competitor.get("competitor_domain", "")
        co_overall = cmp.get("competitor_overall", 0)
        losses = cmp.get("competitor_wins", [])
        lines += [
            "",
            f"COMPETITOR: {co_domain} scores {co_overall}/100 "
            f"(beats client in: {', '.join(losses[:3]) if losses else 'none'})",
        ]

    if wayback.get("available"):
        ins = wayback.get("insights", {})
        if ins.get("talking_point"):
            lines += ["", f"HISTORY INSIGHT: {ins['talking_point']}"]
        if ins.get("summary"):
            lines += [f"BUSINESS SUMMARY: {ins['summary'][:120]}"]

    if local_seo.get("has_nap_info"):
        lines.append("HAS LOCAL PRESENCE: Yes (phone/address found)")
    else:
        lines.append("HAS LOCAL PRESENCE: No NAP info detected")

    return "\n".join(lines)


def _parse_email(text: str) -> Dict[str, str]:
    result = {"subject": "", "body": ""}
    lines = text.strip().splitlines()
    body_lines = []
    in_body = False
    for line in lines:
        if line.startswith("SUBJECT:"):
            result["subject"] = line.replace("SUBJECT:", "").strip()
        elif line.startswith("BODY:"):
            in_body = True
            rest = line.replace("BODY:", "").strip()
            if rest:
                body_lines.append(rest)
        elif in_body:
            body_lines.append(line)
    result["body"] = "\n".join(body_lines).strip()
    return result


def _generate_email(context: str, style: str, instructions: str, max_tokens: int = 350) -> Dict[str, str]:
    prompt = f"""You are writing a cold outreach email on behalf of an SEO consultant who just ran a free audit on a prospect's website.

AUDIT DATA:
{context}

STYLE: {style}

INSTRUCTIONS:
{instructions}

The email must feel genuinely helpful, not salesy. Never use "I hope this email finds you well."
Always reference their SPECIFIC numbers from the audit — not generic statements.
Sign off as the consultant (use "— [Your Name]" as placeholder).

Output EXACTLY this format:
SUBJECT: [email subject line]
BODY:
[full email body, plain text, line breaks between paragraphs]"""

    try:
        return _parse_email(chat([{"role": "user", "content": prompt}], max_tokens=max_tokens, temperature=0.65))
    except Exception:
        return {"subject": "", "body": ""}


def generate_cold_emails(
    domain: str,
    scores: Dict[str, Any],
    revenue_impact: Dict[str, Any],
    competitor: Dict[str, Any],
    wayback: Dict[str, Any],
    local_seo: Dict[str, Any],
) -> Dict[str, Any]:

    context = _build_context(domain, scores, revenue_impact, competitor, wayback, local_seo)

    # Email 1 — Short & punchy (cold first touch)
    email_1 = _generate_email(
        context,
        style="Short and direct. 5–8 lines max. No fluff.",
        instructions=(
            "Lead with the single biggest issue and its dollar cost. "
            "One clear CTA: offer a free 15-min call to walk through the full report. "
            "No bullet points. Conversational tone. Short paragraphs."
        ),
        max_tokens=280,
    )

    # Email 2 — Detailed & professional (warm leads or LinkedIn connections)
    email_2 = _generate_email(
        context,
        style="Professional and detailed. 10–14 lines. Shows expertise.",
        instructions=(
            "Open with what you found on their site specifically. "
            "List 2–3 issues with their exact scores and dollar impact. "
            "If competitor data is available, mention one place the competitor is beating them. "
            "CTA: share the full PDF report and offer to discuss. "
            "Tone: trusted advisor, not salesperson."
        ),
        max_tokens=420,
    )

    # Email 3 — Follow-up (send 3–5 days after no reply)
    email_3 = _generate_email(
        context,
        style="Brief follow-up. 3–5 lines only. Casual and non-pushy.",
        instructions=(
            "Reference the first email briefly. "
            "Add one new specific data point they haven't heard yet (pick something not in email 1). "
            "End with a simple yes/no question to lower friction. "
            "No pressure, just value."
        ),
        max_tokens=180,
    )

    ri_sum = revenue_impact.get("summary", {})
    top    = _top_issues(revenue_impact)

    return {
        "domain":  domain,
        "context_summary": {
            "overall_score": scores.get("overall_score", 0),
            "grade":         scores.get("grade", "?"),
            "monthly_risk_low":  ri_sum.get("monthly_impact_low", 0),
            "monthly_risk_high": ri_sum.get("monthly_impact_high", 0),
            "top_issue": top[0]["headline"] if top else "",
        },
        "emails": [
            {
                "type":    "Short & Punchy",
                "use_for": "Cold first touch — email, LinkedIn DM",
                "icon":    "⚡",
                **email_1,
            },
            {
                "type":    "Professional & Detailed",
                "use_for": "Warm leads, referrals, LinkedIn connections",
                "icon":    "📋",
                **email_2,
            },
            {
                "type":    "Follow-Up",
                "use_for": "Send 3–5 days after no reply",
                "icon":    "🔁",
                **email_3,
            },
        ],
    }
