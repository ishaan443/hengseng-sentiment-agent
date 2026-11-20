import pandas as pd
import pytest

from hengseng.features import ALL_FEATURES, build_features, sentiment_snapshot
from hengseng.model import evaluate_saved, forecast_latest, time_folds, training_rows, walk_forward
from hengseng.prices import next_session, validate_prices


@pytest.fixture(scope="module")
def frame(synthetic, assets):
    _, end, prices, posts = synthetic
    return build_features(prices, posts, assets, end)


def test_exchange_next_session_skips_weekend(assets):
    assert next_session(assets[0], "2026-11-20")[0] == "2026-11-23"
    assert next_session(assets[5], "2026-11-20")[0] == "2026-11-23"


def test_hong_kong_holiday_skipped(assets):
    assert next_session(assets[0], "2026-12-24")[0] == "2026-12-28"


def test_last_bar_is_not_a_zero_return_label(frame):
    last = frame.sort_values("session").groupby("ticker").tail(1)
    assert last.target_return.isna().all()
    assert last.actual_next_close.isna().all()


def test_price_gaps_do_not_extend_prediction_horizon(synthetic, assets):
    _, end, prices, posts = synthetic
    ticker = assets[0]["ticker"]
    day = prices[prices.ticker == ticker].session.iloc[40]
    damaged = prices[~((prices.ticker == ticker) & (prices.session == day))]
    features = build_features(damaged, posts, assets, end)
    preceding = features[(features.ticker == ticker) & (features.target_session == day)]
    assert len(preceding) == 1 and preceding.target_return.isna().all()


def test_future_posts_do_not_change_past_features(synthetic, assets):
    _, end, prices, posts = synthetic
    cutoff = pd.Timestamp("2026-01-15T08:15:00Z")
    base = build_features(prices, posts, assets, cutoff)
    future = dict(posts[0], id="future", text="bullish", sentiment=1.0,
                  published_at="2026-01-16T01:00:00Z", observed_at="2026-01-16T02:00:00Z",
                  available_at="2026-01-16T02:00:00Z", engagement_observed_at="2026-01-16T02:00:00Z")
    other = build_features(prices, posts+[future], assets, cutoff)
    pd.testing.assert_frame_equal(base, other)


def test_backfilled_content_is_not_available_at_publication(synthetic):
    post = dict(synthetic[3][0], published_at="2026-01-14T01:00:00Z",
                available_at="2026-01-16T01:00:00Z", observed_at="2026-01-16T01:00:00Z")
    assert sentiment_snapshot([post], "2026-01-15T08:15:00Z")["mentions"] == 0
    assert sentiment_snapshot([post], "2026-01-16T08:15:00Z")["mentions"] == 1


def test_future_prices_do_not_change_historical_forecast_features(synthetic, assets):
    _, _, prices, posts = synthetic
    cutoff = pd.Timestamp("2026-01-15T08:15:00Z")
    base = build_features(prices, posts, assets, cutoff)
    changed = prices.copy()
    mask = changed.session > "2026-01-15"
    changed.loc[mask, ["open", "high", "low", "close"]] *= 100
    other = build_features(changed, posts, assets, cutoff)
    pd.testing.assert_frame_equal(base, other)


def test_fold_dates_group_all_assets_and_purge_labels(frame):
    eligible = training_rows(frame)
    for _, universe in eligible.groupby("exchange"):
        folds = list(time_folds(universe))
        assert folds
        for train, test in folds:
            assert set(train.session).isdisjoint(test.session)
            assert train.label_end.max() < test.cutoff.min()
            assert train.session.max() < test.session.min()
            assert test.groupby("session").ticker.nunique().eq(5).all()
            dates = sorted(universe.session.unique())
            assert dates.index(test.session.min())-dates.index(train.session.max()) >= 2


def test_ten_days_cannot_be_presented_as_validated(frame):
    short = frame[frame.session >= sorted(frame.session.unique())[-8]]
    oos, folds = walk_forward(short)
    assert oos.empty and folds == []
    forecasts = forecast_latest(short, oos, pd.Timestamp("2026-03-31T08:15:00Z"))
    assert all(p["forecast_method"] == "persistence_fallback" for p in forecasts)
    assert all(p["paper_position"] == "FLAT" for p in forecasts)


def test_one_social_source_fails_required_coverage(synthetic):
    posts = [p for p in synthetic[3] if p["source"] in {"telegram", "exa"}]
    result = sentiment_snapshot(posts, synthetic[1])
    assert not result["coverage_ok"]


def test_predict_and_check_ledger_uses_exact_target_date():
    p = {"ticker": "A", "target_session": "2026-11-23", "issued_at": "2026-11-20T08:15:00Z",
         "target_close_time": "2026-11-23T08:00:00Z", "latest_close": 100.,
         "predicted_price": 102., "predicted_return": .02}
    prices = pd.DataFrame([{"ticker": "A", "session": "2026-11-23", "close": 103.}])
    r = evaluate_saved([p], prices)[0]
    assert r["actual_price"] == 103 and r["absolute_error"] == 1
    assert r["direction_correct"]
    assert evaluate_saved([dict(p, target_session="2026-11-24")], prices)[0]["evaluation_status"] == "pending"
    late = dict(p, issued_at="2026-11-23T09:00:00Z")
    assert evaluate_saved([late], prices)[0]["evaluation_status"] == "invalid_late_forecast"


def test_invalid_calendar_bar_rejected(synthetic, assets):
    prices = synthetic[2].copy()
    prices.loc[0, "close_time"] = "2025-09-01T10:00:00Z"
    with pytest.raises(ValueError, match="calendar"):
        validate_prices(prices, assets)


def test_future_engagement_cannot_enter_old_features(synthetic, assets):
    _, end, prices, posts = synthetic
    poisoned = dict(posts[0], engagement_observed_at="2027-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="Engagement"):
        build_features(prices, [poisoned], assets, end)
