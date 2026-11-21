"""Re-score a previous GitHub collection using only reads from Apify storage."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from hengseng.common import read_json, utc
from hengseng.normalize import merge_first_observations, normalize_row
from hengseng.features import sentiment_snapshot
from hengseng.sentiment import LexiconScorer, score_posts
from hengseng.sources import request


def main():
    evidence = read_json(Path(sys.argv[1]) / "coverage.json")
    start, end = utc(evidence["start"]), utc(evidence["end"])
    assets = read_json("config/assets.json")
    config = read_json("config/sources.json")
    allowed_channels = {name.casefold() for group in config["telegram_channels"].values() for name in group}
    records = {a["ticker"]: [] for a in assets}
    with httpx.Client(base_url="https://api.apify.com/v2/", timeout=60,
                      headers={"Authorization": "Bearer " + os.environ["APIFY_TOKEN"]}) as client:
        for source, actor in config["actors"].items():
            runs = request(client, "GET", "actors/" + actor["id"].replace("/", "~") + "/runs",
                           params={"desc": "true", "status": "SUCCEEDED", "limit": 100})["data"]["items"]
            # The evidence window ended when the recovery began. Include its two preceding attempts.
            for run in runs:
                if not end - pd.Timedelta(minutes=20) <= utc(run["startedAt"]) <= end + pd.Timedelta(minutes=2):
                    continue
                payload = request(client, "GET", f"key-value-stores/{run['defaultKeyValueStoreId']}/records/INPUT")
                if source == "telegram" and not {str(x).casefold() for x in payload.get("urls", [])}.issubset(allowed_channels):
                    continue
                if source == "naver" and not set(payload.get("stocks", [])).issubset(
                        {a["ticker"].split(".")[0] for a in assets} | {a["ticker"] for a in assets}):
                    continue
                if source == "lihkg" and payload.get("mode") not in ("search", "thread"):
                    continue
                observed = utc(run["finishedAt"])
                offset = 0
                while True:
                    batch = request(client, "GET", f"datasets/{run['defaultDatasetId']}/items",
                                    params={"clean": "true", "limit": 1000, "offset": offset})
                    for a in assets:
                        if source == "lihkg" and a["exchange"] != "HKEX":
                            continue
                        for row in batch:
                            try:
                                post = normalize_row(row, source, a, observed, start, end)
                            except (TypeError, ValueError):
                                continue
                            if post:
                                records[a["ticker"]].append(post)
                    if len(batch) < 1000:
                        break
                    offset += len(batch)
    scores = []
    for a in assets:
        posts = score_posts(merge_first_observations([], records[a["ticker"]]), LexiconScorer())
        # Filtering to the recorded window happened above. Summarize the retained observations.
        snapshot_time = max((utc(p["available_at"]) for p in posts), default=end)
        s = sentiment_snapshot(posts, max(end, snapshot_time))
        scores.append({"ticker": a["ticker"], "scored_mentions": s["mentions"],
                       "social_sentiment": s["social_sentiment"] if s["mentions"] else None,
                       "source_scores": s["source_scores"]})
    if not any(r["scored_mentions"] for r in scores):
        raise RuntimeError("No archived social observations could be matched.")
    Path("scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=2))
    print("Scored", sum(r["scored_mentions"] for r in scores), "ticker-post observations.")


if __name__ == "__main__":
    main()
