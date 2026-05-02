#!/usr/bin/env python3
"""
Morning Brief — daily newsletter generator
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
FROM_EMAIL = "Morning Brief <newsletter@gavristiberiu.com>"
TO_EMAIL   = "me@gavristiberiu.com"

SOURCES = [
    {
        "name": "One Useful Thing", "author": "Ethan Mollick",
        "feed": "https://www.oneusefulthing.org/feed",
        "category": "tech"
    },
    {
        "name": "The Diff", "author": "Byrne Hobart",
        "feed": "https://www.thediff.co/archive/feed/",
        "category": "tech"
    },
    {
        "name": "Noahpinion", "author": "Noah Smith",
        "feed": "https://noahpinion.substack.com/feed",
        "category": "macro"
    },
    {
        "name": "Bankless", "author": "Bankless",
        "feed": "https://www.bankless.com/feed",
        "category": "crypto"
    },
]

CSS = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; color: #1a1a1a; font-size: 15px; line-height: 1.6; }
    .wrapper { max-width: 640px; margin: 0 auto; padding: 32px 24px 48px; }
    .header { border-bottom: 2px solid #1a1a1a; padding-bottom: 20px; margin-bottom: 24px; }
    .header-top { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 8px; }
    .brand { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; color: #1a1a1a; }
    .brand span { color: #2563eb; }
    .meta { font-size: 12px; color: #888; }
    .tagline { margin-top: 6px; font-size: 13px; color: #555; }
    .intro-bar { background: #f0f4ff; border-radius: 8px; padding: 14px 18px; margin-bottom: 28px; font-size: 13.5px; color: #333; line-height: 1.6; border-left: 3px solid #2563eb; }
    .intro-bar strong { color: #1a1a1a; }
    .section-heading { font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #888; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #e5e7eb; display: flex; align-items: center; gap: 8px; }
    .section { margin-bottom: 32px; }
    .article { margin-bottom: 22px; }
    .article-source { font-size: 11px; color: #aaa; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; display: flex; justify-content: space-between; align-items: center; }
    .article-title { display: block; font-size: 24px; font-weight: 800; color: #1a1a1a; text-decoration: none; line-height: 1.2; letter-spacing: -0.4px; margin-bottom: 6px; }
    .article-summary { font-size: 14px; color: #555; line-height: 1.65; margin-top: 6px; }
    .article-meta { display: inline-block; font-size: 11px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 4px; }
    .cat-tag { font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; padding: 2px 8px; border-radius: 3px; flex-shrink: 0; }
    .cat-tech { background: #dbeafe; color: #1d4ed8; }
    .cat-macro { background: #d1fae5; color: #065f46; }
    .cat-crypto { background: #ede9fe; color: #5b21b6; }
    .takeaway { margin-top: 12px; background: #f9fafb; border-radius: 6px; padding: 10px 14px; font-size: 13.5px; color: #1a1a1a; line-height: 1.6; }
    .takeaway-label { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: #2563eb; margin-bottom: 3px; }
    .divider { border: none; border-top: 1px solid #e5e7eb; margin: 24px 0; }
    .quick-links { background: #f9fafb; border-radius: 8px; padding: 16px 20px; margin-bottom: 28px; }
    .quick-links-title { font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #888; margin-bottom: 12px; }
    .quick-link-item { font-size: 13.5px; margin-bottom: 8px; display: flex; align-items: baseline; gap: 8px; }
    .quick-link-item::before { content: "→"; color: #2563eb; font-weight: 700; flex-shrink: 0; }
    .quick-link-item a { color: #1a1a1a; text-decoration: none; font-weight: 500; }
    .quick-link-item .ql-source { font-size: 11px; color: #aaa; flex-shrink: 0; }
    .footer { font-size: 12px; color: #bbb; text-align: center; line-height: 1.9; padding-top: 20px; border-top: 1px solid #e5e7eb; }
    .footer a { color: #aaa; }
"""


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


def generate_html(sources_with_articles: list[dict]) -> str:
    today = datetime.datetime.now().strftime("%A, %B %-d, %Y")
    context = build_articles_context(sources_with_articles)

    prompt = f"""You are generating the daily "Morning Brief" newsletter for Tiberiu for {today}.

Below are the latest articles fetched from each source. Your job:
1. Pick the 1-2 most relevant/recent articles per source
2. Write the full newsletter as a single HTML document

STRICT RULES:
- Use the EXACT title and EXACT URL from the list below — never invent, shorten, or alter them
- Summaries: 1-2 sentences max, punchy and direct
- Takeaways: concrete and actionable — something to think about or apply today
- Tone: always positive and forward-looking, never pessimistic
- Category tags: cat-tech (blue), cat-macro (green), cat-crypto (purple)
- Return ONLY valid HTML — no markdown, no code fences, no explanations

TODAY'S ARTICLES:
{context}

Generate the complete HTML using this exact structure (replace placeholders):

<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Morning Brief — {today}</title>
  <style>
{CSS}
  </style>
</head>
<body>
<div class="wrapper">

  <div class="header">
    <div class="header-top">
      <div class="brand">Morning<span>Brief</span></div>
      <div class="meta">{today}</div>
    </div>
    <div class="tagline">Tech &amp; Macro &amp; Crypto, curated for Tiberiu · Est. read time: ~6 min</div>
  </div>

  <div class="intro-bar">
    <strong>Good morning.</strong> [Write 2-3 sentence intro summarising today's key stories — positive, energetic]
  </div>

  <!-- 🤖 AI & Technology section with 1-2 articles -->
  <!-- 📈 Macro Economics section with 1-2 articles -->
  <!-- ₿ Crypto · BTC & ETH section with 1-2 articles -->

  <!-- Each article block must follow this exact pattern:
  <div class="article">
    <div class="article-source"><span>SOURCE NAME · AUTHOR</span><span class="cat-tag cat-CATEGORY">CATEGORY</span></div>
    <a class="article-title" href="EXACT_URL">EXACT_TITLE</a>
    <div class="article-summary">1-2 sentence summary.</div>
    <div class="takeaway">
      <div class="takeaway-label">💡 Your takeaway</div>
      Concrete, actionable takeaway for today.
    </div>
    <span class="article-meta">X min read</span>
  </div>
  -->

  <!-- Quick links: 3-4 additional article links -->
  <div class="quick-links">
    <div class="quick-links-title">⚡ Also worth your time</div>
    <!-- quick-link-items -->
  </div>

  <div class="footer">
    Delivered daily at 7:00 AM &nbsp;·&nbsp; Curated by Claude<br/>
    Sources: <a href="https://www.thediff.co">The Diff</a> &nbsp;·&nbsp;
    <a href="https://noahpinion.substack.com">Noahpinion</a> &nbsp;·&nbsp;
    <a href="https://www.oneusefulthing.org">One Useful Thing</a> &nbsp;·&nbsp;
    <a href="https://www.bankless.com">Bankless</a>
  </div>

</div>
</body>
</html>"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text.strip()


# ── Email Sending ─────────────────────────────────────────────────────────────

def send_email(html: str) -> dict:
    today = datetime.datetime.now().strftime("%A, %B %-d, %Y")
    payload = {
        "from": FROM_EMAIL,
        "to": [TO_EMAIL],
        "subject": f"Morning Brief — {today}",
        "html": html
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("🗞  Morning Brief generator starting...")

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
    print("\n  Sending via Resend...")
    result = send_email(html)
    print(f"  ✓ Email sent! ID: {result.get('id')}")
    print("\n🎉 Done!")


if __name__ == "__main__":
    main()
