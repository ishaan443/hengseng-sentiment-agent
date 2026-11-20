# Verification record

Verified on November 20, 2026 using Python 3.12. Direct package versions are in `requirements-tested.txt`; report manifests record the analysis dependency versions and source hash.

| Check | Outcome |
|---|---|
| `python -m pytest -q` | 31 passed; one deprecation warning from the environment’s AnyIO pytest plugin |
| `hengseng demo` | Completed: ten final forecasts, 6,585 OOS rows including three comparators, 30 folds |
| Synthetic labelling | Present in source data, manifest and prominent dashboard notice |
| Leakage controls | Tested: future posts/prices, observation time, engagement snapshot, fold label endpoints |
| Exchange alignment | Tested: UTC offsets, weekend, Hong Kong holiday, missing session, invalid bar |
| Source contracts | Tested with mocked responses: Apify pagination/failure, no duplicate paid-start retry, Exa request shape, two-social-source + news coverage |
| Outcome checking | Tested: exact target date, pending target, rejected late forecast |
| HTML behavior | jsdom checks passed for all ten rows, five-stock exchange filters, sentiment sorting, two chart traces, fold table and no script errors |
| Offline dashboard | No external resource URLs are loaded by the HTML |
| Live Apify/Exa requests | Not executed; no user tokens or channel list supplied |
| Optional transformer | Adapter implemented; model download/inference not executed |
| Visual browser rendering | Local Chromium launch was blocked by this environment’s process/socket restrictions; DOM behavior was checked instead |
| GitHub/email | Private repository: https://github.com/ishaan443/hengseng-sentiment-agent; no message sent |

No test outcome establishes live data coverage, sentiment accuracy or profitable forecasting. The negative synthetic baseline comparison is retained in the report.
