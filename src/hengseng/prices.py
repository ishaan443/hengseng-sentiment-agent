from __future__ import annotations

from pathlib import Path
import exchange_calendars as xcals
import pandas as pd
import numpy as np

from .common import utc


def schedule(asset, start, end):
    calendar = xcals.get_calendar(asset["calendar"])
    return calendar.schedule.loc[str(start)[:10]:str(end)[:10]].copy()


def next_session(asset, session):
    cal = xcals.get_calendar(asset["calendar"])
    nxt = cal.next_session(pd.Timestamp(session).tz_localize(None))
    return nxt.date().isoformat(), cal.session_close(nxt)


def validate_prices(frame, assets):
    required = {"ticker", "session", "open", "high", "low", "close", "volume", "close_time"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Price columns missing: {sorted(required-set(frame.columns))}")
    frame = frame.copy()
    known = {a["ticker"]: a for a in assets}
    if not set(frame.ticker).issubset(known):
        raise ValueError("Price file contains unknown tickers")
    if frame.duplicated(["ticker", "session"]).any():
        raise ValueError("Duplicate price bar")
    frame["close_time"] = frame.close_time.map(utc)
    frame["session"] = frame.session.astype(str).str[:10]
    numeric = ["open", "high", "low", "close", "volume"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(frame[numeric].to_numpy()).all():
        raise ValueError("Non-finite price data")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any() or (frame.volume < 0).any():
        raise ValueError("Invalid price or volume")
    if ((frame.high < frame[["open", "close", "low"]].max(axis=1)) |
            (frame.low > frame[["open", "close"]].min(axis=1))).any():
        raise ValueError("Inconsistent OHLC bar")
    for ticker, group in frame.groupby("ticker"):
        sched = schedule(known[ticker], group.session.min(), group.session.max())
        expected = {day.date().isoformat(): utc(row.close) for day, row in sched.iterrows()}
        for r in group.itertuples():
            if r.session not in expected or utc(r.close_time) != expected[r.session]:
                raise ValueError(f"Bar does not match exchange calendar: {ticker} {r.session}")
    if "stock_splits" not in frame:
        frame["stock_splits"] = 0.0
    return frame.sort_values(["ticker", "session"]).reset_index(drop=True)


def fetch_prices(assets, destination, days=540, now=None):
    import yfinance as yf
    now = utc(now or pd.Timestamp.now(tz="UTC"))
    start = (now-pd.Timedelta(days=days)).date().isoformat()
    end = (now+pd.Timedelta(days=1)).date().isoformat()
    rows, errors = [], []
    for asset in assets:
        try:
            raw = yf.Ticker(asset["ticker"]).history(start=start, end=end, interval="1d",
                                                    auto_adjust=False, actions=True, raise_errors=True)
            if raw.empty:
                raise ValueError("empty response")
            sched = schedule(asset, start, end)
            closes = {d.date().isoformat(): utc(r.close) for d, r in sched.iterrows()}
            for stamp, r in raw.iterrows():
                day = stamp.date().isoformat()
                if day not in closes or closes[day] + pd.Timedelta(minutes=15) > now:
                    continue
                rows.append({"ticker": asset["ticker"], "session": day,
                             "close_time": closes[day].isoformat(),
                             **{field: float(r[field.title()]) for field in ["open", "high", "low", "close", "volume"]},
                             "stock_splits": float(r.get("Stock Splits", 0))})
        except Exception as exc:
            errors.append(f"{asset['ticker']}: {type(exc).__name__}")
    if errors:
        raise ValueError("Price fetch incomplete; existing CSV preserved. " + "; ".join(errors))
    result = validate_prices(pd.DataFrame(rows), assets)
    destination = Path(destination)
    if destination.exists():
        previous = validate_prices(pd.read_csv(destination), assets)
        # Historical bars used in an earlier experiment remain frozen.
        result = pd.concat([previous, result]).drop_duplicates(["ticker", "session"], keep="first")
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(destination, index=False)
    return result
