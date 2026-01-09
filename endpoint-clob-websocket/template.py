import json
from datetime import datetime
from websocket import create_connection

#token_id = "90468297690119961729415596184451710609666058555177444095392763708049826586245"
token_id = "78771016858683590931968399206043033368231163700315025308842883779104149970413"

ws = create_connection("wss://ws-subscriptions-clob.polymarket.com/ws/market")

ws.send(json.dumps({
    "type": "market",
    "assets_ids": [token_id]
}))

while True:
    message = ws.recv()
    data = json.loads(message)
    timestamp = datetime.now().isoformat()
    log_entry = f"{timestamp}: {json.dumps(data)}\n"
    
    print(data)
    with open("logs/log_orderbook_python.log", "a") as f:
        f.write(log_entry)
