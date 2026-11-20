from __future__ import annotations

import numpy as np
import pandas as pd

from .common import utc
from .prices import next_session, validate_prices

PRICE_FEATURES = ["ret_1", "ret_5", "volatility_10", "range_pct", "volume_ratio", "support_gap", "resistance_gap"]
SOCIAL_FEATURES = ["social_sentiment", "news_sentiment", "log_mentions", "source_disagreement",
                   "news_count", "source_count", "log_engagement", "missing_engagement"]
ALL_FEATURES = PRICE_FEATURES + SOCIAL_FEATURES


def sentiment_snapshot(posts, cutoff):
    cutoff = utc(cutoff)
    start = cutoff-pd.Timedelta(days=10)
    eligible = [p for p in posts if utc(p["available_at"]) <= cutoff
                and start < utc(p["published_at"]) <= cutoff]
    social = [p for p in eligible if p["kind"] == "social"]
    news = [p for p in eligible if p["kind"] == "news"]
    source_scores = {}
    for source in sorted({p["source"] for p in social}):
        rows = [p for p in social if p["source"] == source]
        weights = [min(5.0, 1.0 + np.log1p((p.get("likes") or 0) +
                                          (p.get("reposts") or 0))/4) for p in rows]
        source_scores[source] = float(np.average([p["sentiment"] for p in rows], weights=weights))
    # Equal source weighting limits domination by one high-volume forum.
    sentiment = float(np.mean(list(source_scores.values()))) if source_scores else 0.0
    engagement = sum((p.get("likes") or 0) + (p.get("reposts") or 0) for p in social)
    missing = np.mean([p.get("likes") is None for p in social]) if social else 1.0
    return {"social_sentiment": sentiment,
            "news_sentiment": float(np.mean([p["sentiment"] for p in news])) if news else 0.0,
            "log_mentions": float(np.log1p(len(social))), "mentions": len(social),
            "source_disagreement": float(np.std(list(source_scores.values()))) if source_scores else 0.0,
            "source_count": len(source_scores), "news_count": len(news),
            "log_engagement": float(np.log1p(engagement)), "missing_engagement": float(missing),
            "source_scores": source_scores,
            "coverage_ok": len(source_scores) >= 2 and len(news) > 0}


def build_features(prices, posts, assets, as_of):
    prices = validate_prices(prices, assets)
    as_of = utc(as_of)
    for post in posts:
        if not utc(post["published_at"]) <= utc(post["observed_at"]) <= utc(post["available_at"]):
            raise ValueError("Post timestamps violate publication/observation/availability order")
        if utc(post["engagement_observed_at"]) > utc(post["available_at"]):
            raise ValueError("Engagement snapshot was not available at the feature availability time")
    # Do not let future price bars create labels available before their close.
    prices = prices[prices.close_time + pd.Timedelta(minutes=15) <= as_of]
    records = []
    for asset in assets:
        own = prices[prices.ticker == asset["ticker"]].copy().sort_values("session")
        asset_posts = [p for p in posts if p["ticker"] == asset["ticker"]]
        if own.empty:
            continue
        # Reindex on every exchange session: a missing bar must not silently become n+1.
        from .prices import schedule
        sessions = schedule(asset, own.session.min(), own.session.max()).index.strftime("%Y-%m-%d")
        own = own.set_index("session").reindex(sessions)
        ret = own.close.pct_change(fill_method=None)
        support = own.low.rolling(20, min_periods=20).min()
        resistance = own.high.rolling(20, min_periods=20).max()
        own["ret_1"] = ret
        own["ret_5"] = own.close.pct_change(5, fill_method=None)
        own["volatility_10"] = ret.rolling(10, min_periods=10).std()
        own["range_pct"] = (own.high-own.low)/own.close
        own["volume_ratio"] = own.volume / own.volume.rolling(20, min_periods=20).mean().replace(0, np.nan)
        own["support_gap"] = own.close/support - 1
        own["resistance_gap"] = resistance/own.close - 1
        own["support"], own["resistance"] = support, resistance
        own["target_return"] = own.close.shift(-1)/own.close - 1
        own["actual_next_close"] = own.close.shift(-1)
        own["label_end"] = own.close_time.shift(-1) + pd.Timedelta(minutes=15)
        # Exclude a split discontinuity and its immediate lag window.
        split_window = own.stock_splits.fillna(0).ne(0).rolling(21, min_periods=1).max().eq(1)
        own.loc[split_window, PRICE_FEATURES] = np.nan
        own.loc[own.stock_splits.shift(-1).fillna(0).ne(0), "target_return"] = np.nan
        for session, row in own.iterrows():
            if pd.isna(row.close):
                continue
            cutoff = utc(row.close_time) + pd.Timedelta(minutes=15)
            target_session, target_close = next_session(asset, session)
            snapshot = sentiment_snapshot(asset_posts, cutoff)
            records.append({"ticker": asset["ticker"], "name": asset["name"], "exchange": asset["exchange"],
                "currency": asset["currency"], "session": session, "cutoff": cutoff,
                "target_session": target_session, "target_close_time": target_close,
                "close": row.close, "support": row.support, "resistance": row.resistance,
                "target_return": row.target_return, "actual_next_close": row.actual_next_close,
                "label_end": row.label_end, **{f: row[f] for f in PRICE_FEATURES}, **snapshot})
    return pd.DataFrame(records)
