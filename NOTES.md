# Endpoints

1. CLOB REST – https://clob.polymarket.com
    - Discover markets, orderbooks, prices
    - Fetch historical trades, price history
    - Place / cancel orders (with auth) (Polymarket Documentation)
    - Building a trading bot(placing/cancelling orders)
    - Pulling historical prices or trades at scale.

2. Data-API – https://data-api.polymarket.com
    - Value of a user’s holdings across all markets (`/value`)
    - On-chain user activity (`/activity`)
    - Top holders for a token (`/holders`)
    - Top holders for a token (`/holders`)
    - Other user/account-centric endpoints ([Polymarket Documentation][5])
    - Portfolio dashboards
    - PnL / value tracking
    - Whale-tracking / holder analysis

3. CLOB WebSocket – wss://ws-subscriptions-clob.polymarket.com/ws/
    -  Market channel: public L2 book, price changes, last trade price, etc.
    -  User channel: your own order + trade updates (requires auth with API key/secret/passphrase).
    -  Near real-time prices for trading logic
    -  Reactive bots (cancel/replace orders immediately on fills)
    -  Live orderbook views

4. RTDS – wss://ws-live-data.polymarket.com
    - Crypto prices (`crypto_prices`, `crypto_prices_chainlink`)
    - Comments stream on Polymarket (new comments, reactions, replies)
    - Other RTDS feeds as they add them

***They provide an official TypeScript client, but you can hit the raw WS from Python similarly.***

---

# Summary:
1. `https://clob.polymarket.com` → trading + orderbook + historical prices (CLOB REST)
2. `https://data-api.polymarket.com` → user-centric + on-chain data (holdings, activity, holders)
3. `wss://ws-subscriptions-clob.polymarket.com/ws/` → real-time CLOB markets & user orders (CLOB WebSocket)
4. `wss://ws-live-data.polymarket.com` → real-time general streams (crypto prices, comments, etc.) (RTDS)

---

## Activity vs Positions Endpoints

**`/activity`** — Historical transactions
- Individual past transactions (trades, buys, sells)
- Each entry is a single transaction
- Includes transaction hash, timestamp, and transaction-level details
    **20 fields:**
    1. `proxyWallet`
    2. `timestamp`
    3. `conditionId`
    4. `type`
    5. `size`
    6. `usdcSize`
    7. `transactionHash`
    8. `price`
    9. `asset`
    10. `side`
    11. `outcomeIndex`
    12. `title`
    13. `slug`
    14. `icon`
    15. `eventSlug`
    16. `outcome`
    17. `name`
    18. `pseudonym`
    19. `bio`
    20. `profileImage`
    21. `profileImageOptimized`

**`/positions`** — Current holdings with P&L
- Current open positions across markets
- Each entry is an active position
- Includes calculated P&L, current value, and position metrics
    **25 fields:**
    1. `proxyWallet`
    2. `asset`
    3. `conditionId`
    4. `size`
    5. `avgPrice`
    6. `initialValue`
    7. `currentValue`
    8. `cashPnl`
    9. `percentPnl`
    10. `totalBought`
    11. `realizedPnl`
    12. `percentRealizedPnl`
    13. `curPrice`
    14. `redeemable`
    15. `mergeable`
    16. `title`
    17. `slug`
    18. `icon`
    19. `eventId`
    20. `eventSlug`
    21. `outcome`
    22. `outcomeIndex`
    23. `oppositeOutcome`
    24. `oppositeAsset`
    25. `endDate`
    26. `negativeRisk`

**Key difference:** Activity shows historical transactions (what happened), while Positions shows current holdings with P&L calculations (what you have now).

---

# Sports Tags — Gamma API

These are the official sport tag IDs from `https://gamma-api.polymarket.com/sports` (as of late 2025). Use these IDs to filter markets for specific 
sports.

**NCAA Basketball** — ncaab, 1  
**English Premier League** — epl, 2  
**La Liga** — lal, 3  
**IPL Cricket** — ipl, 5  
**WNBA** — wnba, 6  
**Bundesliga** — bun, 7  
**MLB** — mlb, 8  
**NCAA Football** — cfb, 9  
**NFL** — nfl, 10  
**Ligue 1** — fl1, 11  
**Serie A** — sea, 12  
**UEFA Champions League** — ucl, 13  
**Asian Football** — afc, 15  
**Oceania Football** — ofc, 16  
**FIFA** — fif, 17  
**Eredivisie** — ere, 18  
**Argentina Primera División** — arg, 19  
**Coppa Italia** — itc, 20  
**Liga MX** — mex, 21  
**Leagues Cup** — lcs, 22  
**Copa Libertadores** — lib, 23  
**Copa Sudamericana** — sud, 24  
**Turkish Süper Lig** — tur, 25  
**CONMEBOL** — con, 26  
**CONCACAF** — cof, 27  
**UEFA** — uef, 28  
**CAF African Football** — caf, 29  
**Russian Premier League** — rus, 30  
**FA Cup** — efa, 31  
**EFL** — efl, 32  
**MLS** — mls, 33  
**NBA** — nba, 34  
**NHL** — nhl, 35  
**UEFA Europa League** — uel, 36  
**Counter-Strike 2** — cs2, 37  
**Dota 2** — dota2, 38  
**League of Legends** — lol, 39  
**Valorant** — valorant, 40  
**ODI Cricket** — odi, 41  
**T20 Cricket** — t20, 42  
**Big Bash League** — abb, 43  
**Cricket South Africa** — csa, 44  
**ATP Tennis** — atp, 45  
**WTA Tennis** — wta, 46  
**NCAA Women's Basketball** — cwbb, 47  
**MMA / UFC** — mma, 48  
**Copa del Rey** — cdr, 49  
**Mobile Legends** — mlbb, 50  
**Overwatch** — ow, 51  
**Honor of Kings** — kog, 52  
**Call of Duty** — codmw, 53  
**EA Sports FC / FIFA** — fifa, 54  
**LoL Wild Rift** — lol-wild-rift, 55  
**PUBG** — pubg, 56  
**Rainbow Six Siege** — r6siege, 57  
**Rocket League** — rl, 58  
**StarCraft 2** — starcraft-2, 59  
**StarCraft Brood War** — starcraft-brood-war, 60  
**UEFA Conference League** — col, 61  
**Coupe de France** — cde, 62  
**DFB-Pokal** — dfb, 63  
**Brasileirão** — bra, 64  
**J1 League** — jap, 65  
**J2 League** — ja2, 66  
**K League** — kor, 67  
**Saudi Pro League** — spl, 68  
**Chinese Super League** — chi, 69  
**A-League** — aus, 70  
**Indian Super League** — ind, 71  
**Eliteserien** — nor, 72  
**Superliga** — den, 73  
**Liga Portugal** — por, 74  
**Test Cricket** — test, 75  
**Sheffield Shield** — she, 76  
**SA20 Cricket** — sasa, 77  
**Lanka Premier League** — lpl, 78  
**Pakistan Tri-Series** — psp, 79  
**KBO League** — kbo, 80  
**SHL Hockey** — shl, 81  
**Czech Extraliga** — cehl, 82  
**DEL Hockey** — dehl, 83  
**National League Swiss** — snhl, 84  
**KHL Hockey** — khl, 85  
**AHL Hockey** — ahl, 86  
**International Cricket** — crint, 87  
**Cricket India** — crind, 88  
**Cricket England** — creng, 89  
**Cricket Pakistan** — crpak, 90  
**Cricket Australia** — craus, 91  
**Cricket South Africa** — crsou, 92  
**Cricket UAE** — cruae, 93  
**Cricket New Zealand** — crnew, 94

