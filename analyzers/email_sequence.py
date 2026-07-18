"""
6-email follow-up sequence generator.

Two paths:
  - has_website=True  → SEO / PPC track (fix what's broken)
  - has_website=False → Website build + SEO track (start from scratch)

All 6 emails are written by Ollama with a thread through-line.
Emails 2-6 use "Re: {original_subject}" as subject (reply threading).
"""
import re
from typing import Dict, List

from analyzers.ollama_client import ask


def _ollama(prompt: str, max_tokens: int = 180) -> str:
    return ask(prompt.strip(), max_tokens=max_tokens, temperature=0.75)


def _clean(text: str, max_sentences: int = 2) -> str:
    """Strip markdown and enforce sentence limit."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*',   r'\1', text)
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    result = " ".join(sentences[:max_sentences])
    if result and result[-1] not in ".!?":
        result += "."
    return result


# ── Sequence metadata ─────────────────────────────────────────────────────────

SEQUENCE_META = [
    {"index": 1, "day": 0,  "label": "Initial Outreach"},
    {"index": 2, "day": 3,  "label": "Follow-Up #1 — Quick Check-In"},
    {"index": 3, "day": 7,  "label": "Follow-Up #2 — Free Value"},
    {"index": 4, "day": 14, "label": "Follow-Up #3 — PPC Angle"},
    {"index": 5, "day": 21, "label": "Follow-Up #4 — Soft Urgency"},
    {"index": 6, "day": 30, "label": "Follow-Up #5 — Breakup Email"},
]


def generate_email_sequence(
    biz: Dict,
    email_1_subject: str,
    email_1_body: str,
    has_website: bool,
) -> List[Dict]:
    """
    Returns a list of 6 dicts, each with:
      index, day, label, subject, body
    """
    name      = biz.get("name", "your business")
    owner     = (biz.get("owner_name") or "").split()[0] or "there"
    rating    = biz.get("rating") or ""
    reviews   = biz.get("reviews") or 0
    category  = biz.get("category") or "local business"
    state     = biz.get("state") or ""
    comps     = biz.get("nearest_competitors") or []
    comp      = comps[0] if comps else {}
    comp_name = (comp.get("name") or "a nearby competitor").split("|")[0].strip()[:40]
    comp_rev  = comp.get("reviews") or comp.get("review_count") or "more"

    # Services we sell — woven into prompts
    services_with_web    = "SEO, PPC advertising, and website management"
    services_without_web = "website development, SEO, and PPC advertising"
    services = services_with_web if has_website else services_without_web

    re_subject = f"Re: {email_1_subject}"
    results: List[Dict] = []

    # ── Email 1: already written, just package it ─────────────────────────────
    results.append({
        **SEQUENCE_META[0],
        "subject": email_1_subject,
        "body":    email_1_body,
    })

    # ── Email 2 (Day 3): quick check-in, different data point ────────────────
    if has_website:
        e2_prompt = f"""Write a 2-sentence cold email follow-up for a {category} owner named {owner}.

Context: I sent them an email 3 days ago (below) and got no reply.
My previous email: "{email_1_body}"

This follow-up should:
- Open with "Just wanted to make sure this landed, {owner}."
- Mention that {comp_name} has {comp_rev} Google reviews vs {name}'s {reviews} and that this gap affects Google rankings
- End with one soft question inviting a reply
- Subtly mention that I offer {services}

2 sentences only. No subject line. No greeting. Start directly with the sentence."""
    else:
        e2_prompt = f"""Write a 2-sentence cold email follow-up for a {category} owner named {owner}.

Context: I sent them an email 3 days ago (below) and got no reply.
My previous email: "{email_1_body}"

This follow-up should:
- Open with "Just wanted to make sure this landed, {owner}."
- Mention that {name} is currently invisible to customers searching online, while {comp_name} gets found first because they have a website
- End with one soft question inviting a reply
- Subtly mention that I help with {services}

2 sentences only. No subject line. No greeting. Start directly with the sentence."""

    results.append({
        **SEQUENCE_META[1],
        "subject": re_subject,
        "body":    _clean(_ollama(e2_prompt), 2),
    })

    # ── Email 3 (Day 7): free value drop ─────────────────────────────────────
    if has_website:
        e3_prompt = f"""Write a 3-sentence cold email for a {category} owner named {owner} in {state}.

This is email 3 in a sequence. They haven't replied yet.
Previous email body: "{results[1]['body']}"

This email should:
- Give ONE specific, free, actionable tip they can use today to improve their Google ranking (pick from: adding schema markup, fixing title tags, or improving page speed)
- Do NOT ask them to buy anything yet
- End with: "I have 4 more quick wins like this — want me to send them over?"
- Make it feel genuinely helpful, not salesy
- Services I offer: {services}

3 sentences only. No subject line. No greeting."""
    else:
        e3_prompt = f"""Write a 3-sentence cold email for a {category} owner named {owner} in {state}.

This is email 3 in a sequence. They haven't replied yet.
Previous email body: "{results[1]['body']}"

This email should:
- Give ONE free tip: "Even without a website, you can claim your Google Business Profile for free to start showing up in local searches"
- Explain that this is step 1 — a real website with SEO would multiply those results
- End with: "I build websites for {category} shops that typically start ranking on Google within 60 days — want me to show you what that looks like for {name}?"
- Make it feel genuinely helpful, not salesy

3 sentences only. No subject line. No greeting."""

    results.append({
        **SEQUENCE_META[2],
        "subject": re_subject,
        "body":    _clean(_ollama(e3_prompt, max_tokens=220), 3),
    })

    # ── Email 4 (Day 14): PPC angle ───────────────────────────────────────────
    if has_website:
        e4_prompt = f"""Write a 2-sentence cold email for a {category} owner named {owner}.

This is email 4. They still haven't replied.
Previous email: "{results[2]['body']}"

This email should:
- Introduce a new angle: while SEO takes 3-6 months to build, PPC (Google Ads) can bring new customers to {name} THIS WEEK
- Mention that most {category} businesses in {state} aren't running Google Ads yet, so the cost-per-click is low right now
- End with a direct but soft call to action to book a quick call
- I offer: {services}

2 sentences only. No subject line. No greeting."""
    else:
        e4_prompt = f"""Write a 2-sentence cold email for a {category} owner named {owner}.

This is email 4. They still haven't replied.
Previous email: "{results[2]['body']}"

This email should:
- Introduce the idea that Google Ads (PPC) can drive customers to {name} even before their new website is finished
- Mention that {comp_name} is likely already running ads, and every day without a website + ads is revenue going to competitors
- End with a direct but soft call to action to book a quick call
- I offer: {services}

2 sentences only. No subject line. No greeting."""

    results.append({
        **SEQUENCE_META[3],
        "subject": re_subject,
        "body":    _clean(_ollama(e4_prompt), 2),
    })

    # ── Email 5 (Day 21): soft urgency ────────────────────────────────────────
    e5_prompt = f"""Write a 2-sentence cold email for a {category} owner named {owner}.

This is email 5. They still haven't replied.
Previous email: "{results[3]['body']}"

This email should:
- Create soft urgency: mention that I'm starting work with another {category} business in {state} next week and wanted to give {owner} first right of refusal
- Make clear this is not a hard sell — just flagging the opportunity before I'm fully booked
- End with a very simple yes/no question
- Services I offer: {services}

2 sentences only. No subject line. No greeting."""

    results.append({
        **SEQUENCE_META[4],
        "subject": re_subject,
        "body":    _clean(_ollama(e5_prompt), 2),
    })

    # ── Email 6 (Day 30): breakup email ──────────────────────────────────────
    e6_prompt = f"""Write a 2-sentence breakup cold email for a {category} owner named {owner}.

This is the final email in a 6-email sequence. They never replied.
Previous email: "{results[4]['body']}"

This email should:
- Tell {owner} this is the last email I'll send so I don't fill up their inbox
- Leave the door wide open — say something like "if {name} ever wants help with {services}, I'm one email away"
- Tone: warm, zero pressure, no guilt-tripping

2 sentences only. No subject line. No greeting."""

    results.append({
        **SEQUENCE_META[5],
        "subject": re_subject,
        "body":    _clean(_ollama(e6_prompt), 2),
    })

    return results
