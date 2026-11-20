import copy
import pytest

from hengseng.common import utc
from hengseng.normalize import matches, merge_first_observations, normalize_row
from hengseng.sentiment import LexiconScorer


def test_utc_requires_timezone_and_converts():
    assert str(utc("2026-11-20T15:30:00+09:00")) == "2026-11-20 06:30:00+00:00"
    with pytest.raises(ValueError):
        utc("2026-11-20 15:30")


def test_aliases_do_not_match_substrings(assets):
    assert matches("看好騰訊", assets[0])
    assert matches("bullish $0700", assets[0])
    assert not matches("price is 10700", assets[0])
    assert not matches("NAVERish", assets[8])


def test_naver_board_scope_and_missing_counts(assets):
    row = {"type": "post", "stockCode": "005930", "postId": "1", "writtenAt": "2026-11-18T15:00:00+09:00",
           "title": "상승 호재", "text": "성장", "views": 20, "likes": 2}
    p = normalize_row(row, "naver", assets[5], "2026-11-20T08:00:00Z", "2026-11-10T00:00:00Z", "2026-11-20T08:00:00Z")
    assert p["followers"] is None and p["reposts"] is None
    assert p["likes"] == 2
    assert p["available_at"] != p["published_at"]
    assert normalize_row(row, "naver", assets[6], "2026-11-20T08:00:00Z", "2026-11-10T00:00:00Z", "2026-11-20T08:00:00Z") is None


def test_telegram_legacy_and_reactions(assets):
    row = {"username": "@public", "followers": 200,
           "message": {"fulldate": "2026-11-18T08:00:00Z", "description": "Tencent bullish", "views": 90,
                       "link": "https://t.me/public/12"}}
    p = normalize_row(row, "telegram", assets[0], "2026-11-20T08:00:00Z", "2026-11-10T00:00:00Z", "2026-11-20T08:00:00Z")
    assert p["followers"] == 200 and p["views"] == 90 and p["likes"] is None


def test_missing_news_date_is_rejected(assets):
    with pytest.raises(ValueError, match="timestamp"):
        normalize_row({"title": "Tencent growth", "url": "https://example.org"}, "exa", assets[0],
                      "2026-11-20T08:00:00Z", "2026-11-10T00:00:00Z", "2026-11-20T08:00:00Z")


def test_rerun_cannot_rewrite_text_or_engagement(synthetic):
    post = synthetic[3][0]
    revised = dict(post, text="revised future text", likes=999, observed_at="2026-12-01T00:00:00Z")
    result = merge_first_observations([post], [revised, copy.deepcopy(post)])
    assert len(result) == 1
    assert result[0]["likes"] == post["likes"]
    assert result[0]["text"] == post["text"]


@pytest.mark.parametrize("text,sign", [("bullish growth", 1), ("not bullish", -1),
                                       ("利好 盈利", 1), ("下跌 虧損", -1),
                                       ("상승 호재", 1), ("하락 적자", -1), ("meeting today", 0)])
def test_multilingual_baseline(text, sign):
    result = LexiconScorer().score([text])[0]
    assert result == sign


def test_telegram_profile_without_message_is_skipped(assets):
    row = {"username": "@public", "message": None}
    stamp = "2026-11-20T08:00:00Z"
    assert normalize_row(row, "telegram", assets[0], stamp, stamp, stamp) is None
