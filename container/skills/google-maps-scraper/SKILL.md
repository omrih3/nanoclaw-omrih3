---
name: google-maps-scraper
description: Find businesses, places, ratings, reviews, phone numbers, websites, addresses and emails from Google Maps (e.g. "restaurants near X", "hotels in Y", "pharmacies in Z"). Uses the local open-source gosom/google-maps-scraper binary baked into the container. Use for any place/business search or review collection on Google Maps.
allowed-tools: Bash(gmaps-scrape:*), Bash(timeout:*), Read, Write
---

# Google Maps scraper (gosom/google-maps-scraper v1.18.1)

Scrapes Google Maps with a headless browser, locally in the container. Not an official API: results can vary or get blocked, so say data is indicative. Source: https://github.com/gosom/google-maps-scraper

Run it via the `gmaps-scrape` wrapper (sets Playwright paths; do NOT use Docker, it is not available here). No proxy is configured; do not ask the user for proxy credentials.

## Run

1. Write one search query per line (query + location, in the user's wording or the local language) to `/workspace/agent/gmaps/queries.txt`.
2. Run (always with a timeout, start small):
```bash
mkdir -p /workspace/agent/gmaps
timeout 300 gmaps-scrape -input /workspace/agent/gmaps/queries.txt \
  -results /workspace/agent/gmaps/results.csv \
  -depth 1 -c 2 -lang en -exit-on-inactivity 90s >/workspace/agent/gmaps/run.log 2>&1
```
The scraper logs a lot: always redirect output as above and only `tail -5` the log on failure. Typical run: ~1 minute for ~15 places.
3. Read the CSV (`title, category, address, website, phone, review_count, review_rating, latitude, longitude, ...`) and report the top results concisely: name, rating (review count), address, phone, website. Sort by relevance/rating as asked.

## Options
- `-lang he` / `en`: result language. Hebrew queries work.
- `-json -results .../results.json`: JSON output (needed for `-extra-reviews`).
- `-extra-reviews`: more reviews per place (JSON only, slower).
- `-email`: extract emails from business websites (slower).
- `-depth N`: how far to scroll results (1 = shallow; raise for more places).
- `-geo "lat,lon" -radius METERS` with `-zoom`: bias search to a point (e.g. near a hotel).
- `-fast-mode`: quick, reduced data. `-c`: concurrency (keep 1-4 in the container).
- `gmaps-scrape -h` lists all flags.

## Rules
- Use a fresh output file per request (or delete the old one) so results are not mixed.
- If it returns no rows or errors, report that honestly (blocked, empty, timeout); retry once with fewer/other queries, never invent places.
- For a few places only, keep depth 1 and one or two queries. Keep long jobs under the timeout; split into batches.
- Only collect what the user asked for; business contact data is public listing data, don't compile personal data.
