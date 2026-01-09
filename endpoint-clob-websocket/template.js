const WebSocket = require("ws");
const fs = require("fs");

const tokenId = "90468297690119961729415596184451710609666058555177444095392763708049826586245";
const logFile = fs.createWriteStream("logs/log_orderbook.log", { flags: "a" });

const ws = new WebSocket("wss://ws-subscriptions-clob.polymarket.com/ws/market");

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: "market",
    assets_ids: [tokenId]
  }));

//  setInterval(() => ws.send("PING"), 10000);

};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
//  console.log(data);
  const timestamp = new Date().toISOString();
  const logEntry = `${timestamp}: ${JSON.stringify(data)}\n`;
  
  console.log(data);          
  logFile.write(logEntry);
};
