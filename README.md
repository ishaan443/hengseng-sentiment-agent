# HengSeng Sentiment Price Prediction Agent

A Python research pipeline for five HKEX and five KRX stocks. It combines two social platforms per exchange with Exa news, predicts the next trading session’s closing price, and produces an offline interactive report.

**Delivery status:** the code, synthetic demonstration, chronological evaluation, tests and report are complete. **Live Apify/Exa collection has not been run.** API credentials and a curated public Telegram channel list are required. The project repository is [ishaan443/hengseng-sentiment-agent](https://github.com/ishaan443/hengseng-sentiment-agent) (private). No assessment email has been sent. The supplied numbers are synthetic, including prices.

## Start here

Requires Python 3.11 or later. Run commands from this directory.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,live]'
python -m pytest -q
hengseng demo
```

On Windows, activate with `.venv\Scripts\activate`. Open `outputs/demo/report.html` in a browser. A pre-generated copy is included under `sample_output/report.html`, with rankings, model metrics and the forecast ledger. The dashboard works offline, supports exchange filters and ranking controls, and exports a CSV.

The demo uses seed 42 and simulated history from September 2025 to November 20, 2026. That longer history exists only to exercise out-of-sample evaluation. The report’s sentiment features always use a trailing **10-calendar-day** window. Demo results are not evidence about actual stocks.

## Coverage

| Exchange | Assets | Social platform 1 | Social platform 2 | News |
|---|---|---|---|---|
| HKEX | Tencent 0700.HK, Alibaba 9988.HK, HSBC 0005.HK, Meituan 3690.HK, Xiaomi 1810.HK | LIHKG | Public Telegram channels | Exa |
| KRX | Samsung Electronics 005930.KS, SK hynix 000660.KS, Hyundai Motor 005380.KS, NAVER 035420.KS, LG Chem 051910.KS | Naver stock discussion boards | Public Telegram channels | Exa |

The assignment is interpreted as covering Hong Kong and South Korea because it lists sources for those markets. Exa supplements the two social platforms; it is not counted as one of them. Tickers, cashtags, local-language company names and English aliases are configured in `config/assets.json`.

## Run against live sources

1. Copy `.env.example` to `.env` and set `APIFY_TOKEN` and `EXA_API_KEY` locally.
2. Add relevant public channel usernames/URLs under both `telegram_channels.HKEX` and `telegram_channels.KRX` in `config/sources.json`. Verify the channels actually discuss the selected stocks. Empty lists deliberately fail preflight rather than substituting irrelevant channels.
3. Review the actor configuration and your API budgets. The defaults cap each actor run and request volume. There can be up to 25 actor starts per collection, plus 10 Exa searches. Per-run caps are not an overall account spending cap; configure that in the provider account too. Search caps mean the scrape is a bounded sample, not an exhaustive archive.
4. Run the commands below. No credentials are needed for the demo; collection invokes paid services when configured.

```bash
cp .env.example .env
# Edit .env and config/sources.json before continuing.
hengseng collect --preflight
hengseng collect --data data/live
hengseng run --data data/live --out outputs/live
```

The collector saves original actor inputs, run IDs, build IDs, dataset IDs, raw responses, rejection reasons and coverage. An incomplete collection returns exit code 2 but keeps any successful records. Inspect `data/live/collection.json`; do not claim the two-source requirement passed unless every asset has `meets_requirement: true`. `run` can still produce a report from partial archived inputs if prices are present.

Live prices use `yfinance` as a research convenience. Existing historical bars are retained on subsequent fetches. For higher-assurance work, replace the CSV with a licensed point-in-time price feed following the documented schema. No live quote is presented as a closing-price observation.

### Sentiment backends

The default `lexicon` backend is a transparent EN/ZH/KO baseline. It has no model downloads and is used in the runnable demo. It is **not a validated finance sentiment model**. An optional transformer backend is implemented:

```bash
python -m pip install -e '.[nlp]'
hengseng run --sentiment transformer
```

The transformer adapter uses `cardiffnlp/twitter-xlm-roberta-base-sentiment`, records the resolved revision, and supports pinning `SENTIMENT_REVISION`. The optional model was not downloaded or executed in this delivery. Its sentiment fine-tuning languages do not include Chinese or Korean; evaluate both local languages and finance slang before drawing conclusions. Neither backend handles sarcasm, investment horizons or multi-company target attribution reliably.

## Prediction and validation

For each stock, the decision cutoff is the exchange’s scheduled session close plus 15 minutes. The target is:

```text
y[t] = close[next_exchange_session] / close[t] - 1
predicted_price[t+1] = close[t] * (1 + predicted_return[t])
```

`n+1` means the next **exchange trading session**, accounting for holidays. It does not mean tomorrow’s calendar date. This is a forecast issued after the close; it does not assume an executable trade at that closing price.

Two separate Ridge models are fitted per exchange: sentiment + price features, and a price-only comparator. The unchanged-price forecast is a third baseline. Model settings are fixed in advance. Expanding walk-forward folds group all stocks by session date, leave one date unused between training and testing, and purge any training label not known before the first test cutoff. Each scaler is fitted only on its training fold. No random train/test split is used.

The learned forecast requires at least 60 eligible training dates, 10 prior OOS test dates, two social platforms and news. Until then, the report explicitly uses `persistence_fallback`, with price unchanged and paper position FLAT. Ten days of newly collected history cannot meet those validation requirements. Collect prospectively or supply independently archived, timestamped observations; do not backdate new scrapes to manufacture a historical test.

Outputs include per-stock price MAE/RMSE, return MAE/RMSE, directional accuracy, fold boundaries and individual OOS predictions. Return errors allow comparison across currencies. Pooled price MAE across HKD and KRW is intentionally avoided. The dashboard also shows a descriptive 90th-percentile historical error band, which has no guaranteed coverage.

Paper LONG/SHORT signals require the entire error band to clear ±20 basis points. They are illustrative, carry no claim about transaction costs, and never place an order. No actual portfolio position is known.

### Check forecasts when outcomes arrive

```bash
hengseng collect --data data/live
hengseng evaluate --forecasts outputs/live/forecast_ledger.jsonl \
  --prices data/live/prices.csv --out outputs/live/forecast_evaluation.json
hengseng run --data data/live --out outputs/live
```

The immutable run directories and append-only forecast ledger preserve previously issued forecasts. Evaluation joins the exact target session and keeps unresolved forecasts pending. A live historical replay uses the actual wall-clock issue time; it cannot create a valid past live forecast merely by setting `--as-of`.

## Project layout

```text
config/                  Assets, aliases, actor IDs, channel configuration
src/hengseng/sources.py   Apify runs, pagination, Exa queries, raw archives
src/hengseng/normalize.py Entity matching, UTC timestamps, first-snapshot deduplication
src/hengseng/sentiment.py Lexicon and optional transformer backends
src/hengseng/prices.py    Price ingestion and exchange calendar validation
src/hengseng/features.py Point-in-time price and sentiment features
src/hengseng/model.py    Walk-forward tests, baselines, forecasts, outcome checks
src/hengseng/report.py   Standalone dashboard renderer
src/hengseng/cli.py      Commands and run manifests
tests/                   Leakage, normalization, calendar, API and evaluation tests
docs/                    Methodology, schemas, actor references and submission guide
sample_output/           Generated synthetic report and audit artifacts
```

## Before submission

Read `docs/SUBMISSION_CHECKLIST.md` and `docs/METHODOLOGY.md`. Replace synthetic-only evidence with an honest live collection report after configuring credentials. Keep `.env`, raw user content and tokens out of Git. Share the repository URL and actor/run/build identifiers. Provide narrowly scoped, temporary reproduction credentials privately if the assessor requires them; never commit them to the repository.

The assessment email mentions Tavily, but the technical scope explicitly requests Exa. This implementation uses Apify and Exa and does not require a Tavily token.
