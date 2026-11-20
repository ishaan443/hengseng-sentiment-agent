from __future__ import annotations

import re
from html import unescape

from .common import digest, utc


def text_clean(value):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def matches(text, asset):
    text = text.casefold()
    for alias in [asset["ticker"], *asset["aliases"]]:
        escaped = re.escape(alias.casefold())
        # Prevent 0700 matching 10700, and NAVER matching unrelated word substrings.
        pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])" if alias.isascii() else escaped
        if re.search(pattern, text):
            return True
    return False


def number(value):
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    try:
        result = float(str(value).replace(",", ""))
        return int(result) if result >= 0 and result < 1e15 else None
    except (ValueError, OverflowError):
        return None


def normalize_row(row, source, asset, observed_at, start, end):
    """None means irrelevant/outside window; malformed relevant rows raise ValueError."""
    if source == "lihkg":
        text = text_clean(str(row.get("title") or "") + " " + str(row.get("content") or ""))
        identifier = str(row.get("thread_id", "")) + ":" + str(row.get("reply_id") or "thread")
        published = row.get("created_at")
        url = row.get("thread_url", "")
        likes, views, reposts, followers = row.get("like_count"), None, None, None
        author = row.get("author", "")
    elif source == "naver":
        if row.get("type") == "notice":
            return None
        if str(row.get("stockCode")) != asset["ticker"].split(".")[0]:
            return None
        text = text_clean(str(row.get("title") or "") + " " + str(row.get("text") or ""))
        identifier, published, url = row.get("postId"), row.get("writtenAt"), row.get("url", "")
        likes, views, reposts, followers = row.get("likes"), row.get("views"), None, None
        author = row.get("authorProfileId", row.get("author", ""))
    elif source == "telegram":
        channel = row.get("channel", {})
        channel = channel if isinstance(channel, dict) else {"username": channel}
        message = row.get("message", {})
        text = text_clean(row.get("text") or message.get("description"))
        published = row.get("date") or message.get("fulldate")
        url = message.get("link") or row.get("url", "")
        author = channel.get("username") or row.get("username") or row.get("author") or url
        identifier = f"{author}:{row.get('id') or url}"
        likes = row.get("reactionsTotal")  # Reactions, not exclusively positive likes.
        views = row.get("views", message.get("views"))
        reposts = row.get("forwardsCount")  # Missing when actor does not expose it.
        followers = row.get("followers", channel.get("subscribers"))
    elif source == "exa":
        text = text_clean(str(row.get("title") or "") + " " + str(row.get("text") or ""))
        identifier = url = row.get("url", "")
        published, author = row.get("publishedDate"), row.get("author", "")
        likes = views = reposts = followers = None
    else:
        raise ValueError(f"Unknown source: {source}")
    # Naver's dedicated stock board is sufficient entity attribution.
    if not text or (source != "naver" and not matches(text, asset)):
        return None
    if not published:
        raise ValueError("Missing publication timestamp")
    stamp = utc(published)  # Never assign now() to an unknown publication time.
    if not utc(start) <= stamp <= utc(end):
        return None
    if not identifier or identifier == ":thread":
        raise ValueError("Missing stable post identifier")
    observed = utc(observed_at)
    if stamp > observed:
        raise ValueError("Publication lies after observation")
    return {"id": str(identifier), "ticker": asset["ticker"], "exchange": asset["exchange"],
            "source": source, "kind": "news" if source == "exa" else "social",
            "published_at": stamp.isoformat(), "observed_at": observed.isoformat(),
            "available_at": observed.isoformat(), "text": text, "url": url,
            "author_hash": digest(str(author))[:16] if author else None,
            "likes": number(likes), "views": number(views), "reposts": number(reposts),
            "followers": number(followers), "engagement_observed_at": observed.isoformat()}


def merge_first_observations(old, new):
    """Freeze the earliest text AND engagement snapshot; reruns cannot rewrite history."""
    ordered = sorted([*old, *new], key=lambda p: utc(p["observed_at"]))
    seen_ids, seen_text, result = set(), set(), []
    for p in ordered:
        key = (p["ticker"], p["source"], p["id"])
        text_key = (p["ticker"], p["source"], p["published_at"][:10],
                    digest(text_clean(p["text"]).casefold()))
        if key in seen_ids or text_key in seen_text:
            continue
        seen_ids.add(key)
        seen_text.add(text_key)
        result.append(p)
    return result
