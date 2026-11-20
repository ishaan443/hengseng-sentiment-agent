# Methodology and known limits

## Information available at prediction time

Every normalized observation has `published_at`, `observed_at`, `available_at` and `engagement_observed_at` in UTC. Live collection assigns availability to first observation, not publication. An old post discovered today cannot affect yesterday’s forecast. The earliest text and engagement snapshot is frozen; later likes, followers and text edits cannot overwrite it. Duplicate IDs and exact text copies within a source, ticker and publication UTC day are collapsed.

At session close +15 minutes, the pipeline selects records available by the cutoff and published in the previous ten calendar days. It calculates one engagement-weighted mean per social platform, then an equally weighted mean across platforms. This reduces, but does not eliminate, high-volume-platform domination. Source disagreement and mention counts are retained. Exa news has a separate mean.

A record may legitimately mention multiple assets. The same text can therefore appear for more than one asset; all those assets are assigned to the same date fold within an exchange. Cross-platform copied text is not collapsed because provenance is preserved; this is a remaining sentiment inflation risk. Author hashes permit later spam controls; the current system does not claim to detect bots.

Missing likes, views, reposts and followers stay null, because these fields are not exposed consistently across the selected platforms. Missing likes are represented as a feature. Likes/reposts inform capped engagement weights. Views and followers are retained for inspection but excluded from the predictive model: their availability is inconsistent and channel subscribers are not necessarily personal-author followers. Telegram reactions are a generic engagement measure, not exclusively positive likes.

## Prices and target construction

The exchange-calendars package supplies XHKG and XKRX session times. A 15-minute allowance follows scheduled close to allow final bars/closing auctions to settle. The price collector excludes incomplete sessions. Missing sessions are reindexed before returns and targets are calculated, so the label cannot accidentally become a two-day forecast. Terminal rows have no label. Twenty-day support/resistance are observed high/low extrema, with no centered or future-looking window.

Features: one- and five-session returns, ten-session return volatility, intraday range, volume relative to its trailing mean, distance to support/resistance, social sentiment, news sentiment, log mention count, source dispersion, news count, number of social sources, log engagement, and missing engagement share.

Raw close-to-close price changes are the target, not dividend-adjusted total returns. Bars spanning a reported split are excluded and split-contaminated lag windows are disabled. Yahoo historical series may already contain retrospective adjustments, corrections or delisted-universe omissions. The included convenience feed is not a certified point-in-time archive. The ten-stock universe is fixed for this exercise and creates selection/survivorship bias; no index-wide performance claim is made.

## Validation protocol

1. Fit a pooled return model separately for HKEX and KRX. No cross-exchange information is shared.
2. Require 60 distinct eligible training dates. Assets do not count as additional independent dates.
3. Leave one date out between training and the next test block. Further remove labels whose endpoint is not strictly before the earliest test cutoff.
4. Test on up to 15 subsequent dates, with all eligible tickers from a date in the same block. Expand training and repeat. The final block may be shorter.
5. Fit StandardScaler and Ridge(alpha=10) only on the current training block. The model and feature specification are fixed, not selected using OOS outcomes.
6. Evaluate sentiment + price, price-only, and zero-return persistence on exactly the same test rows. Predictions are capped at ±20% consistently for all evaluation and inference.

Each block is an out-of-sample test at the time it is predicted. Earlier test outcomes may enter later training blocks. This is walk-forward evaluation, not a permanently untouched final holdout or a significance test. If iterating on features, reserve a new untouched future period; do not tune to these results.

The price-only comparator uses the same coverage-qualified dates as the sentiment model for comparability. This selection can favor periods with more social activity. The notebook-free workflow exports all fold boundaries and rows so that the choice can be audited. MAE/RMSE are reported per ticker; aggregate comparisons use return error, not raw currency units. Directional accuracy uses sign equality, excludes exactly zero realized returns, and treats the persistence forecast as neutral. It is not a profitable-trading metric.

## Forecasts, bands and positions

A final research model is trained only on labels available before the current cutoff. Ten distinct prior OOS dates are required for a historical absolute-error estimate. The band is the model’s predicted return ± the pooled exchange’s 90th-percentile absolute OOS residual. Serial dependence, regime changes and uneven volatility mean this is **not calibrated conformal coverage**.

The paper signal is LONG only if the lower return band is above +0.2%, SHORT only if the upper band is below −0.2%, otherwise FLAT. This intentionally conservative illustrative rule is not an executed strategy. There is no backtested equity curve, transaction-cost model, borrow availability check or claimed Sharpe ratio. Actual holdings are unavailable.

If requirements are unmet, the system abstains from a trained forecast, labels the method `persistence_fallback`, sets the position FLAT, and reports the exact reason. Unchanged-price estimates remain numerically available without pretending that a model was validated.

## What the delivered demonstration establishes

The seeded generator supplies fabricated prices and EN/ZH/KO messages with a weak known relationship to future fabricated returns. It is a software fixture, not a study of financial markets. As generated on November 20, 2026:

| Market | OOS rows per method | Persistence MAE (bps) | Price-only MAE (bps) | Sentiment + price MAE (bps) |
|---|---:|---:|---:|---:|
| HKEX | 1,105 | 108.65 | 109.59 | 110.33 |
| KRX | 1,090 | 102.73 | 103.14 | 103.63 |

These values are taken from the supplied `sample_output/oos_predictions.csv`. Sentiment does not beat persistence in this fixture. That negative result is retained. There are 30 walk-forward folds across the two markets and 2,195 distinct stock-date OOS forecasts for each model; 6,585 rows include all three comparators. The ten final n+1 forecasts remain pending until a next-session observation exists. Their paper positions are all FLAT.

## Next experiments

Accumulate at least several months of prospective observations, with daily coverage monitoring. Hand-label a balanced sample of Chinese/Cantonese, Korean and English posts, including slang, negation, sarcasm and multi-entity texts. Evaluate sentiment macro-F1 separately by language/source before replacing the transparent baseline. The optional XLM-R model is an adapter, not proof of local-language finance accuracy. Try changes only on training/validation periods, record the experiment count, and preserve a future holdout. Measure incremental return error and uncertainty before considering an executable strategy.
