from websocket import WebSocketApp
import json
import time
import threading

url = "wss://ws-subscriptions-clob.polymarket.com"

def on_message(ws, message):
    print(message)

def on_error(ws, error):
    print("Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("Connection closed")

def on_open(ws):
    # Subscribe to market channel with asset IDs
    ws.send(json.dumps({
        "assets_ids": ["YOUR_TOKEN_ID_HERE"],
        "type": "market"
    }))
    
    # Start ping thread to keep connection alive
    def ping():
        while True:
            ws.send("PING")
            time.sleep(10)
    threading.Thread(target=ping).start()

ws = WebSocketApp(
    url + "/ws/market",
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
    on_open=on_open
)

ws.run_forever()
