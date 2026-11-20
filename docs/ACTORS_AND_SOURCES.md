# Actor configuration and source references

Documentation reviewed November 20, 2026. These are **configured actors**, not a claim that paid runs were executed for this delivery.

| Source | Configured actor ID | Approach |
|---|---|---|
| LIHKG | `claude_code_reviewer/lihkg-scraper-en` | Search aliases, then fetch matching recent threads and replies |
| Naver | `hgservices/naver-stock-discussion-scraper` | Dedicated board for each Korean stock code with a date limit |
| Telegram | `crawl_craft/telegram-scraper` | Search aliases inside configured public channels, requesting the legacy message/profile output |
| News | Exa `/search` endpoint | Company/ticker query, news category, publication window, article text |

Actor availability, input schemas, pricing and site behavior can change. The defaults use the `latest` build tag to permit an initial run. On a successful live run, retain the resolved build ID and set the configuration to the provider’s corresponding immutable build number for later reproduction. The raw archive records exact inputs, actor/run/dataset/build IDs and content hashes. API fixture tests validate the integration logic, not the actors’ current live access or coverage.

Search and result caps can omit relevant content. LIHKG search focuses on newly created recent threads; replies on older threads are not exhaustively discovered. Full-thread replies without an explicit asset match are conservatively excluded. Naver dedicated-board context establishes the ticker even when text omits the company name. Telegram public previews may omit messages or counters, and private groups are out of scope. Exa results are a relevance-ranked sample with estimated publication dates and may contain updated pages; observation time prevents those retrieved versions from entering earlier forecasts.

## Primary references

- [LIHKG actor documentation](https://apify.com/claude_code_reviewer/lihkg-scraper-en)
- [Naver discussion actor documentation](https://apify.com/hgservices/naver-stock-discussion-scraper)
- [Telegram actor documentation](https://apify.com/crawl_craft/telegram-scraper)
- [Apify Run Actor API](https://docs.apify.com/api/v2/actors-runs-post)
- [Apify dataset items API](https://docs.apify.com/api/v2/dataset-items-get)
- [Exa Search API](https://exa.ai/docs/reference/search)
- [exchange-calendars](https://github.com/gerrymanoim/exchange_calendars)
- [yfinance](https://github.com/ranaroussi/yfinance)
- [Multilingual sentiment model card](https://huggingface.co/cardiffnlp/twitter-xlm-roberta-base-sentiment)

## Credentials

Only `APIFY_TOKEN` and `EXA_API_KEY` are required for collection. Tokens are read from the environment or an ignored `.env`; the project never puts them in request URLs or manifests. The assessment also mentions Tavily, but this implementation follows the Exa requirement. There is no Tavily integration or token to provide.

No credentials were supplied during development. To reproduce the live run, the assessor can use their own provider accounts or temporary scoped credentials shared through an agreed private channel. Do not paste working tokens into GitHub, README files, the public report or the submission email body.
