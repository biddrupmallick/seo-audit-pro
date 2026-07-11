import asyncio
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from analyzers.ollama_client import chat

OLLAMA_MODEL = "llama3.1"
COMPETITOR_MAX_PAGES = 40   # keep competitor crawl fast


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def _score(data: Dict, key: str = "score") -> int:
    return int(data.get(key, 0))


def _cat_score(scores: Dict, cat: str) -> int:
    return int(scores.get("category_scores", {}).get(cat, {}).get("score", 0))


def _compare_scores(client_scores: Dict, comp_scores: Dict) -> Dict[str, Any]:
    categories = [
        "technical", "onpage", "schema", "aeo",
        "geo", "performance", "local_seo", "conversion", "content",
    ]
    comparison: Dict[str, Any] = {}
    client_wins, comp_wins = [], []

    for cat in categories:
        cs = _cat_score(client_scores, cat)
        cc = _cat_score(comp_scores, cat)
        diff = cs - cc
        if diff > 5:
            winner = "client"
            client_wins.append(cat)
        elif diff < -5:
            winner = "competitor"
            comp_wins.append(cat)
        else:
            winner = "tie"
        comparison[cat] = {
            "client":     cs,
            "competitor": cc,
            "diff":       diff,
            "winner":     winner,
        }

    return {
        "by_category":   comparison,
        "client_wins":   client_wins,
        "competitor_wins": comp_wins,
        "client_overall":     int(client_scores.get("overall_score", 0)),
        "competitor_overall": int(comp_scores.get("overall_score", 0)),
    }


def _ai_comparison(
    client_domain: str,
    comp_domain: str,
    comparison: Dict,
    client_scores: Dict,
    comp_scores: Dict,
    client_local: Dict,
    comp_local: Dict,
    client_conv: Dict,
    comp_conv: Dict,
) -> Dict[str, str]:
    by_cat = comparison["by_category"]
    weak   = [c for c, v in by_cat.items() if v["winner"] == "competitor"]
    strong = [c for c, v in by_cat.items() if v["winner"] == "client"]

    cl_cta   = client_conv.get("summary", {}).get("pages_with_cta", 0)
    co_cta   = comp_conv.get("summary", {}).get("pages_with_cta", 0)
    cl_local = client_local.get("has_local_business_schema", False)
    co_local = comp_local.get("has_local_business_schema", False)

    prompt = f"""SEO competitive analysis.

CLIENT: {client_domain} — Overall score: {comparison['client_overall']}/100
COMPETITOR: {comp_domain} — Overall score: {comparison['competitor_overall']}/100

WHERE COMPETITOR BEATS CLIENT: {', '.join(weak) if weak else 'none'}
WHERE CLIENT BEATS COMPETITOR: {', '.join(strong) if strong else 'none'}

KEY DETAILS:
- Client CTA pages: {cl_cta} | Competitor CTA pages: {co_cta}
- Client LocalBusiness schema: {cl_local} | Competitor: {co_local}
- Client grade: {client_scores.get('grade','?')} | Competitor grade: {comp_scores.get('grade','?')}

Score breakdown:
{chr(10).join([f"  {cat}: client={v['client']} competitor={v['competitor']} ({v['winner']} wins)" for cat, v in by_cat.items()])}

Output EXACTLY this format (4 lines):
HEADLINE: [One punchy sentence: who is winning and why]
THEIR_EDGE: [What the competitor is doing better — be specific, reference categories]
YOUR_EDGE: [What the client is doing better — if nothing, say what they COULD own]
STEAL: [The single quickest thing to copy from the competitor this week]"""

    try:
        text = chat([{"role": "user", "content": prompt}], max_tokens=200, temperature=0.5)
    except Exception:
        return {}

    result: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        for key in ("HEADLINE", "THEIR_EDGE", "YOUR_EDGE", "STEAL"):
            if line.startswith(f"{key}:"):
                result[key.lower()] = line[len(key) + 1:].strip()
    return result


async def analyze_competitor(
    competitor_url: str,
    client_domain: str,
    client_scores: Dict[str, Any],
    client_technical: Dict[str, Any],
    client_onpage: Dict[str, Any],
    client_schema: Dict[str, Any],
    client_aeo: Dict[str, Any],
    client_geo: Dict[str, Any],
    client_performance: Dict[str, Any],
    client_images: Dict[str, Any],
    client_local_seo: Dict[str, Any],
    client_conversion: Dict[str, Any],
    client_content: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Crawl competitor site and produce a side-by-side comparison with the client.
    Returns empty dict gracefully on failure.
    """
    from crawler.spider import Spider
    from analyzers.technical   import analyze_technical
    from analyzers.onpage      import analyze_onpage
    from analyzers.schema      import analyze_schema
    from analyzers.aeo         import analyze_aeo
    from analyzers.geo         import analyze_geo
    from analyzers.performance import analyze_performance
    from analyzers.images      import analyze_images
    from analyzers.local_seo   import analyze_local_seo
    from analyzers.conversion  import analyze_conversion
    from analyzers.content     import analyze_content
    from scoring.scorer        import calculate_scores

    comp_domain = _domain(competitor_url)

    try:
        spider = Spider(competitor_url, max_pages=COMPETITOR_MAX_PAGES)
        pages  = await spider.crawl()
    except Exception as e:
        return {"available": False, "error": f"Could not crawl competitor: {e}"}

    if not pages:
        return {"available": False, "error": "No pages crawled from competitor site."}

    # Run all analyzers (same as client)
    try:
        comp_tech  = await asyncio.to_thread(analyze_technical,  pages)
        comp_op    = await asyncio.to_thread(analyze_onpage,     pages)
        comp_sch   = await asyncio.to_thread(analyze_schema,     pages)
        comp_aeo   = await asyncio.to_thread(analyze_aeo,        pages)
        comp_geo   = await asyncio.to_thread(analyze_geo,        pages)
        comp_perf  = await asyncio.to_thread(analyze_performance, pages)
        comp_img   = await asyncio.to_thread(analyze_images,     pages)
        comp_local = await asyncio.to_thread(analyze_local_seo,  pages)
        comp_conv  = await asyncio.to_thread(analyze_conversion,  pages)
        comp_cont  = await asyncio.to_thread(analyze_content,    pages)
        comp_scores = calculate_scores(
            comp_tech, comp_op, comp_sch, comp_aeo, comp_geo,
            comp_perf, comp_img, comp_local, comp_conv, comp_cont,
        )
    except Exception as e:
        return {"available": False, "error": f"Analysis failed: {e}"}

    comparison = _compare_scores(client_scores, comp_scores)
    insights   = _ai_comparison(
        client_domain, comp_domain, comparison,
        client_scores, comp_scores,
        client_local_seo, comp_local,
        client_conversion, comp_conv,
    )

    return {
        "available":        True,
        "competitor_url":   competitor_url,
        "competitor_domain": comp_domain,
        "pages_crawled":    len(pages),
        "competitor_scores": {
            "overall_score": comp_scores.get("overall_score", 0),
            "grade":         comp_scores.get("grade", "?"),
            "grade_color":   comp_scores.get("grade_color", "#888"),
            "category_scores": {
                cat: {
                    "score": data.get("score", 0),
                    "grade": data.get("grade", "?"),
                    "grade_color": data.get("grade_color", "#888"),
                }
                for cat, data in comp_scores.get("category_scores", {}).items()
            },
        },
        "comparison": comparison,
        "insights":   insights,
        "competitor_summary": {
            "technical":   comp_tech.get("summary", {}),
            "onpage":      comp_op.get("summary", {}),
            "local_seo":   comp_local.get("summary", {}),
            "conversion":  comp_conv.get("summary", {}),
            "content":     comp_cont.get("summary", {}),
            "performance": comp_perf.get("summary", {}),
        },
    }
