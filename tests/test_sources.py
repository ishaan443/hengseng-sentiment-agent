import httpx
import pytest

from hengseng.common import read_json
from hengseng.sources import ApifyRunner, SourceError, preflight, request


def config():
    return {"actors": {"telegram": {"id": "vendor/actor", "build": "0.1"}},
            "actor_timeout_seconds": 20, "max_charge_usd_per_actor_run": .25,
            "telegram_channels": {"HKEX": [], "KRX": []}}


def test_preflight_rejects_missing_keys_and_channels(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with pytest.raises(SourceError, match="APIFY_TOKEN.*EXA_API_KEY.*HKEX.*KRX"):
        preflight(config())


def test_apify_records_run_and_paginates(tmp_path):
    calls = []
    def handler(req):
        calls.append(req)
        if req.method == "POST":
            assert "maxTotalChargeUsd=0.25" in str(req.url)
            return httpx.Response(201, json={"data": {"id": "run1", "status": "SUCCEEDED", "buildId": "build1", "defaultDatasetId": "dataset1"}})
        offset = int(req.url.params.get("offset"))
        return httpx.Response(200, json=[{"id": i} for i in range(1000)] if offset == 0 else [{"id": 1000}])
    client = httpx.Client(transport=httpx.MockTransport(handler))
    runner = ApifyRunner("test-secret", tmp_path, config(), client)
    assert len(runner.run("telegram", {"urls": ["example"]})) == 1001
    assert len(calls) == 3
    manifest = read_json(tmp_path / "run1-run.json")
    assert manifest["build_id"] == "build1" and manifest["row_count"] == 1001
    assert "test-secret" not in (tmp_path / "run1-run.json").read_text()


def test_paid_actor_start_is_not_retried():
    count = 0
    def handler(req):
        nonlocal count
        count += 1
        return httpx.Response(503, json={"error": "failure"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceError):
            request(client, "POST", "https://api.apify.com/v2/actors/test/runs")
    assert count == 1


def test_actor_failure_is_not_silently_reported_as_success(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json={"data": {"id": "failed", "status": "FAILED"}})))
    runner = ApifyRunner("secret", tmp_path, config(), client)
    with pytest.raises(SourceError, match="FAILED"):
        runner.run("telegram", {})


def test_exa_and_social_collection_contract(tmp_path, monkeypatch, assets):
    import hengseng.sources as sources
    import pandas as pd
    from hengseng.common import read_jsonl
    monkeypatch.setenv("APIFY_TOKEN", "fake-apify")
    monkeypatch.setenv("EXA_API_KEY", "fake-exa")
    cfg = config()
    cfg.update(max_results_per_query=10, news_results_per_asset=2)
    cfg["telegram_channels"] = {"HKEX": ["public-hk"], "KRX": ["public-kr"]}
    real_client = httpx.Client
    monkeypatch.setattr(sources.httpx, "Client", lambda **kwargs: real_client(
        transport=httpx.MockTransport(lambda req: httpx.Response(500))))
    current = pd.Timestamp.now(tz="UTC")
    stamp = (current-pd.Timedelta(hours=1)).isoformat()
    monkeypatch.setattr(sources.ApifyRunner, "run", lambda self, source, args: (
        [{"type": "post", "stockCode": "005930", "postId": "one", "writtenAt": stamp,
          "title": "삼성전자 성장", "text": "호재", "likes": 2}]
        if source == "naver" else [{"channel": {"username": "public-kr"}, "id": 4,
                                   "date": stamp, "text": "Samsung Electronics bullish"}]))
    def mock_request(client, method, url, **kwargs):
        assert url == "https://api.exa.ai/search" and method == "POST"
        payload = kwargs["json"]
        assert payload["category"] == "news" and payload["numResults"] == 2
        assert payload["contents"]["text"]["maxCharacters"] == 6000
        assert payload["startPublishedDate"] < payload["endPublishedDate"]
        return {"results": [{"url": "https://example.org/news", "publishedDate": stamp,
                             "title": "Samsung Electronics earnings", "text": "strong growth"}]}
    monkeypatch.setattr(sources, "request", mock_request)
    manifest = sources.collect([assets[5]], cfg, tmp_path, now=current)
    assert manifest["coverage"][0]["meets_requirement"] is True
    assert {p["source"] for p in read_jsonl(tmp_path / "posts.jsonl")} == {"naver", "telegram", "exa"}
    assert manifest["failures"] == []
