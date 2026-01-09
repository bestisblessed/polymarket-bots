const WebSocket = require("ws");
const fs = require("fs");
const https = require("https");
const querystring = require("querystring");

// const tokenId = "90468297690119961729415596184451710609666058555177444095392763708049826586245";
// const tokenId = "78771016858683590931968399206043033368231163700315025308842883779104149970413";
const defaultAssetIds = [
  "9582457452124876970491702012602654966458667596959660948687161390487436717790",
  "16876502714779661815672749154759628865100317015605958130253912276725814629837",
];
const assetIds = process.argv.slice(2);
const assetsIds = assetIds.length > 0 ? assetIds : defaultAssetIds;
const envPath = ".env";
if (fs.existsSync(envPath)) {
  const envLines = fs.readFileSync(envPath, "utf8").split(/\r?\n/);
  for (const line of envLines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!match) {
      continue;
    }
    const key = match[1];
    let value = match[2].trim();
    if (value.includes(" #")) {
      value = value.split(" #")[0].trim();
    }
    if (
      (value.startsWith("\"") && value.endsWith("\"")) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (!process.env[key]) {
      process.env[key] = value;
    }
  }
}

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
    sendPushoverNotification(data);
  }
  logFile.write(logEntry);
};

function sendPushoverNotification(data) {
  const userKey = process.env.PUSHOVER_GROUP_KEY;
  const apiToken = process.env.PUSHOVER_API_TOKEN;
  if (!userKey || !apiToken) {
    return;
  }

  const eventType = data.event_type || "unknown";
  const market = data.market || "unknown";
  const message = `Non price_change event: ${eventType}\nmarket: ${market}`;
  const postData = querystring.stringify({
    token: apiToken,
    user: userKey,
    title: "CLOB event",
    message,
  });

  const req = https.request(
    {
      method: "POST",
      hostname: "api.pushover.net",
      path: "/1/messages.json",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": Buffer.byteLength(postData),
      },
    },
    (res) => {
      res.on("data", () => {});
    }
  );

  req.on("error", (err) => {
    console.error("Pushover error:", err.message);
  });
  req.write(postData);
  req.end();
}
