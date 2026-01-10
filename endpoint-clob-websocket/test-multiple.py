import json
from websocket import create_connection

ws = create_connection("wss://ws-subscriptions-clob.polymarket.com/ws/")

ws.send(json.dumps({
    "type": "MARKET",
    "assets_ids": [
        "TOKEN_ID_1",
        "TOKEN_ID_2",
        "TOKEN_ID_3",
    ],
}))

while True:
    print(ws.recv())

