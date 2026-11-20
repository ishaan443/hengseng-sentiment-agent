# Data contracts

`data/live/posts.jsonl` is one normalized observation per line. Source payloads are separately retained in the raw archive. The pipeline freezes the first retained observation. Local JSONL/CSV storage is designed for a single writer; do not run concurrent collectors on the same directory.

| Field | Meaning |
|---|---|
| `id`, `source`, `ticker` | Stable source identity plus canonical asset identity |
| `exchange`, `kind` | HKEX/KRX; social/news |
| `text`, `url` | Clean text and source URL |
| `published_at` | Explicitly zoned publication time converted to UTC |
| `observed_at`, `available_at` | First retrieval time; no retrospective publication-time backfill |
| `engagement_observed_at` | Timestamp of the stored engagement snapshot |
| `likes`, `views`, `reposts`, `followers` | Nullable nonnegative counts; no invented zeros for missing values |
| `author_hash` | SHA-256-derived pseudonymous author key, or null |
| `sentiment` | Added by analysis; score from −1 to +1 |

The source window is inclusive at the start/end in collection and open on the lower bound in feature aggregation. Post timestamps lacking a timezone are rejected. Naver’s documented offset is already in its response. Articles with no publication timestamp are rejected and counted in the manifest. Relevance filters can reject valid articles lacking an exact alias; manually review rejected samples before production use.

Price CSV columns are `ticker,session,close_time,open,high,low,close,volume,stock_splits`. Session is the exchange-local date (`YYYY-MM-DD`); `close_time` must be the calendar’s UTC closing timestamp. `stock_splits` is zero when no event is reported. Imports must follow the same schema, use real finalized bars, and include the full asset universe. Do not silently forward-fill missing prices.

`features.csv` exposes every forecast-origin feature and label. `oos_predictions.csv` contains exchange, ticker, origin session, exact target session, fold, model, predicted/actual return and predicted/actual price. These results are always generated from later test dates.

`rankings.csv` is ordered by exchange, then descending social mentions and sentiment. The HTML can re-sort by sentiment or predicted return. `forecasts.json` includes the input cutoff, actual issue time, target close time, method/status, paper signal, descriptive error band and support/resistance. `forecast_ledger.jsonl` retains runs, and `forecast_evaluation.json` marks evaluated, pending or invalid late forecasts. Real and synthetic modes must use separate data/output directories.

`outputs/.../runs/<run_id>/` stores a run’s forecasts, configuration hashes, metrics and fold metadata. The ID is derived from the input/environment manifest. Latest convenience files in the output root can be replaced by the next run; retained runs and the forecast ledger preserve prior evidence.
