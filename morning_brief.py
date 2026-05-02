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
        "name": "Marginal Revolution", "author": "Tyler Cowen",
        "feed": "https://feeds.feedburner.com/marginalrevolution/feed",
        "category": "macro"
    },
    {
        "name": "Bankless", "author": "Bankless",
        "feed": "https://www.bankless.com/feed",
        "category": "crypto"
    },
]

# Email-safe HTML template — uses inline styles only, no flexbox, no pseudo-elements
EMAIL_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Morning Brief — {DATE}</title>
</head>
<body style="margin:0;padding:0;background:#ffffff;font-family:Helvetica,Arial,sans-serif;color:#1a1a1a;font-size:15px;line-height:1.6;">
<div style="max-width:640px;margin:0 auto;padding:32px 24px 48px;">

  <!-- Header -->
  <table width="100%" cellpadding="0" cellspacing="0" style="border-bottom:2px solid #1a1a1a;padding-bottom:20px;margin-bottom:24px;">
    <tr>
      <td style="font-size:22px;font-weight:800;color:#1a1a1a;">
        Morning<span style="color:#2563eb;">Brief</span>
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
          <td align="right"><span style="font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;padding:2px 8px;border-radius:3px;background:{CAT_BG};color:{CAT_COLOR};">{CATEGORY}</span></td>
        </tr>
      </table>
      <a href="{URL}" style="display:block;font-size:24px;font-weight:800;color:#1a1a1a;text-decoration:none;line-height:1.2;margin-bottom:6px;">{TITLE}</a>
      <div style="font-size:14px;color:#555;line-height:1.65;margin-top:6px;">{SUMMARY}</div>
      <div style="margin-top:12px;background:#f9fafb;border-radius:6px;padding:10px 14px;font-size:13.5px;color:#1a1a1a;line-height:1.6;">
        <div style="font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#2563eb;margin-bottom:4px;">&#128161; Your takeaway</div>
        {TAKEAWAY}
      </div>
      <div style="font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.08em;margin-top:8px;">{READ_TIME}</div>
    </div>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;"/>"""

QUICK_LINK_TEMPLATE = """    <div style="font-size:13.5px;margin-bottom:8px;">
      <span style="color:#2563eb;font-weight:700;margin-right:6px;">&#8594;</span>
      <a href="{URL}" style="color:#1a1a1a;text-decoration:none;font-weight:500;">{TITLE}</a>
      <span style="font-size:11px;color:#aaa;margin-left:4px;">{SOURCE}</span>
    </div>"""

CAT_STYLES = {
    "tech":   {"bg": "#dbeafe", "color": "#1d4ed8", "label": "Tech"},
    "macro":  {"bg": "#d1fae5", "color": "#065f46", "label": "Macro"},
    "crypto": {"bg": "#ede9fe", "color": "#5b21b6", "label": "Crypto"},
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

    prompt = f"""You are curating the daily "Morning Brief" newsletter for Tiberiu on {today}.

Below are the latest articles from each source. Return a JSON object with this EXACT structure:

{{
  "intro": "2-3 sentence energetic intro summarising the day's key stories",
  "sections": [
    {{
      "category": "tech",
      "articles": [
        {{
          "source": "Source Name",
          "author": "Author Name",
          "title": "EXACT title from the list below",
          "url": "EXACT url from the list below",
          "summary": "1-2 punchy sentences",
          "takeaway": "Concrete, actionable insight for today",
          "read_time": "4 min read"
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
- Use the EXACT title and EXACT URL from the list — never invent or alter them
- Pick 1-2 articles per category for the main sections; remaining go in quick_links (3-4 total)
- Tone: always positive and forward-looking, never pessimistic
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
            articles_html += ARTICLE_TEMPLATE.format(
                SOURCE=_s(f"{art.get('source','')} · {art.get('author','')}"),
                CAT_BG=cat_style["bg"],
                CAT_COLOR=cat_style["color"],
                CATEGORY=cat_style["label"],
                URL=_s(art.get("url", "#")),
                TITLE=_s(art.get("title", "")),
                SUMMARY=_s(art.get("summary", "")),
                TAKEAWAY=_s(art.get("takeaway", "")),
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
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ✗ Resend error {e.code}: {body}")
        raise


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
