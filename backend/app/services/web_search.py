"""
Web search for Sable (opt-in, keyless via DuckDuckGo).

This is the ONLY part of LENS that reaches the public internet, and it is OFF by
default. It is used solely by the Sable assistant — which never receives client
data — so only the analyst's typed question is ever sent out. Fail-soft: any
error yields no results and Sable answers from its own knowledge.

DuckDuckGo's HTML endpoint is keyless but unofficial; the parse can break if they
change markup. That trade-off was chosen deliberately (no API key / no cost).
"""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

_DDG = "https://html.duckduckgo.com/html/"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

_LINK_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S
)
_SNIP_RE = re.compile(r'class="result__snippet"[^>]*>(?P<snip>.*?)</a>', re.S)


class WebSearchError(RuntimeError):
    pass


def _clean(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _real_url(href: str) -> str:
    """DDG wraps result links as //duckduckgo.com/l/?uddg=<encoded>. Unwrap it."""
    if "uddg=" in href:
        u = ("https:" + href) if href.startswith("//") else href
        q = parse_qs(urlparse(u).query)
        if q.get("uddg"):
            return unquote(q["uddg"][0])
    return href


def parse_results(html_text: str, max_results: int = 5) -> list[dict]:
    """Extract {title, url, snippet} blocks from DDG HTML. Pure — unit-tested."""
    links = list(_LINK_RE.finditer(html_text))
    snips = list(_SNIP_RE.finditer(html_text))
    out: list[dict] = []
    for i, m in enumerate(links[:max_results]):
        title = _clean(m.group("title"))
        if not title:
            continue
        out.append({
            "title": title,
            "url": _real_url(m.group("href")),
            "snippet": _clean(snips[i].group("snip")) if i < len(snips) else "",
        })
    return out


def search(query: str, max_results: int = 5) -> list[dict]:
    """Run a keyless DuckDuckGo search. Raises WebSearchError on transport failure
    (the caller decides whether to degrade)."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        with httpx.Client(timeout=10, headers={"User-Agent": _UA}, follow_redirects=True) as c:
            resp = c.post(_DDG, data={"q": q[:400]})
            resp.raise_for_status()
            return parse_results(resp.text, max_results=max_results)
    except httpx.HTTPError as exc:
        raise WebSearchError(str(exc)) from exc
