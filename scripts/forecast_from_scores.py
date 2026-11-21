"""Issue a prospective sentiment benchmark using only published aggregate evidence."""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main(folder):
    with (folder / "historical_baseline.csv").open() as file:
        history = list(csv.DictReader(file))
    scores = {r["ticker"]: r for r in json.loads((folder / "scores.json").read_text())}
    now = datetime.now(timezone.utc)
    rows = []
    for line in (folder / "forecast_ledger.jsonl").read_text().splitlines():
        baseline = json.loads(line)
        if now >= datetime.fromisoformat(baseline["target_close_time"]):
            raise ValueError("Target close has passed. Preserve the original ledger.")
        ticker = baseline["ticker"]
        score = scores[ticker]
        recent = sorted((r for r in history if r["ticker"] == ticker),
                        key=lambda r: datetime.strptime(r["target"], "%b %d, %Y"), reverse=True)[:20]
        assert len(recent) == 20 and all(float(r["baseline"]) > 0 for r in recent)
        scale = sum(abs(float(r["actual_close"]) / float(r["baseline"]) - 1) for r in recent) / len(recent)
        valid = len(score["source_scores"]) >= 2 and score["social_sentiment"] is not None
        change = scale * score["social_sentiment"] if valid else None
        rows.append(dict(ticker=ticker, currency=baseline["currency"], issued_at=now.isoformat(),
                         session=baseline["session"], target_session=baseline["target_session"],
                         target_close_time=baseline["target_close_time"], latest_close=baseline["latest_close"],
                         predicted_price=baseline["latest_close"] * (1 + change) if valid else None,
                         forecast_method="experimental_sentiment_rule", predicted_return=change,
                         direction=("UP" if change > 0 else "DOWN" if change < 0 else "FLAT") if valid else None,
                         mean_abs_daily_return=scale, social_sentiment=score["social_sentiment"],
                         source_scores=score["source_scores"], paper_position="FLAT",
                         status="issued" if valid else "abstained_insufficient_sources"))
    with (folder / "sentiment_forecasts.jsonl").open("x") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
