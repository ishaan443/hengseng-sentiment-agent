"""Export aggregate collection evidence and a dashboard for a public workflow run."""
import json
import os
from pathlib import Path
from shutil import copyfile

from hengseng.report import write_report


def main():
    collection = json.loads(Path("data/live/collection.json").read_text())
    out = Path("public-results")
    out.mkdir(exist_ok=True)
    summary = {k: collection[k] for k in ("start", "end", "coverage")}
    summary["failed_requests"] = len(collection["failures"])
    (out / "coverage.json").write_text(json.dumps(summary, indent=2))
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as report:
        print("## Live source coverage", file=report)
        print(f"Window: {summary['start']} to {summary['end']} (UTC).", file=report)
        print("| Ticker | Social platforms | News items | Meets coverage |", file=report)
        print("| --- | --- | ---: | --- |", file=report)
        for row in summary["coverage"]:
            sources = ", ".join(row["social_sources"]) or "None"
            print(f"| {row['ticker']} | {sources} | {row['news']} | {row['meets_requirement']} |", file=report)

    results = Path("outputs/live")
    if (results / "report.html").exists():
        # Rebuild from aggregate outputs. Raw actor runs and dataset identifiers stay on the runner.
        manifest = json.loads((results / "manifest.json").read_text())
        import pandas as pd
        try:
            oos = pd.read_csv(results / "oos_predictions.csv").to_dict(orient="records")
        except pd.errors.EmptyDataError:
            oos = []
        payload = {k: manifest[k] for k in ("mode", "as_of", "sentiment")}
        payload.update(version=manifest["pipeline_version"], manifest=summary, oos=oos)
        for name in ("forecasts", "metrics", "folds"):
            payload[name] = json.loads((results / f"{name}.json").read_text())
        write_report(out / "report.html", payload)
        copyfile(results / "rankings.csv", out / "rankings.csv")


if __name__ == "__main__":
    main()
