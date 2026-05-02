#!/usr/bin/env python3
"""
MorningTBrief — daily newsletter generator
Fetches latest articles from 4 sources, generates HTML with Claude, sends via Resend.
"""

import os
import json
import datetime
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────
RESEND_API_KEY   = os.environ["RESEND_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
FROM_EMAIL = "MorningTBrief <newsletter@gavristiberiu.com>"
TO_EMAIL   = "me@gavristiberiu.com"

SOURCES = [
    {
        "name": "One Useful Thing", "author": "Ethan Mollick",
        "feed": "https://www.oneusefulthing.org/feed",
        "category": "tech", "type": "rss"
    },
    {
        "name": "The Diff", "author": "Byrne Hobart",
        "feed": "https://www.thediff.co/archive/feed/",
        "category": "tech", "type": "rss"
    },
    {
        "name": "Marginal Revolution", "author": "Tyler Cowen",
        "feed": "https://feeds.feedburner.com/marginalrevolution/feed",
        "category": "macro", "type": "rss"
    },
    {
        "name": "Bankless", "author": "Bankless",
        "feed": "https://www.bankless.com/feed",
        "category": "crypto", "type": "rss"
    },
    {
        "name": "NYT Technology", "author": "New York Times",
        "feed": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "category": "tech", "type": "rss"
    },
    {
        "name": "NYT Economy", "author": "New York Times",
        "feed": "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
        "category": "macro", "type": "rss"
    },
    {
        "name": "Bloomberg Markets", "author": "Bloomberg",
        "feed": "https://feeds.bloomberg.com/markets/news.rss",
        "category": "macro", "type": "rss"
    },
    {
        "name": "Bloomberg Technology", "author": "Bloomberg",
        "feed": "https://feeds.bloomberg.com/technology/news.rss",
        "category": "tech", "type": "rss"
    },
    {
        "name": "Hacker News", "author": "YCombinator",
        "feed": "https://news.ycombinator.com/rss",
        "category": "tech", "type": "rss"
    },
    {
        "name": "CNBC Economy", "author": "CNBC",
        "feed": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
        "category": "macro", "type": "rss"
    },
    {
        "name": "CoinDesk", "author": "CoinDesk",
        "feed": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "category": "crypto", "type": "rss"
    },
]

# Email-safe HTML template — uses inline styles only, no flexbox, no pseudo-elements
EMAIL_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>MorningTBrief — {DATE}</title>
</head>
<body style="margin:0;padding:0;background:#ffffff;font-family:Helvetica,Arial,sans-serif;color:#1a1a1a;font-size:15px;line-height:1.6;">
<div style="max-width:640px;margin:0 auto;padding:32px 24px 48px;">

  <!-- Header -->
  <table width="100%" cellpadding="0" cellspacing="0" style="border-bottom:2px solid #1a1a1a;padding-bottom:20px;margin-bottom:24px;">
    <tr>
      <td style="font-size:22px;font-weight:800;color:#1a1a1a;">
        MorningT<span style="color:#2563eb;">Brief</span>
      </td>
      <td align="right" style="font-size:12px;color:#888;">{DATE}</td>
    </tr>
    <tr>
      <td colspan="2" style="font-size:13px;color:#555;padding-top:6px;">
        Tech &amp; Macro &amp; Crypto, curated for Tiberiu &nbsp;·&nbsp; Est. read time: ~6 min
      </td>
    </tr>
  </table>

  <!-- Intro -->
  <div style="background:#f0f4ff;border-radius:8px;padding:14px 18px;margin-bottom:28px;font-size:13.5px;color:#333;line-height:1.6;border-left:4px solid #2563eb;">
    <strong style="color:#1a1a1a;">Good morning.</strong> {INTRO}
  </div>

  {SECTIONS}

  <!-- Quick Links -->
  <div style="background:#f9fafb;border-radius:8px;padding:16px 20px;margin-bottom:28px;">
    <div style="font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#888;margin-bottom:12px;">&#9889; Also worth your time</div>
    {QUICK_LINKS}
  </div>

  <!-- Footer -->
  <div style="font-size:12px;color:#bbb;text-align:center;line-height:1.9;padding-top:20px;border-top:1px solid #e5e7eb;">
    Delivered daily at 7:00 AM &nbsp;·&nbsp; Curated by Claude<br/>
    <a href="https://www.thediff.co" style="color:#aaa;">The Diff</a> &nbsp;·&nbsp;
    <a href="https://noahpinion.substack.com" style="color:#aaa;">Noahpinion</a> &nbsp;·&nbsp;
    <a href="https://www.oneusefulthing.org" style="color:#aaa;">One Useful Thing</a> &nbsp;·&nbsp;
    <a href="https://www.bankless.com" style="color:#aaa;">Bankless</a>
  </div>

</div>
</body>
</html>"""

SECTION_TEMPLATE = """
  <div style="margin-bottom:32px;">
    <div style="font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#888;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid #e5e7eb;">
      {ICON} {SECTION_NAME}
    </div>
    {ARTICLES}
  </div>"""

ARTICLE_TEMPLATE = """
    <div style="margin-bottom:22px;">
      <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:8px;">
        <tr>
          <td style="font-size:11px;color:#aaa;text-transform:uppercase;letter-spacing:0.06em;font-weight:600;">{SOURCE}</td>
          <td align="right">
            <span style="font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;padding:2px 8px;border-radius:3px;background:{CAT_BG};color:{CAT_COLOR};margin-right:4px;">{CATEGORY}</span>
            <span style="font-size:11px;font-weight:700;padding:2px 7px;border-radius:3px;background:{SENT_BG};color:{SENT_COLOR};">{SENT_ICON} {SENTIMENT}</span>
          </td>
        </tr>
      </table>
      <a href="{URL}" style="display:block;font-size:24px;font-weight:800;color:#1a1a1a;text-decoration:none;line-height:1.2;margin-bottom:10px;">{TITLE}</a>
      <div style="font-size:12px;font-weight:700;color:#555;background:#f3f4f6;border-radius:4px;padding:5px 10px;margin-bottom:12px;">&#128202; {KEY_STAT}</div>
      <table cellpadding="0" cellspacing="0" width="100%">
        <tr><td style="padding-top:10px;padding-bottom:2px;">
          <span style="font-size:11px;font-weight:800;color:#2563eb;text-transform:uppercase;letter-spacing:0.08em;">What Happened</span>
        </td></tr>
        <tr><td style="padding-bottom:14px;font-size:14px;color:#1a1a1a;line-height:1.65;">{WHAT_HAPPENED}</td></tr>
        <tr><td style="padding-top:0;padding-bottom:2px;">
          <span style="font-size:11px;font-weight:800;color:#7c3aed;text-transform:uppercase;letter-spacing:0.08em;">Why It Matters</span>
        </td></tr>
        <tr><td style="padding-bottom:14px;font-size:14px;color:#1a1a1a;line-height:1.65;">{WHY_IT_MATTERS}</td></tr>
        <tr><td style="padding-top:0;padding-bottom:2px;">
          <span style="font-size:11px;font-weight:800;color:#059669;text-transform:uppercase;letter-spacing:0.08em;">What To Do</span>
        </td></tr>
        <tr><td style="padding-bottom:4px;font-size:14px;color:#1a1a1a;line-height:1.65;">{WHAT_TO_DO}</td></tr>
      </table>
      <div style="font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.08em;margin-top:10px;">{READ_TIME}</div>
    </div>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;"/>"""

QUICK_LINK_TEMPLATE = """    <table cellpadding="0" cellspacing="0" style="margin-bottom:10px;width:100%;">
      <tr>
        <td style="width:18px;vertical-align:top;padding-top:1px;color:#2563eb;font-weight:700;font-size:13.5px;">&#8594;</td>
        <td style="font-size:13.5px;line-height:1.5;">
          <a href="{URL}" style="color:#1a1a1a;text-decoration:none;font-weight:500;">{TITLE}</a>
          <span style="font-size:11px;color:#aaa;margin-left:4px;">{SOURCE}</span>
        </td>
      </tr>
    </table>"""

CAT_STYLES = {
    "tech":   {"bg": "#dbeafe", "color": "#1d4ed8", "label": "Tech"},
    "macro":  {"bg": "#d1fae5", "color": "#065f46", "label": "Macro"},
    "crypto": {"bg": "#ede9fe", "color": "#5b21b6", "label": "Crypto"},
}

SENTIMENT_STYLES = {
    "bullish":  {"bg": "#dcfce7", "color": "#15803d", "icon": "🟢"},
    "bearish":  {"bg": "#fee2e2", "color": "#b91c1c", "icon": "🔴"},
    "neutral":  {"bg": "#fef9c3", "color": "#92400e", "icon": "🟡"},
}

SECTION_META = {
    "tech":   {"icon": "🤖", "name": "AI &amp; Technology"},
    "macro":  {"icon": "📈", "name": "Macro Economics"},
    "crypto": {"icon": "₿",  "name": "Crypto · BTC &amp; ETH"},
}


# ── RSS Fetching ──────────────────────────────────────────────────────────────

def fetch_feed(url: str, max_items: int = 3) -> list[dict]:
    """Fetch RSS/Atom feed, return list of {title, link, description}."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MorningBrief/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        items = []

        # RSS 2.0
        for item in root.findall(".//item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            desc  = (item.findtext("description") or "").strip()[:600]
            if title and link:
                items.append({"title": title, "link": link, "description": desc})

        # Atom
        if not items:
            ns = "http://www.w3.org/2005/Atom"
            for entry in root.findall(f".//{{{ns}}}entry")[:max_items]:
                title = (entry.findtext(f"{{{ns}}}title") or "").strip()
                link_el = entry.find(f"{{{ns}}}link")
                link = link_el.get("href", "") if link_el is not None else ""
                summary = (entry.findtext(f"{{{ns}}}summary") or "").strip()[:600]
                if title and link:
                    items.append({"title": title, "link": link, "description": summary})

        return items
    except Exception as e:
        print(f"  ⚠ Could not fetch {url}: {e}")
        return []


def fetch_reddit(subreddit: str, max_items: int = 3) -> list[dict]:
    """Fetch top hot posts from a subreddit via Reddit's public JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=10"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MorningBrief/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        items = []
        for post in data["data"]["children"]:
            p = post["data"]
            if p.get("stickied") or p.get("is_self") and not p.get("selftext"):
                continue  # skip pinned/empty posts
            title = p.get("title", "").strip()
            permalink = f"https://reddit.com{p.get('permalink', '')}"
            score = p.get("score", 0)
            comments = p.get("num_comments", 0)
            desc = (p.get("selftext", "") or p.get("title", ""))[:400]
            if title:
                items.append({
                    "title": title,
                    "link": permalink,
                    "description": f"{desc} [{score:,} upvotes · {comments:,} comments]"
                })
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"  ⚠ Could not fetch r/{subreddit}: {e}")
        return []


# ── Newsletter Generation ─────────────────────────────────────────────────────

def build_articles_context(sources_with_articles: list[dict]) -> str:
    lines = []
    for s in sources_with_articles:
        lines.append(f"\n### {s['name']} · {s['author']} (category: {s['category']})")
        for i, a in enumerate(s["articles"], 1):
            lines.append(f"  {i}. TITLE: {a['title']}")
            lines.append(f"     URL:   {a['link']}")
            lines.append(f"     DESC:  {a['description'][:400]}")
    return "\n".join(lines)


def generate_content(sources_with_articles: list[dict]) -> dict:
    """Ask Claude to return structured JSON content for the newsletter."""
    today = datetime.datetime.now().strftime("%A, %B %-d, %Y")
    context = build_articles_context(sources_with_articles)

    prompt = f"""You are curating the daily "MorningTBrief" newsletter for Tiberiu on {today}.

Write in the exact style of The Daily Skimm newsletter. Use their signature language patterns:
- Start summaries with "Here's the deal:" or "What's happening:"
- Use "Why you should care:" or "Why it matters:" to transition to impact
- Use short, punchy sentences. One idea per sentence. Like this.
- Use "So..." or "But here's the thing..." as connectors
- Use "Long story short:" before the key point
- Address the reader as "you" directly — always personal
- Use rhetorical questions to hook: "Remember when X? Yeah, that's happening again."
- Use ellipses for suspense and em-dashes for punchy asides
- End takeaways with "The bottom line:" or "What to watch:"
- Zero corporate jargon. If it sounds like a press release, rewrite it.
- Each summary should feel like a text from a smart friend who read the whole article so you don't have to.
- Do NOT add any <br/> tags inside what_happened, why_it_matters, or what_to_do — spacing is handled by the template
- When you use these phrases, always wrap them in <strong> tags: "Here's the deal:" → <strong>Here's the deal:</strong> | "Why it matters:" → <strong>Why it matters:</strong> | "The bottom line:" → <strong>The bottom line:</strong>
- No other phrases should be bolded

Below are the latest articles. Return a JSON object with this EXACT structure:

{{
  "intro": "2-3 sentence Skimm-style intro — witty, energetic, hooks the reader on today's big themes",
  "sections": [
    {{
      "category": "tech",
      "articles": [
        {{
          "source": "Source Name",
          "author": "Author Name",
          "title": "EXACT title from the list below",
          "url": "EXACT url from the list below",
          "key_stat": "The single most important number, percentage, or fact from this story (e.g. '87% accuracy', '$2.4B raised', 'rates held at 4.5%')",
          "sentiment": "bullish OR bearish OR neutral",
          "what_happened": "1-2 punchy sentences — just the facts, Skimm voice, no jargon",
          "why_it_matters": "1-2 sentences — the implication, why should Tiberiu care right now",
          "what_to_do": "1 concrete action or thing to think about today — direct, personal, specific",
          "read_time": "X min read"
        }}
      ]
    }},
    {{
      "category": "macro",
      "articles": [...]
    }},
    {{
      "category": "crypto",
      "articles": [...]
    }}
  ],
  "quick_links": [
    {{"title": "EXACT title", "url": "EXACT url", "source": "Source Name"}}
  ]
}}

STRICT RULES:
- Use the EXACT URL from the list — never invent or alter URLs
- Rewrite the title in plain English, max 8 words, Skimm style — clear, punchy, no jargon or SEO clickbait
- Pick 1-2 articles per category for main sections; remaining go in quick_links (3-4 total)
- sentiment must be exactly one of: bullish, bearish, neutral
- key_stat must be a specific number or fact — never vague (not "significant growth", yes "up 34% YoY")
- Tone: always positive and forward-looking, never pessimistic
- Even bearish stories must end on an opportunity angle — "What To Do" should always frame the situation as something Tiberiu can use to his advantage, not something to fear or avoid
- Return ONLY valid JSON — no markdown, no code fences, no explanations

TODAY'S ARTICLES:
{context}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    # Strip code fences if Claude added them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _s(value) -> str:
    """Escape curly braces in dynamic values so they don't break str.format()."""
    return str(value).replace("{", "&#123;").replace("}", "&#125;")


def assemble_html(content: dict) -> str:
    """Assemble email-safe HTML from structured content dict using inline-style templates."""
    today = datetime.datetime.now().strftime("%A, %B %-d, %Y")

    # Build sections
    sections_html = ""
    for section in content.get("sections", []):
        cat = section["category"]
        meta = SECTION_META.get(cat, {"icon": "•", "name": cat.title()})
        cat_style = CAT_STYLES.get(cat, {"bg": "#f3f4f6", "color": "#374151", "label": cat.title()})

        articles_html = ""
        for art in section.get("articles", []):
            sent_key = art.get("sentiment", "neutral").lower()
            sent_style = SENTIMENT_STYLES.get(sent_key, SENTIMENT_STYLES["neutral"])
            articles_html += ARTICLE_TEMPLATE.format(
                SOURCE=_s(f"{art.get('source','')} · {art.get('author','')}"),
                CAT_BG=cat_style["bg"],
                CAT_COLOR=cat_style["color"],
                CATEGORY=cat_style["label"],
                SENT_BG=sent_style["bg"],
                SENT_COLOR=sent_style["color"],
                SENT_ICON=sent_style["icon"],
                SENTIMENT=_s(sent_key.capitalize()),
                URL=_s(art.get("url", "#")),
                TITLE=_s(art.get("title", "")),
                KEY_STAT=_s(art.get("key_stat", "")),
                WHAT_HAPPENED=_s(art.get("what_happened", "")),
                WHY_IT_MATTERS=_s(art.get("why_it_matters", "")),
                WHAT_TO_DO=_s(art.get("what_to_do", "")),
                READ_TIME=_s(art.get("read_time", "")),
            )

        sections_html += SECTION_TEMPLATE.format(
            ICON=meta["icon"],
            SECTION_NAME=meta["name"],
            ARTICLES=articles_html,
        )

    # Build quick links
    quick_links_html = ""
    for ql in content.get("quick_links", []):
        quick_links_html += QUICK_LINK_TEMPLATE.format(
            URL=_s(ql.get("url", "#")),
            TITLE=_s(ql.get("title", "")),
            SOURCE=_s(ql.get("source", "")),
        )

    return EMAIL_TEMPLATE.format(
        DATE=today,
        INTRO=_s(content.get("intro", "")),
        SECTIONS=sections_html,
        QUICK_LINKS=quick_links_html,
    )


def generate_html(sources_with_articles: list[dict]) -> str:
    """Generate newsletter HTML: ask Claude for JSON content, then assemble with templates."""
    content = generate_content(sources_with_articles)
    return assemble_html(content)


# ── Email Sending ─────────────────────────────────────────────────────────────

def send_email(html: str) -> dict:
    import time
    today = datetime.datetime.now().strftime("%A, %B %-d, %Y")
    payload = {
        "from": FROM_EMAIL,
        "to": [TO_EMAIL],
        "subject": f"MorningTBrief — {today}",
        "html": html
    }
    data = json.dumps(payload).encode()

    last_err = None
    for attempt in range(1, 4):
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=data,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "MorningBrief/1.0 (Python urllib)",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  ✗ Attempt {attempt} — Resend error {e.code}: {body}")
            last_err = e
            if attempt < 3:
                time.sleep(3)
    raise last_err


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("🗞  MorningTBrief generator starting...")

    # 1. Fetch all feeds
    sources_with_articles = []
    for source in SOURCES:
        print(f"  Fetching {source['name']}...")
        articles = fetch_feed(source["feed"])
        if articles:
            sources_with_articles.append({**source, "articles": articles})
            print(f"  ✓ {len(articles)} articles found")
        else:
            print(f"  ✗ No articles (skipping)")

    if not sources_with_articles:
        raise RuntimeError("No articles fetched from any source — aborting.")

    # 2. Generate newsletter HTML with Claude
    print("\n  Generating newsletter with Claude...")
    html = generate_html(sources_with_articles)
    print(f"  ✓ HTML generated ({len(html):,} chars)")

    # 3. Send via Resend
    masked = RESEND_API_KEY[:6] + "..." + RESEND_API_KEY[-4:] if len(RESEND_API_KEY) > 10 else "***"
    print(f"\n  Sending via Resend (key: {masked})...")
    result = send_email(html)
    print(f"  ✓ Email sent! ID: {result.get('id')}")
    print("\n🎉 Done!")


if __name__ == "__main__":
    main()
