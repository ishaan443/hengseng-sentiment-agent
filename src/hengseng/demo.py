"""Synthetic fixtures. These are never evidence of live predictive performance."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .common import write_json, write_jsonl
from .prices import schedule


def generate(assets, data_dir, end="2026-11-20", seed=42):
    rng = np.random.default_rng(seed)
    prices, posts = [], []
    initial = [450, 110, 85, 150, 40, 70000, 190000, 230000, 200000, 300000]
    for index, asset in enumerate(assets):
        sessions = schedule(asset, "2025-09-01", end)
        price = initial[index]
        prev_latent = prev_return = 0
        sources = ["lihkg", "telegram"] if asset["exchange"] == "HKEX" else ["naver", "telegram"]
        for number, (session, bar) in enumerate(sessions.iterrows()):
            # A deliberately weak, known synthetic relationship exercises the full pipeline.
            ret = float(np.clip(.10*prev_return + .002*prev_latent + rng.normal(0, .013), -.12, .12))
            opening = price * (1+rng.normal(0, .003))
            price *= 1+ret
            high = max(price, opening)*(1+abs(rng.normal(.004, .002)))
            low = min(price, opening)*(1-abs(rng.normal(.004, .002)))
            prices.append({"ticker": asset["ticker"], "session": session.date().isoformat(),
                           "close_time": bar.close.isoformat(), "open": opening, "high": high,
                           "low": low, "close": price, "volume": int(rng.lognormal(16, .35)), "stock_splits": 0.0})
            latent = float(rng.normal())
            positive_prob = 1/(1+np.exp(-latent))
            for source in [*sources, "exa"]:
                count = 1 if source == "exa" else int(rng.integers(2, 5))
                for item in range(count):
                    positive = rng.random() < positive_prob
                    phrases = (["bullish growth strong", "利好 盈利 看好", "상승 호재 성장"] if positive else
                               ["bearish loss weak", "利空 虧損 看淡", "하락 악재 손실"])
                    language = 2 if asset["exchange"] == "KRX" and source != "exa" else 1 if source == "lihkg" else 0
                    published = bar.close-pd.Timedelta(hours=2, minutes=item*7)
                    observed = published+pd.Timedelta(minutes=5)
                    identity = f"synthetic-{index}-{number}-{source}-{item}"
                    posts.append({"id": identity, "ticker": asset["ticker"], "exchange": asset["exchange"],
                        "source": source, "kind": "news" if source == "exa" else "social",
                        "published_at": published.isoformat(), "observed_at": observed.isoformat(),
                        "available_at": observed.isoformat(), "engagement_observed_at": observed.isoformat(),
                        "text": f"SYNTHETIC {asset['name']} {asset['ticker']} {phrases[language]} sample {number}-{item}",
                        "url": "", "author_hash": f"synthetic-author-{item}",
                        "likes": int(rng.integers(0, 40)) if source != "exa" else None,
                        "views": int(rng.integers(50, 4000)) if source == "telegram" else None,
                        "reposts": int(rng.integers(0, 10)) if source == "telegram" else None,
                        "followers": int(rng.integers(300, 10000)) if source == "telegram" else None})
            prev_latent, prev_return = latent, ret
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(prices).to_csv(data_dir / "prices.csv", index=False)
    write_jsonl(data_dir / "posts.jsonl", posts)
    last = max(pd.Timestamp(p["close_time"]) for p in prices)+pd.Timedelta(minutes=15)
    write_json(data_dir / "collection.json", {"mode": "synthetic", "seed": seed,
                "as_of": last.isoformat(), "rows": len(posts), "price_bars": len(prices),
                "note": "Entire history is generated. No real API collection or investment result."})
    return last
