from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
import pandas as pd

from . import __version__
from .common import digest, read_json, read_jsonl, utc, write_json, write_jsonl
from .demo import generate
from .features import build_features
from .model import evaluate_saved, forecast_latest, metrics, walk_forward
from .prices import fetch_prices, validate_prices
from .report import write_report
from .sentiment import LexiconScorer, TransformerScorer, score_posts
from .sources import collect, preflight


def analyse(data_dir, out_dir, assets, as_of=None, backend="lexicon"):
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    collection = read_json(data_dir / "collection.json")
    mode = collection["mode"]
    if (out_dir / "manifest.json").exists() and read_json(out_dir / "manifest.json")["mode"] != mode:
        raise ValueError("Synthetic and live results must use separate output directories")
    as_of = utc(as_of or collection.get("as_of") or pd.Timestamp.now(tz="UTC"))
    prices = validate_prices(pd.read_csv(data_dir / "prices.csv"), assets)
    missing = {a["ticker"] for a in assets}-set(prices.ticker)
    if missing:
        raise ValueError(f"Missing price series: {sorted(missing)}")
    posts = read_jsonl(data_dir / "posts.jsonl")
    scorer = LexiconScorer() if backend == "lexicon" else TransformerScorer(os.environ.get("SENTIMENT_REVISION") or None)
    posts = score_posts(posts, scorer)
    features = build_features(prices, posts, assets, as_of)
    if features.empty:
        raise ValueError("No completed price bars available at the requested as-of time")
    oos, folds = walk_forward(features)
    # A historical replay must never pretend it was actually issued in the past.
    issued_at = as_of if mode == "synthetic" else pd.Timestamp.now(tz="UTC")
    forecasts = forecast_latest(features, oos, issued_at)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_root = Path(__file__).parent
    code_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(source_root.iterdir()) if p.suffix in {".py", ".html"}}
    manifest = {"mode": mode, "as_of": as_of.isoformat(), "issued_at": issued_at.isoformat(),
                "pipeline_version": __version__, "code_sha256": digest(code_hashes),
                "python": sys.version.split()[0], "sentiment": scorer.metadata,
                "packages": {p: version(p) for p in ["numpy", "pandas", "scikit-learn", "exchange-calendars", "httpx"]},
                "assets": assets, "files": {p: hashlib.sha256((data_dir/p).read_bytes()).hexdigest()
                                           for p in ["prices.csv", "posts.jsonl", "collection.json"]},
                "validation": {"min_train_dates": 60, "test_block_dates": 15, "gap_dates": 1,
                    "ridge_alpha": 10.0, "selection": "fixed, no OOS tuning", "target": "next-session raw close return"},
                "collection": collection}
    run_id = digest(manifest)[:16]
    # A distinct immutable directory preserves forecasts made on each run.
    run_dir = out_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    forecasts.sort(key=lambda row: (row["exchange"], -row["mentions"], -row["social_sentiment"]))
    for row in forecasts:
        row.update(run_id=run_id, data_mode=mode)
    result_metrics = metrics(oos)
    for directory in (run_dir, out_dir):
        write_json(directory / "manifest.json", manifest)
        write_json(directory / "forecasts.json", forecasts)
        write_json(directory / "metrics.json", result_metrics)
        write_json(directory / "folds.json", folds)
        pd.DataFrame(forecasts).to_csv(directory / "rankings.csv", index=False)
        oos.to_csv(directory / "oos_predictions.csv", index=False)
    features.to_csv(out_dir / "features.csv", index=False)
    write_jsonl(out_dir / "last_10_days.jsonl", [p for p in posts
                if as_of-pd.Timedelta(days=10) < utc(p["published_at"]) <= as_of and utc(p["available_at"]) <= as_of])
    ledger = read_jsonl(out_dir / "forecast_ledger.jsonl")
    existing = {(p["run_id"], p["ticker"]) for p in ledger}
    ledger += [p for p in forecasts if (p["run_id"], p["ticker"]) not in existing]
    write_jsonl(out_dir / "forecast_ledger.jsonl", ledger)
    write_json(out_dir / "forecast_evaluation.json", evaluate_saved(ledger, prices))
    payload = {"mode": mode, "as_of": as_of.isoformat(), "version": __version__,
               "sentiment": scorer.metadata, "forecasts": forecasts,
               "oos": oos.to_dict(orient="records"), "metrics": result_metrics,
               "folds": folds, "manifest": manifest}
    write_report(out_dir / "report.html", payload)
    return {"report": str((out_dir / "report.html").resolve()), "mode": mode,
            "forecasts": len(forecasts), "oos_forecasts": len(oos), "run_id": run_id}


def main(argv=None):
    parser = argparse.ArgumentParser(description="HengSeng sentiment research agent")
    parser.add_argument("--assets", default="config/assets.json")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Generate labelled synthetic inputs and a complete report")
    demo.add_argument("--data", default="data/demo")
    demo.add_argument("--out", default="outputs/demo")
    demo.add_argument("--seed", default=42, type=int)
    demo.add_argument("--end", default="2026-11-20")
    ingest = sub.add_parser("collect", help="Fetch 10 days through Apify/Exa and archive observations")
    ingest.add_argument("--data", default="data/live")
    ingest.add_argument("--sources", default="config/sources.json")
    ingest.add_argument("--preflight", action="store_true", help="Validate required keys/config without network calls")
    run = sub.add_parser("run", help="Analyse archived inputs; no paid calls")
    run.add_argument("--data", default="data/live")
    run.add_argument("--out", default="outputs/live")
    run.add_argument("--as-of", help="ISO timestamp with timezone; default now for live data")
    run.add_argument("--sentiment", choices=["lexicon", "transformer"], default="lexicon")
    check = sub.add_parser("evaluate", help="Score saved forecasts after their next-session bar arrives")
    check.add_argument("--forecasts", default="outputs/live/forecast_ledger.jsonl")
    check.add_argument("--prices", default="data/live/prices.csv")
    check.add_argument("--out", default="outputs/live/forecast_evaluation.json")
    args = parser.parse_args(argv)
    load_dotenv()
    try:
        assets = read_json(args.assets)
        if args.command == "demo":
            data = Path(args.data)
            if (data / "collection.json").exists() and read_json(data / "collection.json")["mode"] != "synthetic":
                raise ValueError("Refusing to overwrite live data with synthetic fixtures")
            as_of = generate(assets, data, end=args.end, seed=args.seed)
            print(analyse(data, args.out, assets, as_of=as_of))
        elif args.command == "collect":
            config = read_json(args.sources)
            preflight(config)
            if args.preflight:
                print("Local preflight passed. Actor access, costs and source coverage still require a live run.")
                return 0
            data = Path(args.data)
            if (data / "collection.json").exists() and read_json(data / "collection.json")["mode"] == "synthetic":
                raise ValueError("Use a separate data directory for live observations")
            manifest = collect(assets, config, data)
            fetch_prices(assets, data / "prices.csv")
            complete = all(r["meets_requirement"] for r in manifest["coverage"])
            print(f"Collection recorded. All assets have two social platforms + news: {complete}.")
            return 0 if complete and not manifest["failures"] else 2
        elif args.command == "run":
            print(analyse(args.data, args.out, assets, args.as_of, args.sentiment))
        elif args.command == "evaluate":
            rows = evaluate_saved(read_jsonl(args.forecasts), validate_prices(pd.read_csv(args.prices), assets))
            write_json(args.out, rows)
            print(f"Evaluated {sum(r['evaluation_status']=='evaluated' for r in rows)} / {len(rows)} forecasts.")
    except (ValueError, RuntimeError, FileNotFoundError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
