import websocket
import json
import time

url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
ws = websocket.create_connection(url)

# Subscribe to a market
ws.send(json.dumps({
    "assets_ids": ["YOUR_TOKEN_ID_HERE"],
    "type": "market"
}))

# Listen for messages
while True:
    ws.send("PING")  # Keep alive
    result = ws.recv()
    print(result)
    time.sleep(1)
