'''
List all markets info from a given slug with the top holders of each
'''

EVENT_SLUG = "which-company-has-best-ai-model-end-of-2025"

import json
import requests
from polymarket_apis import PolymarketGammaClient

gamma = PolymarketGammaClient()
all_markets = gamma.get_markets(closed=False, limit=10000) + gamma.get_markets(closed=True, limit=10000)

# Find all markets from given slug
markets_in_event = []
for m in all_markets:
    if getattr(m, "events", None):
        for ev in m.events:
            if ev.slug == EVENT_SLUG:
                markets_in_event.append(m)
                break

# Sort markets by volume
markets_in_event = list({m.id: m for m in markets_in_event}.values())
markets_in_event = sorted(markets_in_event, key=lambda m: (m.volume_num or 0), reverse=True)
print(f"Found {len(markets_in_event)} markets in event '{EVENT_SLUG}':\n")
for m in markets_in_event:
    print(f"Title: {m.question}")
    print(f"Slug: {m.slug}")
    print(f"Market ID: {m.id}")
    print(f"Condition ID: {m.condition_id}")
    print(f"Volume: ${m.volume_num}")
    r = requests.get(
        "https://data-api.polymarket.com/holders",
        params={"market": m.condition_id},
        timeout=20,
    )
    r.raise_for_status()
    holders_payload = r.json()
    outcomes = m.outcomes
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = [outcomes]
    for token_data in holders_payload:
        holders = token_data.get("holders", []) or []
        outcome_index = None
        if holders and "outcomeIndex" in holders[0]:
            outcome_index = holders[0]["outcomeIndex"]
        outcome_name = (
            outcomes[outcome_index] if isinstance(outcome_index, int) and outcomes and outcome_index < len(outcomes)
            else str(outcome_index if outcome_index is not None else "?")
        )
        print(f"\nOutcome: {outcome_name}".upper())
        print("Top 10 Holders:")
        for i, h in enumerate(holders[:10], 1):
            name = h.get("name") or h.get("pseudonym") or h.get("proxyWallet", "")
            amount = h.get("amount")
            print(f"  {i}. {name}: {amount:,.2f} shares")
    print("\n")
    print("=" * 80)
    print("\n")
