import re
from collections import Counter, defaultdict
from typing import List, Dict, Any

# Common English stopwords — no external download needed
STOPWORDS = {
    "a","about","above","after","again","against","all","am","an","and","any",
    "are","aren't","as","at","be","because","been","before","being","below",
    "between","both","but","by","can","can't","cannot","could","couldn't","did",
    "didn't","do","does","doesn't","doing","don't","down","during","each","few",
    "for","from","further","get","got","had","hadn't","has","hasn't","have",
    "haven't","having","he","he'd","he'll","he's","her","here","here's","hers",
    "herself","him","himself","his","how","how's","i","i'd","i'll","i'm","i've",
    "if","in","into","is","isn't","it","it's","its","itself","let's","me","more",
    "most","mustn't","my","myself","no","nor","not","of","off","on","once","only",
    "or","other","ought","our","ours","ourselves","out","over","own","same",
    "shan't","she","she'd","she'll","she's","should","shouldn't","so","some",
    "such","than","that","that's","the","their","theirs","them","themselves",
    "then","there","there's","these","they","they'd","they'll","they're",
    "they've","this","those","through","to","too","under","until","up","very",
    "was","wasn't","we","we'd","we'll","we're","we've","were","weren't","what",
    "what's","when","when's","where","where's","which","while","who","who's",
    "whom","why","why's","will","with","won't","would","wouldn't","you","you'd",
    "you'll","you're","you've","your","yours","yourself","yourselves",
    # web noise
    "click","here","read","more","learn","back","next","prev","home","menu",
    "search","contact","page","site","website","www","http","https","com","org",
    "net","html","css","js","cookie","privacy","policy","terms","copyright",
    "rights","reserved","skip","content","navigation","footer","header","main",
    "nav","ul","li","div","span","img","alt","href","src","width","height",
    "style","class","id","type","value","name","action","method","form",
    "button","input","select","option","label","table","tr","td","th",
    "1","2","3","4","5","6","7","8","9","0","use","used","using","new","also",
    "just","like","well","good","best","great","get","make","way","time",
    "need","know","want","see","look","go","come","take","give","find","work",
}


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^\w\s\-']", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def _tokenize(text: str) -> List[str]:
    return [w for w in re.split(r"[\s\-]+", text) if len(w) > 2 and w not in STOPWORDS and not w.isdigit()]


def _ngrams(tokens: List[str], n: int) -> List[str]:
    return [" ".join(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


def analyze_keyword_opportunities(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not pages:
        return {"score": 0, "summary": {}, "opportunities": [], "quick_wins": [], "top_keywords": []}

    # Per-keyword data: {kw: {freq, title_count, h1_count, h2_count, body_count, pages}}
    kw_data: Dict[str, Dict] = defaultdict(lambda: {
        "freq": 0, "title_count": 0, "h1_count": 0,
        "h2_count": 0, "body_count": 0, "pages": set()
    })

    for page in pages:
        # Support both CrawledPage dataclass and plain dict
        if hasattr(page, "url"):
            url = page.url or ""
            title = _clean_text(getattr(page, "title", "") or "")
            h1s = " ".join(getattr(page, "h1s", []) or [])
            h2s = " ".join(getattr(page, "h2s", []) or [])
            body = _clean_text(getattr(page, "text_content", "") or getattr(page, "body_text", "") or "")
        else:
            url = page.get("url", "")
            title = _clean_text(page.get("title", "") or "")
            h1s = " ".join(page.get("h1s", []) or [])
            h2s = " ".join(page.get("h2s", []) or [])
            body = _clean_text(page.get("text_content", "") or page.get("body_text", "") or "")

        title_tokens = _tokenize(title)
        h1_tokens = _tokenize(_clean_text(h1s))
        h2_tokens = _tokenize(_clean_text(h2s))
        body_tokens = _tokenize(body)

        def _add(tokens, field, weight=1):
            seen = set()
            for n in (1, 2, 3):
                for kw in _ngrams(tokens, n):
                    if len(kw) < 4:
                        continue
                    if kw not in seen:
                        kw_data[kw]["freq"] += weight
                        kw_data[kw][field] += 1
                        kw_data[kw]["pages"].add(url)
                        seen.add(kw)

        _add(title_tokens, "title_count", weight=5)
        _add(h1_tokens, "h1_count", weight=4)
        _add(h2_tokens, "h2_count", weight=2)
        _add(body_tokens, "body_count", weight=1)

    # Score each keyword
    scored = []
    for kw, d in kw_data.items():
        # Skip extremely rare (only 1 body mention, no heading presence)
        if d["freq"] < 2:
            continue
        # Prefer multi-word phrases and penalise very long ones
        word_count = len(kw.split())
        if word_count > 5:
            continue

        score = d["freq"]
        in_title = d["title_count"] > 0
        in_h1 = d["h1_count"] > 0
        gap = d["body_count"] > 0 and not in_title and not in_h1

        scored.append({
            "keyword": kw,
            "word_count": word_count,
            "freq": d["freq"],
            "in_title": in_title,
            "in_h1": in_h1,
            "in_h2": d["h2_count"] > 0,
            "body_count": d["body_count"],
            "page_count": len(d["pages"]),
            "is_gap": gap,
            "score": score,
        })

    scored.sort(key=lambda x: (-x["score"], -x["word_count"]))

    top_keywords = scored[:30]
    opportunities = [k for k in scored if k["is_gap"]][:20]
    quick_wins = [k for k in scored if k["in_h2"] and not k["in_title"] and not k["in_h1"]][:10]

    # Scoring: penalise if many keywords are gaps (missed optimisation)
    total_kws = len(scored)
    gap_ratio = len([k for k in scored if k["is_gap"]]) / max(total_kws, 1)
    raw_score = max(0, 100 - int(gap_ratio * 80))

    summary = {
        "total_keywords_found": total_kws,
        "gap_keywords": len(opportunities),
        "quick_win_keywords": len(quick_wins),
        "gap_ratio_pct": round(gap_ratio * 100, 1),
        "top_keyword": top_keywords[0]["keyword"] if top_keywords else "",
    }

    return {
        "score": raw_score,
        "summary": summary,
        "opportunities": opportunities,
        "quick_wins": quick_wins,
        "top_keywords": top_keywords,
    }
