# ws_market_test_blocking.py
import json
from websocket import create_connection

WSS = "wss://ws-subscriptions-clob.polymarket.com/ws/"
MARKET_ID = "REPLACE_WITH_MARKET_ID"

ws = create_connection(WSS)

ws.send(json.dumps({
    "type": "subscribe",
    "channel": "market",
    "markets": [MARKET_ID],
}))

while True:
    print(ws.recv())

