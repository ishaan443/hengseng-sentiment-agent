"""Fixed-specification models; date-grouped expanding walk-forward evaluation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import ALL_FEATURES, PRICE_FEATURES

MIN_TRAIN_DATES = 60
MIN_TEST_DATES = 10
TEST_BLOCK = 15
GAP_DATES = 1


def estimator():
    # Fixed before seeing OOS results; fit preprocessing separately inside every fold.
    return make_pipeline(StandardScaler(), Ridge(alpha=10.0))


def training_rows(frame):
    return frame[frame.coverage_ok & frame.target_return.notna()].dropna(subset=ALL_FEATURES).copy()


def time_folds(frame, min_train=MIN_TRAIN_DATES, block=TEST_BLOCK, gap=GAP_DATES):
    dates = sorted(frame.session.unique())
    for start in range(min_train + gap, len(dates), block):
        test_dates = dates[start:start+block]
        test = frame[frame.session.isin(test_dates)]
        first_cutoff = test.cutoff.min()
        # All assets share a date group; a second purge enforces label availability.
        train = frame[frame.session.isin(dates[:start-gap]) & (frame.label_end < first_cutoff)]
        if train.session.nunique() >= min_train:
            yield train, test


def metrics(oos):
    if oos.empty:
        return []
    results = []
    for (exchange, ticker, model), group in oos.groupby(["exchange", "ticker", "model"]):
        error = group.pred_return-group.actual_return
        price_error = group.predicted_price-group.actual_price
        nonzero = group.actual_return.abs() > 1e-12
        results.append({"exchange": exchange, "ticker": ticker, "model": model,
            "n": len(group), "return_mae": float(error.abs().mean()),
            "return_rmse": float(np.sqrt(np.mean(error**2))),
            "price_mae": float(price_error.abs().mean()),
            "price_rmse": float(np.sqrt(np.mean(price_error**2))),
            "direction_accuracy": float((np.sign(group.loc[nonzero, "pred_return"]) ==
                                         np.sign(group.loc[nonzero, "actual_return"])).mean()) if nonzero.any() else None})
    return results


def walk_forward(frame):
    predictions, audit = [], []
    for exchange, universe in training_rows(frame).groupby("exchange"):
        for fold, (train, test) in enumerate(time_folds(universe), 1):
            audit.append({"exchange": exchange, "fold": fold, "train_rows": len(train),
                          "train_dates": train.session.nunique(), "train_end": train.session.max(),
                          "max_label_end": train.label_end.max().isoformat(),
                          "test_start": test.session.min(), "test_end": test.session.max(),
                          "min_test_cutoff": test.cutoff.min().isoformat(), "test_rows": len(test)})
            for name, columns in (("sentiment_ridge", ALL_FEATURES), ("price_only_ridge", PRICE_FEATURES),
                                  ("persistence", None)):
                pred = estimator().fit(train[columns], train.target_return).predict(test[columns]) if columns else np.zeros(len(test))
                # Guard pathological outputs consistently in OOS and live prediction.
                pred = np.clip(pred, -0.20, 0.20)
                for (_, row), value in zip(test.iterrows(), pred):
                    predictions.append({"exchange": exchange, "ticker": row.ticker, "session": row.session,
                        "target_session": row.target_session, "fold": fold, "model": name,
                        "pred_return": float(value), "actual_return": row.target_return,
                        "predicted_price": float(row.close*(1+value)), "actual_price": row.actual_next_close,
                        "cutoff": row.cutoff.isoformat()})
    return pd.DataFrame(predictions), audit


def forecast_latest(frame, oos, issued_at):
    records = []
    labelled = training_rows(frame)
    for _, row in frame.sort_values("session").groupby("ticker").tail(1).iterrows():
        train = labelled[(labelled.exchange == row.exchange) & (labelled.label_end < row.cutoff)
                         & (labelled.session < row.session)]
        own_oos = oos[(oos.exchange == row.exchange) & (oos.model == "sentiment_ridge") &
                      (oos.target_session < row.session)] if not oos.empty else pd.DataFrame()
        reason = "validated_research_model"
        if not row.coverage_ok:
            reason = "insufficient_sources"
        elif row[ALL_FEATURES].isna().any():
            reason = "insufficient_price_history"
        elif train.session.nunique() < MIN_TRAIN_DATES:
            reason = "insufficient_training_history"
        elif own_oos.empty or own_oos.session.nunique() < MIN_TEST_DATES:
            reason = "insufficient_oos_history"
        ready = reason == "validated_research_model"
        value = float(np.clip(estimator().fit(train[ALL_FEATURES], train.target_return)
                      .predict(pd.DataFrame([row[ALL_FEATURES]]))[0], -0.2, 0.2)) if ready else 0.0
        # Descriptive historical error band, NOT a calibrated coverage guarantee.
        q = float(np.quantile(np.abs(own_oos.pred_return-own_oos.actual_return), .9)) if ready else None
        lo, hi = (float(row.close * (1+value-q)), float(row.close*(1+value+q))) if q is not None else (None, None)
        position = "FLAT"
        if ready and q is not None:
            if value-q > 0.002:
                position = "LONG"
            elif value+q < -0.002:
                position = "SHORT"
        records.append({"ticker": row.ticker, "name": row["name"], "exchange": row.exchange,
            "currency": row.currency, "session": row.session, "cutoff": row.cutoff.isoformat(),
            "issued_at": issued_at.isoformat(), "target_session": row.target_session,
            "target_close_time": row.target_close_time.isoformat(), "latest_close": float(row.close),
            "predicted_price": float(row.close*(1+value)), "predicted_return": value,
            "forecast_method": "sentiment_ridge" if ready else "persistence_fallback",
            "status": reason, "direction": "UP" if value > .001 else "DOWN" if value < -.001 else "FLAT",
            "paper_position": position, "position_is_actual": False,
            "error_band_low": lo, "error_band_high": hi,
            "support": float(row.support) if pd.notna(row.support) else None,
            "resistance": float(row.resistance) if pd.notna(row.resistance) else None,
            "social_sentiment": float(row.social_sentiment), "news_sentiment": float(row.news_sentiment),
            "mentions": int(row.mentions), "news_count": int(row.news_count),
            "source_count": int(row.source_count), "source_scores": row.source_scores,
            "training_dates": int(train.session.nunique())})
    return records


def evaluate_saved(forecasts, prices):
    actuals = {(str(r.ticker), str(r.session)[:10]): r for r in prices.itertuples()}
    out = []
    for p in forecasts:
        r = actuals.get((p["ticker"], p["target_session"]))
        result = dict(p, evaluation_status="pending", actual_price=None, absolute_error=None,
                      absolute_return_error=None, direction_correct=None)
        if pd.Timestamp(p["issued_at"]) >= pd.Timestamp(p["target_close_time"]):
            result["evaluation_status"] = "invalid_late_forecast"
        elif r is not None:
            actual_return = r.close/p["latest_close"]-1
            result.update(evaluation_status="evaluated", actual_price=float(r.close),
                          absolute_error=abs(p["predicted_price"]-float(r.close)),
                          absolute_return_error=abs(p["predicted_return"]-actual_return),
                          direction_correct=bool(np.sign(p["predicted_return"]) == np.sign(actual_return)))
        out.append(result)
    return out
