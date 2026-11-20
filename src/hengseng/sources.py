"""Read public data through Apify and Exa; persist every request/run for audit."""
from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pandas as pd

from .common import digest, read_jsonl, utc, write_json, write_jsonl
from .normalize import merge_first_observations, normalize_row


class SourceError(RuntimeError):
    pass


def request(client, method, url, **kwargs):
    # Actor POST is deliberately NOT retried: a timeout may already have started a paid run.
    attempts = 4 if method == "GET" else 1
    for attempt in range(attempts):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            if attempt + 1 == attempts:
                raise SourceError(f"{method} {url}: transport failure; inspect recorded run before retrying") from exc
            time.sleep(min(2**attempt, 8))
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt + 1 < attempts:
                time.sleep(min(float(response.headers.get("retry-after", 2**attempt)), 30))
                continue
        if response.status_code >= 400:
            # Do not echo response bodies/headers, which can contain credentials.
            raise SourceError(f"{method} {url}: HTTP {response.status_code}")
        return response.json()
    raise SourceError("Request exhausted retries")


class ApifyRunner:
    def __init__(self, token, archive, config, client=None):
        self.archive = Path(archive)
        self.config = config
        self.client = client or httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=60)
        self.base = "https://api.apify.com/v2"
        self.runs = []

    def run(self, source, run_input):
        actor = self.config["actors"][source]
        path = f"{self.base}/actors/{quote(actor['id'].replace('/', '~'), safe='~')}/runs"
        fingerprint = digest({"actor": actor, "input": run_input})[:16]
        record = {"source": source, "actor_id": actor["id"], "requested_build": actor["build"],
                  "input": run_input, "request_hash": fingerprint}
        write_json(self.archive / f"{fingerprint}-request.json", record)
        run = request(self.client, "POST", path, json=run_input,
                      params={"build": actor["build"], "timeout": self.config["actor_timeout_seconds"],
                              "maxTotalChargeUsd": self.config["max_charge_usd_per_actor_run"]})["data"]
        record.update(run_id=run["id"], build_id=run.get("buildId"), status=run["status"])
        self.runs.append(record)
        write_json(self.archive / f"{run['id']}-run.json", record)
        deadline = time.monotonic() + self.config["actor_timeout_seconds"] + 120
        while run["status"] in {"READY", "RUNNING", "TIMING-OUT", "ABORTING"}:
            if time.monotonic() > deadline:
                # Explicit abort on client timeout to bound a continuing run.
                request(self.client, "POST", f"{self.base}/actor-runs/{run['id']}/abort")
                raise SourceError(f"Actor run {run['id']} exceeded client deadline and was aborted")
            time.sleep(2)
            run = request(self.client, "GET", f"{self.base}/actor-runs/{run['id']}",
                          params={"waitForFinish": 20})["data"]
        record.update(status=run["status"], dataset_id=run.get("defaultDatasetId"),
                      build_id=run.get("buildId"), finished_at=run.get("finishedAt"))
        write_json(self.archive / f"{run['id']}-run.json", record)
        if run["status"] != "SUCCEEDED":
            raise SourceError(f"Actor run {run['id']} ended {run['status']}")
        rows, offset = [], 0
        while True:
            batch = request(self.client, "GET", f"{self.base}/datasets/{run['defaultDatasetId']}/items",
                            params={"offset": offset, "limit": 1000, "clean": "true"})
            rows.extend(batch)
            if len(batch) < 1000:
                break
            offset += len(batch)
        record["row_count"] = len(rows)
        record["data_sha256"] = digest(rows)
        write_json(self.archive / f"{run['id']}-run.json", record)
        write_json(self.archive / f"{run['id']}-data.json", rows)
        return rows


def preflight(config):
    missing = [name for name in ("APIFY_TOKEN", "EXA_API_KEY") if not os.environ.get(name)]
    for exchange in ("HKEX", "KRX"):
        if not config["telegram_channels"].get(exchange):
            missing.append(f"config/sources.json: telegram_channels.{exchange}")
    if missing:
        raise SourceError("Live collection needs: " + ", ".join(missing))


def collect(assets, config, data_dir, now=None):
    preflight(config)  # Validate all required inputs before any paid API calls.
    end = utc(now or pd.Timestamp.now(tz="UTC"))
    start = end - pd.Timedelta(days=10)
    data_dir = Path(data_dir)
    archive = data_dir / "raw" / end.strftime("%Y%m%dT%H%M%S%fZ")
    runner = ApifyRunner(os.environ["APIFY_TOKEN"], archive, config)
    exa = httpx.Client(headers={"x-api-key": os.environ["EXA_API_KEY"]}, timeout=90)
    posts, failures, notices = [], [], []
    cap = config["max_results_per_query"]

    def accept(rows, source, asset):
        observed = pd.Timestamp.now(tz="UTC")
        accepted = 0
        for row in rows:
            try:
                p = normalize_row(row, source, asset, observed, start, end)
                if p:
                    posts.append(p)
                    accepted += 1
            except (ValueError, TypeError) as exc:
                notices.append({"ticker": asset["ticker"], "source": source,
                                "row_hash": digest(row), "reason": str(exc)})
        return accepted

    try:
        for asset in assets:
            source = "lihkg" if asset["exchange"] == "HKEX" else "naver"
            try:
                if source == "lihkg":
                    listing = runner.run(source, {"mode": "search", "keywords": asset["aliases"],
                                                  "order": "desc_create_time", "maxItems": cap})
                    ids = []
                    for r in listing:
                        try:
                            if start <= utc(r.get("created_at")) <= end:
                                ids.append(str(r["thread_id"]))
                        except (ValueError, TypeError, KeyError):
                            continue
                    ids = list(dict.fromkeys(ids))[:cap]
                    # Full-thread mode is needed to get body text rather than search titles only.
                    rows = runner.run(source, {"mode": "thread", "threadIds": ids,
                                               "maxItems": len(ids)}) if ids else []
                else:
                    rows = runner.run(source, {"stocks": [asset["ticker"].split(".")[0]],
                                               "dateFrom": start.tz_convert("Asia/Seoul").date().isoformat(),
                                               "maxResults": cap})
                accept(rows, source, asset)
            except SourceError as exc:
                failures.append({"ticker": asset["ticker"], "source": source, "error": str(exc)})
            try:
                rows = runner.run("telegram", {"urls": config["telegram_channels"][asset["exchange"]],
                    "collectMessages": True, "maxMessagesPerChannel": cap,
                    "dateFrom": start.isoformat(), "dateTo": end.isoformat(),
                    "searchQueries": asset["aliases"], "outputMode": "legacy",
                    "exactSubscriberCount": True})
                accept(rows, "telegram", asset)
            except SourceError as exc:
                failures.append({"ticker": asset["ticker"], "source": "telegram", "error": str(exc)})
            try:
                payload = {"query": f"{asset['name']} {asset['ticker']} earnings stock company news",
                           "category": "news", "type": "auto", "numResults": config["news_results_per_asset"],
                           "startPublishedDate": start.isoformat(), "endPublishedDate": end.isoformat(),
                           "contents": {"text": {"maxCharacters": 6000}}}
                result = request(exa, "POST", "https://api.exa.ai/search", json=payload)
                write_json(archive / f"exa-{asset['ticker']}.json", {"input": payload, "response": result})
                accept(result.get("results", []), "exa", asset)
            except SourceError as exc:
                failures.append({"ticker": asset["ticker"], "source": "exa", "error": str(exc)})
    finally:
        runner.client.close()
        exa.close()
        write_jsonl(data_dir / "posts.jsonl", merge_first_observations(
            read_jsonl(data_dir / "posts.jsonl"), posts))
        coverage = []
        for a in assets:
            own = [p for p in posts if p["ticker"] == a["ticker"]]
            social = sorted({p["source"] for p in own if p["kind"] == "social"})
            news = sum(p["kind"] == "news" for p in own)
            coverage.append({"ticker": a["ticker"], "social_sources": social,
                             "posts": len(own), "news": news, "meets_requirement": len(social) >= 2 and news > 0})
        manifest = {"mode": "live", "start": start.isoformat(), "end": end.isoformat(),
                    "window_days": 10, "actors": runner.runs, "coverage": coverage,
                    "failures": failures, "rejected_rows": notices,
                    "scope": "Capped public search results; complete platform coverage is not asserted."}
        write_json(archive / "manifest.json", manifest)
        write_json(data_dir / "collection.json", manifest)
    return manifest
