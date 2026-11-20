# Finish and submit

## Already prepared

- Python package and CLI, ten-stock universe and two-platform social coverage design per exchange.
- Apify adapters and Exa news requests, raw archives, UTC normalization and data-quality gates.
- Multilingual baseline sentiment and optional transformer adapter.
- Calendar-aligned features, expanding OOS tests, two comparators and exact-session outcome checks.
- Synthetic visual report, rankings, metrics, folds and reproducibility manifests.
- Automated tests and GitHub Actions workflow.

## Required before describing this as a live completed assessment

1. Add working Apify/Exa credentials locally, review the configured public Telegram channels, and complete an actual collection. Inspect rejected records and all ten source-coverage rows.
2. Review actor costs and archive the real actor/build/run/dataset IDs. Do not replace the configured actor list with a statement that those actors were already used.
3. Open the live report and confirm price timestamps, missing fields, currency and source attribution. The initial live report will correctly abstain from a trained model because ten days is insufficient history.
4. Either provide a real, independently timestamped historical archive for meaningful OOS validation or explain that prospective evaluation is pending. Synthetic OOS results are a software demonstration only. It is better to submit that honest limitation than fabricate market performance.
5. The project repository is [ishaan443/hengseng-sentiment-agent](https://github.com/ishaan443/hengseng-sentiment-agent) (public). Keep API keys, `.env`, private channel data and raw posts out of Git. The supplied sample output is explicitly synthetic.
6. Replace the placeholders in the email draft below after reviewing the implementation. Submit the repository URL and reproducibility instructions. Share any required temporary credentials privately, and revoke them after the assessment.

## Email draft — fill in after the live checks

To: gilad@crowdwisdomtrading.com

Subject: AI Agents Developer Internship Assessment — HengSeng Sentiment Agent — Ishaan Dhanda

Hello Gilad,

Please find my HengSeng sentiment price prediction project here:

Repository: https://github.com/ishaan443/hengseng-sentiment-agent

The project covers five HKEX and five KRX assets, with LIHKG + Telegram for Hong Kong, Naver + Telegram for Korea, and Exa news. It includes a Python pipeline, an interactive report, source/run manifests, chronological walk-forward evaluation against persistence and price-only baselines, and a command to check stored forecasts against next-session outcomes.

Live collection status: [INSERT VERIFIED STATUS AND COLLECTION DATES]

Validation status: [DISTINGUISH REAL OOS RESULTS FROM THE INCLUDED SYNTHETIC DEMO]

The actor IDs and reproduction instructions are in docs/ACTORS_AND_SOURCES.md. Credentials can be supplied through an agreed private channel; they are not included in the repository.

Best regards,
Ishaan Dhanda

## Be ready to explain

Why predict returns and convert to price? Why is a random split inappropriate? Why can current engagement leak into a historical test? Why are ten days insufficient for a robust model? What does the unchanged-price baseline reveal? How are holidays, missing sessions and newly discovered old posts handled? How would you evaluate Korean/Cantonese sentiment quality? What remains untested live? Review and understand the code before presenting it, and describe assistance used honestly if asked.
