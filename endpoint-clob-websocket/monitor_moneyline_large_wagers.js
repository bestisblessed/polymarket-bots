// Sources (Polymarket WebSocket docs):
// - https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
// - https://docs.polymarket.com/quickstart/websocket/WSS-Quickstart
// - https://docs.polymarket.com/developers/CLOB/websocket/market-channel

const WebSocket = require("ws");
const https = require("https");
const querystring = require("querystring");

const WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market";
const EVENT_URL = "https://polymarket.com/event/nfl-la-car-2026-01-10";
const EVENT_NAME = "NFL: Rams vs Panthers (Moneyline)";

const DEFAULT_MIN_NOTIONAL = 10000;
const MIN_NOTIONAL_USDC = Number.parseFloat(
  process.env.MIN_NOTIONAL_USDC || DEFAULT_MIN_NOTIONAL
);

const PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json";
const PUSHOVER_API_TOKEN = process.env.PUSHOVER_API_TOKEN;
const PUSHOVER_GROUP_KEY = process.env.PUSHOVER_GROUP_KEY;

const assetIdsFromEnv = process.env.ASSET_IDS
  ? process.env.ASSET_IDS.split(",").map((asset) => asset.trim()).filter(Boolean)
  : [];
const assetIdsFromArgs = process.argv.slice(2).map((asset) => asset.trim()).filter(Boolean);
const assetIds = assetIdsFromArgs.length > 0 ? assetIdsFromArgs : assetIdsFromEnv;

if (assetIds.length === 0) {
  console.error(
    "Missing asset IDs. Provide them as CLI args or ASSET_IDS env var (comma-separated)."
  );
  process.exit(1);
}

if (!Number.isFinite(MIN_NOTIONAL_USDC)) {
  console.error("MIN_NOTIONAL_USDC must be a number.");
  process.exit(1);
}

const seenHashes = new Set();
const MAX_SEEN_HASHES = 5000;

const ws = new WebSocket(WS_URL);

ws.onopen = () => {
  ws.send(
    JSON.stringify({
      type: "market",
      assets_ids: assetIds,
    })
  );
  console.log(`Subscribed to assets: ${assetIds.join(", ")}`);
  console.log(`Large wager threshold: $${MIN_NOTIONAL_USDC.toFixed(2)} USDC`);
};

ws.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  const events = Array.isArray(payload) ? payload : [payload];

  events.forEach((message) => {
    if (message.event_type !== "price_change") {
      return;
    }

    if (!Array.isArray(message.price_changes)) {
      return;
    }

    message.price_changes.forEach((change) => {
      if (!change || !change.hash || seenHashes.has(change.hash)) {
        return;
      }

      const price = Number.parseFloat(change.price);
      const size = Number.parseFloat(change.size);
      if (!Number.isFinite(price) || !Number.isFinite(size)) {
        return;
      }

      const notional = price * size;
      if (notional < MIN_NOTIONAL_USDC) {
        return;
      }

      seenHashes.add(change.hash);
      if (seenHashes.size > MAX_SEEN_HASHES) {
        const [oldest] = seenHashes;
        seenHashes.delete(oldest);
      }

      const side = change.side || "UNKNOWN";
      const assetId = change.asset_id || "unknown";
      const bestBid = change.best_bid ? Number.parseFloat(change.best_bid).toFixed(3) : "n/a";
      const bestAsk = change.best_ask ? Number.parseFloat(change.best_ask).toFixed(3) : "n/a";

      const messageBody = [
        `${EVENT_NAME} large wager detected`,
        `Side: ${side}`,
        `Price: ${price.toFixed(3)}`,
        `Size: ${size.toLocaleString()}`,
        `Notional: $${notional.toFixed(2)} USDC`,
        `Asset: ${assetId}`,
        `Best bid/ask: ${bestBid} / ${bestAsk}`,
        `Market: ${message.market || "unknown"}`,
      ].join("\n");

      sendPushover(messageBody, EVENT_URL);
    });
  });
};

ws.onerror = (error) => {
  console.error("WebSocket error:", error.message || error);
};

ws.onclose = () => {
  console.log("WebSocket connection closed.");
};

function sendPushover(message, url) {
  if (!PUSHOVER_API_TOKEN || !PUSHOVER_GROUP_KEY) {
    console.log("Pushover credentials not found, skipping notification.");
    return;
  }

  const payload = {
    token: PUSHOVER_API_TOKEN,
    user: PUSHOVER_GROUP_KEY,
    title: "Polymarket Moneyline Alert",
    message,
  };

  if (url) {
    payload.url = url;
    payload.url_title = "Open Polymarket Event";
  }

  const body = querystring.stringify(payload);
  const request = https.request(
    PUSHOVER_ENDPOINT,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": Buffer.byteLength(body),
      },
    },
    (response) => {
      if (response.statusCode !== 200) {
        console.error(`Pushover failed: ${response.statusCode}`);
      } else {
        console.log("Pushover notification sent.");
      }
    }
  );

  request.on("error", (error) => {
    console.error("Pushover request failed:", error.message || error);
  });

  request.write(body);
  request.end();
}
