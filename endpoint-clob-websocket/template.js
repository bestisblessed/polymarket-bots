const WebSocket = require("ws");
const fs = require("fs");

// const tokenId = "90468297690119961729415596184451710609666058555177444095392763708049826586245";
// const tokenId = "78771016858683590931968399206043033368231163700315025308842883779104149970413";
const defaultAssetIds = [
  "9582457452124876970491702012602654966458667596959660948687161390487436717790",
  "16876502714779661815672749154759628865100317015605958130253912276725814629837",
];
const assetIds = process.argv.slice(2);
const assetsIds = assetIds.length > 0 ? assetIds : defaultAssetIds;
const logFile = fs.createWriteStream("logs/log_orderbook.log", { flags: "a" });

const ws = new WebSocket("wss://ws-subscriptions-clob.polymarket.com/ws/market");

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: "market",
    assets_ids: assetsIds
  }));

//  setInterval(() => ws.send("PING"), 10000);

};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  const timestamp = new Date().toISOString();
  const logEntry = `${timestamp}: ${JSON.stringify(data)}\n`;
  if (data.event_type !== "price_change") {
    console.log(data);
  }
  logFile.write(logEntry);
};
