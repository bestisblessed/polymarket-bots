"""Public trade matching and profile QR artwork for UFC X alerts."""

import hashlib
import io
import math
import re
import threading
import time
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from queue import Empty, Queue

import requests

DATA_API = "https://data-api.polymarket.com/trades"
LOOKUP_BUDGET_SECONDS = 15
WINDOW_SECONDS = 2
WALLET_RE = re.compile(r"0x[0-9a-fA-F]{40}\Z")
HASH_RE = re.compile(r"0x[0-9a-fA-F]{64}\Z")
# Use a conservative allowlist for public labels: no domains, URLs or X mentions.
NAME_RE = re.compile(r"[\w -]+\Z", re.UNICODE)


def short_wallet(wallet):
    return wallet[:6] + "…" + wallet[-6:]


def trader_name(trade, wallet):
    for key in ("name", "pseudonym"):
        label = unicodedata.normalize("NFC", " ".join(str(trade.get(key) or "").split()))
        if label and NAME_RE.fullmatch(label) and not label.lower().startswith("0x"):
            return label
    return short_wallet(wallet)


def _number(value):
    value = Decimal(str(value))
    if not value.is_finite():
        raise ValueError("Non-finite trade number")
    return value


def match_trader(event, condition_id, trades):
    """Return (attribution, evidence); never choose between distinct candidates."""
    evidence = {"status": "unmatched", "candidate_count": 0}
    try:
        asset = str(event["asset_id"])
        price, size = _number(event["price"]), _number(event["size"])
        timestamp = _number(event["timestamp"]) / 1000
        tx = str(event.get("transaction_hash") or "").lower()
        if (not HASH_RE.fullmatch(str(condition_id)) or not asset.isdigit()
                or event.get("side") != "BUY" or not 0 < price <= 1
                or size <= 0 or timestamp <= 0
                or (event.get("market") and event["market"].lower() != condition_id.lower())
                or (tx and not HASH_RE.fullmatch(tx))):
            raise ValueError("Invalid event identifiers")
    except (KeyError, TypeError, ValueError, InvalidOperation, AttributeError):
        return None, {**evidence, "status": "invalid_event"}
    if not isinstance(trades, list):
        return None, {**evidence, "status": "invalid_response"}
    if len(trades) >= 1000:
        return None, {**evidence, "status": "incomplete_window"}

    candidates = {}
    for row in trades:
        try:
            if (row["conditionId"].lower() != condition_id.lower()
                    or str(row["asset"]) != asset or row["side"] != "BUY"
                    or abs(_number(row["price"]) - price) > Decimal("0.000001")
                    or abs(_number(row["size"]) - size) > Decimal("0.0001")
                    or abs(_number(row["timestamp"]) - timestamp) > WINDOW_SECONDS):
                continue
            row_tx = str(row.get("transactionHash") or "").lower()
            if tx and row_tx != tx:
                continue
            wallet = str(row.get("proxyWallet") or "").lower()
            if not WALLET_RE.fullmatch(wallet) or not HASH_RE.fullmatch(row_tx):
                return None, {**evidence, "status": "invalid_candidate"}
            key = (wallet, row_tx, str(row["asset"]), str(_number(row["price"])),
                   str(_number(row["size"])), str(row["timestamp"]))
            candidates[key] = row
        except (KeyError, TypeError, ValueError, InvalidOperation, AttributeError):
            # A malformed response must not make an apparently unique match trustworthy.
            return None, {**evidence, "status": "invalid_response"}
    evidence["candidate_count"] = len(candidates)
    if len(candidates) != 1:
        evidence["status"] = "ambiguous" if candidates else "unmatched"
        return None, evidence
    row = next(iter(candidates.values()))
    wallet = row["proxyWallet"].lower()
    attribution = {
        "wallet": wallet,
        "name": trader_name(row, wallet),
        "profile_url": f"https://polymarket.com/profile/{wallet}",
        "transaction_hash": row["transactionHash"].lower(),
    }
    evidence.update(status="matched", matched_by="transaction_hash" if tx else "unique_trade",
                    transaction_hash=attribution["transaction_hash"], wallet=wallet)
    return attribution, evidence


def lookup_trader(event, condition_id, *, budget=LOOKUP_BUDGET_SECONDS):
    """Bound caller wait even if DNS/network I/O exceeds its socket timeout."""
    _, validation = match_trader(event, condition_id, [])
    if validation["status"] == "invalid_event":
        return None, validation
    budget = max(0, min(float(budget), LOOKUP_BUDGET_SECONDS))
    deadline = time.monotonic() + budget
    stop = threading.Event()
    results = Queue(maxsize=1)
    second = float(event["timestamp"]) / 1000
    params = {"market": condition_id, "side": "BUY", "takerOnly": "true",
              "start": math.floor(second - WINDOW_SECONDS),
              "end": math.ceil(second + WINDOW_SECONDS), "limit": 1000}

    def worker():
        last = {"status": "unmatched", "attempts": 0}
        while not stop.is_set() and time.monotonic() < deadline:
            last["attempts"] += 1
            try:
                response = requests.get(DATA_API, params=params, timeout=(1, 2))
                response.raise_for_status()
                attribution, evidence = match_trader(event, condition_id, response.json())
                evidence["attempts"] = last["attempts"]
                last = evidence
                if attribution or evidence["status"] != "unmatched":
                    results.put((attribution, evidence))
                    return
            except (requests.RequestException, ValueError) as exc:
                last["status"] = "lookup_error"
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    if 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                        break
            stop.wait(min(2, max(0, deadline - time.monotonic())))
        if not stop.is_set():
            results.put((None, last))

    threading.Thread(target=worker, daemon=True, name="ufc-trader-lookup").start()
    try:
        return results.get(timeout=budget)
    except Empty:
        return None, {"status": "timeout", "budget_seconds": budget}
    finally:
        stop.set()


def weighted_length(text):
    """Conservative upper bound for URL-free X text (including emoji sequences)."""
    text = unicodedata.normalize("NFC", text)
    return sum(1 if ord(c) <= 0x10FF or 0x2000 <= ord(c) <= 0x200D
               or 0x2010 <= ord(c) <= 0x201F or 0x2032 <= ord(c) <= 0x2037
               else 2 for c in text)


def fit_text(text, budget):
    text = unicodedata.normalize("NFC", text)
    if weighted_length(text) <= budget:
        return text
    while text and weighted_length(text + "…") > budget:
        text = text[:-1]
    return text.rstrip() + "…" if budget > 0 else ""


def compose_trader_image(image_path, attribution, *, output_dir=None):
    """Append a wallet-specific footer; return original artwork on any failure."""
    if not image_path or not attribution:
        return image_path
    try:
        import qrcode
        from PIL import Image, ImageDraw, ImageFont, ImageOps

        wallet = attribution["wallet"]
        if not WALLET_RE.fullmatch(wallet):
            raise ValueError("Invalid profile wallet")
        source = Path(image_path)
        stat = source.stat()
        identity = f"{source.resolve()}:{stat.st_mtime_ns}:{stat.st_size}:{wallet}:{attribution['name']}:footer-v1"
        key = hashlib.sha256(identity.encode()).hexdigest()[:32]
        directory = Path(output_dir) if output_dir else Path(__file__).parent / "data" / "trader_profile_images"
        destination = directory / f"{key}.jpg"
        if destination.is_file():
            return str(destination)
        with Image.open(source) as opened:
            art = ImageOps.exif_transpose(opened).convert("RGB")
        if art.width < 1200 or art.width > 2000:
            width = min(2000, max(1200, art.width))
            art = art.resize((width, round(art.height * width / art.width)), Image.Resampling.LANCZOS)
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=1)
        qr.add_data(f"https://polymarket.com/profile/{wallet}")
        qr.make(fit=True)
        qr.box_size = max(6, int(art.width * 0.28 / (qr.modules_count + 8)))
        code = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        margin = max(24, art.width // 60)
        footer_height = code.height + 2 * margin + art.width // 40
        composed = Image.new("RGB", (art.width, art.height + footer_height), "white")
        composed.paste(art, (0, 0))
        draw = ImageDraw.Draw(composed)

        def font(size):
            for filename in ("DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"):
                try:
                    return ImageFont.truetype(filename, size)
                except OSError:
                    pass
            return ImageFont.load_default(size=size)

        left_width = art.width - code.width - 3 * margin
        label_font = font(art.width // 45)
        name_font = font(art.width // 32)
        wallet_font = font(art.width // 60)
        name = attribution["name"]
        while name and draw.textlength(name + "…", font=name_font) > left_width:
            name = name[:-1]
        if name != attribution["name"]:
            name = name.rstrip() + "…"
        top = art.height + footer_height // 3
        draw.text((margin, top), "Polymarket trader", font=label_font, fill="#555555")
        draw.text((margin, top + art.width // 30), name, font=name_font, fill="black")
        draw.text((margin, top + art.width // 13), wallet, font=wallet_font, fill="#333333")
        code_x = art.width - code.width - margin
        composed.paste(code, (code_x, art.height + margin))
        draw.text((code_x, art.height + margin + code.height), "Scan trader profile",
                  font=font(art.width // 55), fill="black")
        image_bytes = io.BytesIO()
        composed.save(image_bytes, format="JPEG", quality=95, optimize=True)
        if image_bytes.tell() > 5 * 1024 * 1024:
            raise ValueError("Composed image exceeds 5 MB")
        directory.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(image_bytes.getvalue())
        return str(destination)
    except Exception as exc:
        print(f"[WARN] Trader QR unavailable; using original artwork: {exc}")
        return image_path
