#!/usr/bin/env python3
import sys

import requests

limit = int(sys.argv[1]) if len(sys.argv) > 1 else 200
offset = 0
slugs = set()

while True:
    r = requests.get(
        "https://gamma-api.polymarket.com/events",
        params={
            "tag_slug": "ufc",
            "active": "true",
            "closed": "false",
            "archived": "false",
            "limit": limit,
            "offset": offset,
        },
        headers={"User-Agent": "curl/8.0"},
        timeout=60,
    )
    r.raise_for_status()
    events = r.json() or []
    if not events:
        break

    for ev in events:
        if not any((m.get("sportsMarketType") or "") == "moneyline" for m in (ev.get("markets") or [])):
            continue
        slug = ev.get("slug")
        if slug:
            slugs.add(slug)

    offset += len(events)

for slug in sorted(slugs):
    print(slug)
