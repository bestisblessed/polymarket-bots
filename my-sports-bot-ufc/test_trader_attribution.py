"""Focused regression tests; all X/Pushover/network writes are mocked."""

import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))
import trader_attribution as attribution
import monitor_ufc_large_wagers as monitor
from PIL import Image
import requests

CONDITION = "0x" + "1" * 64
TX = "0x" + "2" * 64
WALLET = "0x" + "3" * 40
EVENT = {"asset_id": "12345", "market": CONDITION, "side": "BUY",
         "price": "0.76", "size": "6745.18", "timestamp": "1786702800123",
         "transaction_hash": TX}
TRADE = {"conditionId": CONDITION, "asset": "12345", "side": "BUY",
         "price": 0.76, "size": 6745.18, "timestamp": 1786702800,
         "transactionHash": TX, "proxyWallet": WALLET,
         "name": "uondrey", "pseudonym": "Fallback-Name"}
INFO = {"condition_id": CONDITION, "event_title": "UFC 330 - Islam Makhachev vs. Ian Machado Garry",
        "outcome": "Islam Makhachev", "market_display": "Moneyline",
        "sports_market_type": "moneyline", "event_slug": "ufc-test"}


class MatchingTests(unittest.TestCase):
    def test_hash_match_and_duplicate_row(self):
        trader, evidence = attribution.match_trader(EVENT, CONDITION, [TRADE, TRADE.copy()])
        self.assertEqual(trader["wallet"], WALLET)
        self.assertEqual(evidence["candidate_count"], 1)
        self.assertEqual(evidence["matched_by"], "transaction_hash")

    def test_hashless_unique_match(self):
        event = {k: v for k, v in EVENT.items() if k != "transaction_hash"}
        trader, evidence = attribution.match_trader(event, CONDITION, [TRADE])
        self.assertEqual(trader["name"], "uondrey")
        self.assertEqual(evidence["matched_by"], "unique_trade")

    def test_ambiguous_wallets_rejected(self):
        other = {**TRADE, "proxyWallet": "0x" + "4" * 40}
        self.assertEqual(attribution.match_trader(EVENT, CONDITION, [TRADE, other])[1]["status"], "ambiguous")

    def test_wrong_hash_rejected(self):
        self.assertIsNone(attribution.match_trader(EVENT, CONDITION, [{**TRADE, "transactionHash": "0x" + "4" * 64}])[0])

    def test_split_fill_and_other_trade_fields_rejected(self):
        for field, value in [("size", 100), ("price", 0.77), ("timestamp", 1786702810),
                             ("asset", "67890"), ("side", "SELL"), ("conditionId", "0x" + "4" * 64)]:
            with self.subTest(field=field):
                self.assertIsNone(attribution.match_trader(EVENT, CONDITION, [{**TRADE, field: value}])[0])

    def test_invalid_and_incomplete_response(self):
        for row in [{**TRADE, "proxyWallet": "bad"}, {**TRADE, "transactionHash": ""},
                    {**TRADE, "price": "nan"}, {}]:
            self.assertIsNone(attribution.match_trader(EVENT, CONDITION, [row])[0])
        self.assertIsNone(attribution.match_trader(EVENT, CONDITION, [TRADE] * 1000)[0])

    def test_invalid_event_and_missing_timestamp(self):
        for event in [{**EVENT, "timestamp": None}, {**EVENT, "size": "nan"},
                      {**EVENT, "market": "bad"}, {**EVENT, "transaction_hash": "bad"}]:
            self.assertEqual(attribution.match_trader(event, CONDITION, [TRADE])[1]["status"], "invalid_event")

    def test_names_and_url_like_names(self):
        for name in ["https://example.com", "example.com", "@Someone", "0x1234-123456"]:
            self.assertEqual(attribution.trader_name({"name": name, "pseudonym": "Fallback-Name"}, WALLET), "Fallback-Name")
        self.assertEqual(attribution.trader_name({}, WALLET), attribution.short_wallet(WALLET))

    def test_delayed_indexing(self):
        empty, indexed = Mock(), Mock()
        empty.json.return_value = []
        indexed.json.return_value = [TRADE]
        with patch.object(attribution.requests, "get", side_effect=[empty, indexed]) as get, \
                patch.object(attribution.threading.Event, "wait", return_value=False):
            trader, evidence = attribution.lookup_trader(EVENT, CONDITION, budget=1)
        self.assertEqual(trader["wallet"], WALLET)
        self.assertEqual(evidence["attempts"], 2)
        self.assertEqual(get.call_args.kwargs["params"]["market"], CONDITION)
        self.assertEqual(get.call_args.kwargs["params"]["side"], "BUY")

    def test_lookup_wall_clock_timeout(self):
        response = Mock()
        response.json.return_value = []
        def delayed(*args, **kwargs):
            time.sleep(0.2)
            return response
        with patch.object(attribution.requests, "get", side_effect=delayed):
            start = time.monotonic()
            trader, evidence = attribution.lookup_trader(EVENT, CONDITION, budget=0.03)
        self.assertIsNone(trader)
        self.assertEqual(evidence["status"], "timeout")
        self.assertLess(time.monotonic() - start, 0.15)


class ImageAndPostTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.art = self.root / "art.jpg"
        Image.new("RGB", (2000, 1333), "#228899").save(self.art)
        self.trader = attribution.match_trader(EVENT, CONDITION, [TRADE])[0]

    def test_footer_cache_is_wallet_specific_and_source_specific(self):
        first = attribution.compose_trader_image(str(self.art), self.trader, output_dir=self.root)
        self.assertEqual(first, attribution.compose_trader_image(str(self.art), self.trader, output_dir=self.root))
        other = {**self.trader, "wallet": "0x" + "4" * 40}
        second = attribution.compose_trader_image(str(self.art), other, output_dir=self.root)
        self.assertNotEqual(first, second)
        with Image.open(first) as composed:
            self.assertEqual(composed.width, 2000)
            self.assertGreater(composed.height, 1333)
            self.assertLess(Path(first).stat().st_size, 5 * 1024 * 1024)
            with Image.open(self.art) as original:
                self.assertEqual(composed.getpixel((10, 10)), original.getpixel((10, 10)))
        Image.new("RGB", (2000, 1333), "red").save(self.art)
        self.assertNotEqual(first, attribution.compose_trader_image(str(self.art), self.trader, output_dir=self.root))

    def test_image_failure_and_unattributed_fallback(self):
        self.assertEqual(attribution.compose_trader_image("missing.jpg", self.trader), "missing.jpg")
        self.assertEqual(attribution.compose_trader_image(str(self.art), None), str(self.art))

    def test_text_preserves_wager_and_attribution_with_unicode(self):
        text = monitor.build_x_alert_tweet("非常長的賽事名稱" * 30, "非常長的市場名稱" * 30,
            "Islam Makhachev" * 30, .76, 5126.34, 1618.84, 6745.18,
            trader={**self.trader, "name": "非常長的用戶名稱" * 30})
        self.assertLessEqual(attribution.weighted_length(text), 280)
        self.assertIn("$5,126.34 to win $1,618.84 (6,745.18 shares)", text)
        self.assertIn("Wallet: " + WALLET, text)
        self.assertTrue(text.startswith("🐳 UFC SHARP ACTION\n\n"))
        self.assertIn("\n\nPolymarket Trader:", text)
        self.assertNotIn("https://", text)

    def test_token_metadata_keeps_condition_id(self):
        state = monitor.build_token_map_for_event(event_slug="test", event_title="test", markets=[
            {"conditionId": CONDITION, "clobTokenIds": ["12345"], "outcomes": ["Yes"]}])
        self.assertEqual(state["token_map"]["12345"]["condition_id"], CONDITION)

    def test_dry_run_has_no_external_writes(self):
        fixture = self.root / "fixture.json"
        fixture.write_text(json.dumps({"event": EVENT, "market_info": {**INFO, "ufc_image_path": "art.jpg"},
                                       "trades": [TRADE], "provenance": "unit fixture"}))
        with patch.object(requests, "post", side_effect=AssertionError("External POST")), \
                patch.object(requests, "get", side_effect=AssertionError("External GET")), \
                patch.object(monitor, "compose_trader_image", side_effect=AssertionError("QR disabled")):
            result = monitor.dry_run_fixture(str(fixture), str(self.root / "preview"))
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["matching"]["status"], "matched")
        self.assertTrue(Path(result["image_path"]).is_file())
        self.assertEqual(Path(result["image_path"]), self.art)

    def test_live_handler_preserves_pushover_then_posts_original_image(self):
        info = {**INFO, "ufc_image_path": str(self.art)}
        with patch.object(monitor, "log_event"), patch.object(monitor, "send_pushover") as push, \
                patch.object(monitor, "lookup_trader", return_value=(self.trader, {"status": "matched"})), \
                patch.object(monitor, "compose_trader_image", side_effect=AssertionError("QR disabled")), \
                patch.object(monitor, "send_x_tweet") as send:
            monitor.process_last_trade_price(EVENT, {"12345": info}, 1000)
        push.assert_called_once()
        send.assert_called_once()
        self.assertIn("\n\nPolymarket Trader: uondrey | Wallet: " + WALLET, send.call_args.args[0])
        self.assertEqual(send.call_args.kwargs["image_path"], str(self.art))

    def test_requested_full_wallet_layout(self):
        trader = {**self.trader, "name": "Liverpool1",
                  "wallet": "0xd4225ee3c77fda4d1360e096669e4e97198a7e43"}
        text = monitor.build_x_alert_tweet(
            "UFC Fight Night - Robert Bryczek vs. Rodolfo Vieira", "Moneyline",
            "Rodolfo Vieira", .97, 1800, 51.62, 1851.62, trader=trader)
        self.assertEqual(text, "🐳 UFC SHARP ACTION\n\n"
            "UFC Fight Night - Robert Bryczek vs. Rodolfo Vieira\n"
            "Market: Moneyline\nSide: Rodolfo Vieira @ 97%\n"
            "Wager: $1,800.00 to win $51.62 (1,851.62 shares)\n\n"
            "Polymarket Trader: Liverpool1 | Wallet: " + trader["wallet"])
        self.assertLessEqual(attribution.weighted_length(text), 280)

    def test_sender_never_retries_uncertain_post(self):
        with patch.object(monitor, "get_x_auth", return_value=Mock()), \
                patch.object(monitor.requests, "post", side_effect=requests.Timeout) as post:
            self.assertIsNone(monitor.send_x_tweet("test"))
        self.assertEqual(post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
