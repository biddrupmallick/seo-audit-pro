from typing import Dict, Any, List

# Conservative industry benchmarks used for all estimates
_BENCHMARKS = {
    "monthly_visitors":        1000,   # small business baseline
    "mobile_share":            0.63,   # 63% of web traffic is mobile (Statista 2024)
    "avg_lead_value":          150,    # USD per lead (conservative)
    "base_conversion_rate":    0.025,  # 2.5% baseline
    "mobile_abandon_3s":       0.53,   # 53% abandon after 3s (Google)
    "cta_lift":                0.22,   # 22% more conversions with strong CTA
    "schema_ctr_lift":         0.25,   # 25% higher CTR with rich results
    "meta_desc_ctr_lift":      0.058,  # 5.8% CTR drop without meta desc
    "local_search_store_visit": 0.72,  # 72% of local searchers visit within 5 miles
    "broken_page_return_rate": 0.12,   # only 12% return after hitting a 4xx
    "thin_content_rank_chance": 0.08,  # 8% chance thin content ranks page 1
    "load_time_conversion_drop": 0.07, # 7% conversion drop per extra second
}


def _severity(monthly_low: float, monthly_high: float) -> str:
    mid = (monthly_low + monthly_high) / 2
    if mid >= 800:
        return "critical"
    elif mid >= 300:
        return "warning"
    return "low"


def calculate_revenue_impact(
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

    B = _BENCHMARKS
    V = B["monthly_visitors"]
    LV = B["avg_lead_value"]
    CR = B["base_conversion_rate"]
    items: List[Dict[str, Any]] = []

    tech_s  = technical.get("summary", {})
    op_s    = onpage.get("summary", {})
    perf_s  = performance.get("summary", {})
    conv_s  = conversion.get("summary", {})
    cont_s  = content.get("summary", {})
    schema_s = schema.get("summary", {})

    # ── 1. Slow Page Load ────────────────────────────────────────────────────
    avg_rt = perf_s.get("avg_response_time", 0)
    slow_pages = perf_s.get("slow_pages", 0)
    if avg_rt > 1.5:
        extra_seconds = max(0, avg_rt - 1.0)
        mobile_visitors = V * B["mobile_share"]
        if avg_rt >= 3.0:
            abandoned = mobile_visitors * B["mobile_abandon_3s"]
            conv_drop = extra_seconds * B["load_time_conversion_drop"]
            low  = int(abandoned * CR * LV * 0.5)
            high = int(abandoned * CR * LV * 1.2 + V * conv_drop * LV)
            headline = f"Avg {avg_rt}s load time is killing mobile conversions"
            detail   = (
                f"53% of mobile visitors abandon pages that take over 3 seconds. "
                f"With {int(mobile_visitors):,} estimated monthly mobile visitors, "
                f"you're losing ~{int(abandoned):,} of them before they even see your offer."
            )
        else:
            conv_drop = extra_seconds * B["load_time_conversion_drop"]
            low  = int(V * conv_drop * LV * 0.4)
            high = int(V * conv_drop * LV * 0.9)
            headline = f"Avg {avg_rt}s load time is reducing your conversion rate"
            detail   = (
                f"Every extra second of load time reduces conversions by ~7%. "
                f"Cutting load time to under 1s could recover {int(conv_drop * 100)}% "
                f"of lost conversions each month."
            )
        items.append({
            "icon": "⚡",
            "category": "Performance",
            "headline": headline,
            "detail": detail,
            "benchmark": "Google: 53% of mobile users leave if a page takes >3s to load",
            "monthly_impact_low": low,
            "monthly_impact_high": high,
            "severity": _severity(low, high),
            "fix": "Enable server caching, compress images, use a CDN",
            "fix_time": "1–2 weeks",
        })

    # ── 2. Pages Missing CTAs ────────────────────────────────────────────────
    pages_missing_cta = total_pages - conv_s.get("pages_with_cta", 0)
    if pages_missing_cta > 0:
        ratio = pages_missing_cta / max(total_pages, 1)
        lost_leads = V * ratio * B["cta_lift"] * CR
        low  = int(lost_leads * LV * 0.5)
        high = int(lost_leads * LV * 1.5)
        items.append({
            "icon": "🎯",
            "category": "Conversion",
            "headline": f"{pages_missing_cta} pages have no CTA — visitors leave with nowhere to go",
            "detail": (
                f"{pages_missing_cta} of your {total_pages} pages have no call-to-action. "
                f"Pages with strong CTAs convert up to 22% more visitors. "
                f"Every month without them is revenue you'll never recover."
            ),
            "benchmark": "HubSpot: personalized CTAs convert 202% better than generic ones",
            "monthly_impact_low": low,
            "monthly_impact_high": high,
            "severity": _severity(low, high),
            "fix": "Add one clear CTA per page (Book a Call, Get a Quote, Download, etc.)",
            "fix_time": "2–4 hours",
        })

    # ── 3. Broken Pages (4xx) ────────────────────────────────────────────────
    broken = tech_s.get("broken_pages", 0)
    if broken > 0:
        lost_visitors = V * (broken / max(total_pages, 1)) * (1 - B["broken_page_return_rate"])
        low  = int(lost_visitors * CR * LV * 0.5)
        high = int(lost_visitors * CR * LV * 1.2)
        items.append({
            "icon": "🔴",
            "category": "Technical SEO",
            "headline": f"{broken} broken pages are sending visitors to dead ends",
            "detail": (
                f"88% of users won't return to a website after a bad experience. "
                f"Only 12% of visitors who hit a broken page come back. "
                f"Each broken page also wastes Google's crawl budget."
            ),
            "benchmark": "88% of online consumers are less likely to return after a bad experience (Gomez)",
            "monthly_impact_low": low,
            "monthly_impact_high": high,
            "severity": _severity(low, high),
            "fix": "Set up 301 redirects for all 4xx pages to the closest relevant page",
            "fix_time": "1–2 hours",
        })

    # ── 4. Missing Meta Descriptions ─────────────────────────────────────────
    missing_meta = op_s.get("missing_meta_description", 0)
    if missing_meta > 0:
        ratio = missing_meta / max(total_pages, 1)
        ctr_loss = ratio * B["meta_desc_ctr_lift"]
        lost_clicks = V * ctr_loss
        low  = int(lost_clicks * CR * LV * 0.4)
        high = int(lost_clicks * CR * LV * 1.0)
        items.append({
            "icon": "📝",
            "category": "On-Page SEO",
            "headline": f"{missing_meta} pages missing meta descriptions — lower click-through from Google",
            "detail": (
                f"Without meta descriptions, Google writes its own — often poorly. "
                f"Well-written meta descriptions improve click-through rate by ~5.8%. "
                f"On {missing_meta} pages, that's real traffic you're not getting."
            ),
            "benchmark": "Portent: meta descriptions improve CTR by 5.8% on average",
            "monthly_impact_low": low,
            "monthly_impact_high": high,
            "severity": _severity(low, high),
            "fix": "Write a unique 120–160 character meta description for each page",
            "fix_time": "2–4 hours",
        })

    # ── 5. Schema Markup Missing ─────────────────────────────────────────────
    pages_no_schema = schema_s.get("pages_without_schema", 0)
    if pages_no_schema > 0:
        ctr_lift_lost = B["schema_ctr_lift"] * (pages_no_schema / max(total_pages, 1))
        lost_clicks = V * ctr_lift_lost
        low  = int(lost_clicks * CR * LV * 0.4)
        high = int(lost_clicks * CR * LV * 1.0)
        items.append({
            "icon": "🔗",
            "category": "Schema Markup",
            "headline": f"{pages_no_schema} pages lack schema — missing rich results in Google",
            "detail": (
                f"Rich results (star ratings, FAQs, breadcrumbs) appear only on pages with schema. "
                f"They get up to 25% higher click-through rates than plain listings. "
                f"Your competitors with schema are visually dominating your shared keywords."
            ),
            "benchmark": "Google: rich results get up to 25% more clicks than standard listings",
            "monthly_impact_low": low,
            "monthly_impact_high": high,
            "severity": _severity(low, high),
            "fix": "Add Organization, BreadcrumbList, and FAQPage schema to key pages",
            "fix_time": "3–5 hours",
        })

    # ── 6. Local SEO Gaps ────────────────────────────────────────────────────
    missing_local = local_seo.get("missing_local_signals", [])
    has_maps    = local_seo.get("has_google_maps", False)
    has_schema  = local_seo.get("has_local_business_schema", False)
    has_nap     = local_seo.get("has_nap_info", False)
    local_score = scores.get("category_scores", {}).get("local_seo", {}).get("score", 100)

    if local_score < 70 or len(missing_local) >= 2:
        local_visitors = V * B["local_search_store_visit"]
        low  = int(local_visitors * CR * LV * 0.4)
        high = int(local_visitors * CR * LV * 1.2)
        missing_str = ", ".join(missing_local[:3]) if missing_local else "key local signals"
        items.append({
            "icon": "📍",
            "category": "Local SEO",
            "headline": f"Missing {missing_str} — invisible to local buyers",
            "detail": (
                f"72% of consumers who do a local search visit a business within 5 miles. "
                f"Without {'Google Maps embed, ' if not has_maps else ''}"
                f"{'LocalBusiness schema, ' if not has_schema else ''}"
                f"{'NAP info, ' if not has_nap else ''}"
                f"your business doesn't show up when nearby customers are ready to buy."
            ),
            "benchmark": "Google: 72% of local searchers visit a store within 5 miles of their search",
            "monthly_impact_low": low,
            "monthly_impact_high": high,
            "severity": _severity(low, high),
            "fix": "Add LocalBusiness schema, embed Google Maps, and add consistent NAP on every page",
            "fix_time": "2–3 hours",
        })

    # ── 7. Thin Content Pages ────────────────────────────────────────────────
    thin_pages = cont_s.get("thin_content_pages", 0)
    if thin_pages > 0:
        rank_miss = thin_pages * (1 - B["thin_content_rank_chance"])
        low  = int(rank_miss * 20 * CR * LV * 0.3)
        high = int(rank_miss * 50 * CR * LV * 0.8)
        items.append({
            "icon": "✍️",
            "category": "Content Quality",
            "headline": f"{thin_pages} thin content pages that Google won't rank",
            "detail": (
                f"Pages with under 300 words rarely rank on page 1. "
                f"Each thin page is a missed ranking opportunity — "
                f"topics your customers are searching for that you could own but don't."
            ),
            "benchmark": "Backlinko: average page 1 result has 1,447 words",
            "monthly_impact_low": low,
            "monthly_impact_high": high,
            "severity": _severity(low, high),
            "fix": "Expand each thin page to 600+ words with relevant headings, FAQs, and examples",
            "fix_time": "1–2 hrs per page",
        })

    # ── 8. No Trust Signals ──────────────────────────────────────────────────
    trust_pages = conv_s.get("pages_with_trust_signals", 0)
    if trust_pages < (total_pages * 0.3):
        low  = int(V * 0.05 * CR * LV * 0.5)
        high = int(V * 0.15 * CR * LV * 1.2)
        items.append({
            "icon": "🛡️",
            "category": "Conversion",
            "headline": f"Only {trust_pages} pages have trust signals — visitors don't feel safe buying",
            "detail": (
                f"Trust signals (testimonials, certifications, guarantees, reviews) "
                f"directly impact whether a visitor becomes a customer. "
                f"Without them, visitors choose your competitor who looks more credible."
            ),
            "benchmark": "Nielsen: 92% of consumers trust peer recommendations over brand advertising",
            "monthly_impact_low": low,
            "monthly_impact_high": high,
            "severity": _severity(low, high),
            "fix": "Add client logos, testimonials, or a guarantee statement to key pages",
            "fix_time": "2–4 hours",
        })

    # ── Sort by severity ─────────────────────────────────────────────────────
    order = {"critical": 0, "warning": 1, "low": 2}
    items.sort(key=lambda x: order.get(x["severity"], 3))

    total_low  = sum(i["monthly_impact_low"] for i in items)
    total_high = sum(i["monthly_impact_high"] for i in items)

    # Opportunity score: how much revenue is being left on table (0-100)
    max_possible = len(items) * 1000
    opportunity_score = min(100, int((total_high / max(max_possible, 1)) * 100)) if items else 0

    return {
        "items": items,
        "summary": {
            "total_issues": len(items),
            "monthly_impact_low":  total_low,
            "monthly_impact_high": total_high,
            "opportunity_score":   opportunity_score,
            "critical_count": sum(1 for i in items if i["severity"] == "critical"),
            "warning_count":  sum(1 for i in items if i["severity"] == "warning"),
        },
    }
