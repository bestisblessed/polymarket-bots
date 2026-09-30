"""Focused regression tests; all X/Pushover/network writes are mocked."""

import json
from pathlib import Path
import sys
import tempfile
import threading
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
        dispatcher = Mock()
        with patch.object(monitor, "log_event"), patch.object(monitor, "send_pushover") as push, \
                patch.object(monitor, "lookup_trader", return_value=(self.trader, {"status": "matched"})), \
                patch.object(monitor, "compose_trader_image", side_effect=AssertionError("QR disabled")), \
                patch.object(monitor, "send_x_tweet") as send:
            monitor.process_last_trade_price(EVENT, {"12345": info}, 1000,
                                             alert_dispatcher=dispatcher)
            push.assert_not_called()
            send.assert_not_called()
            dispatcher.submit.assert_called_once()
            monitor.deliver_whale_alert(dispatcher.submit.call_args.args[0])
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


class BackgroundAlertTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def dispatcher(self, handler, **kwargs):
        dispatcher = monitor.AlertDispatcher(handler, self.root, **kwargs)
        self.addCleanup(dispatcher.close)
        return dispatcher

    def test_slow_lookup_does_not_block_next_trade_or_fast_worker(self):
        blocked, release, fast_posted, slow_posted = [threading.Event() for _ in range(4)]
        self.addCleanup(release.set)
        dispatcher = self.dispatcher(monitor.deliver_whale_alert, workers=2, capacity=2)

        def lookup(event, condition):
            if event["timestamp"] == EVENT["timestamp"]:
                blocked.set()
                release.wait(3)
            return None, {"status": "timeout"}

        def posted(text, **kwargs):
            (fast_posted if "$760.00" in text else slow_posted).set()
            return "test-post-id"

        with patch.object(monitor, "log_event") as log, \
                patch.object(monitor, "send_pushover"), \
                patch.object(monitor, "lookup_trader", side_effect=lookup), \
                patch.object(monitor, "send_x_tweet", side_effect=posted) as post:
            start = time.monotonic()
            monitor.process_last_trade_price(EVENT, {"12345": INFO}, 500,
                                             alert_dispatcher=dispatcher)
            self.assertLess(time.monotonic() - start, 0.2)
            self.assertTrue(blocked.wait(1))
            small = {**EVENT, "size": "1"}
            monitor.process_last_trade_price(small, {"12345": INFO}, 500,
                                             alert_dispatcher=dispatcher)
            fast = {**EVENT, "size": "1000", "timestamp": "1786702801123"}
            monitor.process_last_trade_price(fast, {"12345": INFO}, 500,
                                             alert_dispatcher=dispatcher)
            self.assertEqual(log.call_count, 3)
            self.assertTrue(fast_posted.wait(1), "second worker must not wait for slow lookup")
            self.assertFalse(slow_posted.is_set())
            release.set()
            self.assertTrue(slow_posted.wait(1))
            dispatcher.close()
            self.assertEqual(post.call_count, 2)
            self.assertTrue(all("Polymarket Trader:" not in call.args[0]
                                for call in post.call_args_list))

    def test_burst_overflow_is_saved_and_delivered_once(self):
        entered, release, finished = [threading.Event() for _ in range(3)]
        seen = []
        lock = threading.Lock()

        def deliver(job):
            entered.set()
            release.wait(3)
            with lock:
                seen.append(job["id"])
                if len(seen) == 6:
                    finished.set()

        dispatcher = self.dispatcher(deliver, workers=2, capacity=1)
        self.addCleanup(release.set)
        with patch("builtins.print") as output:
            start = time.monotonic()
            for i in range(6):
                self.assertTrue(dispatcher.submit({"id": i}))
            self.assertLess(time.monotonic() - start, 0.2)
            self.assertTrue(entered.wait(1))
            self.assertTrue(any("queue full" in str(call) for call in output.call_args_list))
            self.assertGreater(len(list(self.root.glob("*.json"))), 0)
            release.set()
            self.assertTrue(finished.wait(2))
        dispatcher.close()
        self.assertCountEqual(seen, range(6))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_actual_websocket_callback_returns_during_slow_lookup(self):
        blocked, release, posted = [threading.Event() for _ in range(3)]
        callback_times = []
        info = {**INFO, "market_title": "Moneyline"}
        state = {"token_map": {"12345": info}, "token_ids": ["12345"],
                 "event_slug": "ufc-test", "event_title": "Test", "event_url": "", "markets": []}

        def lookup(*args):
            blocked.set()
            release.wait(3)
            return None, {"status": "timeout"}

        def post(*args, **kwargs):
            posted.set()
            return "test-id"

        class FakeWebSocket:
            def __init__(self, url, **callbacks):
                self.on_message = callbacks["on_message"]

            def run_forever(self, **kwargs):
                try:
                    for event in [EVENT, {**EVENT, "size": "1"}]:
                        start = time.monotonic()
                        self.on_message(self, json.dumps({**event, "event_type": "last_trade_price"}))
                        callback_times.append(time.monotonic() - start)
                    if not blocked.wait(1):
                        raise AssertionError("worker did not start lookup")
                    if posted.is_set():
                        raise AssertionError("lookup gate should still block only the worker")
                finally:
                    release.set()
                    posted.wait(1)
                raise KeyboardInterrupt

        with patch.object(monitor, "fetch_event_markets", return_value=state), \
                patch.object(monitor, "prepare_ufc_event_images"), \
                patch.object(monitor, "ALERT_SPOOL_DIR", str(self.root)), \
                patch.object(monitor, "HEALTHCHECK_URL", ""), \
                patch.object(monitor, "heartbeat_worker"), \
                patch.object(monitor, "log_event") as log, \
                patch.object(monitor, "send_pushover"), \
                patch.object(monitor, "lookup_trader", side_effect=lookup), \
                patch.object(monitor, "send_x_tweet", side_effect=post) as send, \
                patch.object(monitor.websocket, "WebSocketApp", FakeWebSocket):
            monitor.run_monitor("ufc-test", 1000)
        self.assertEqual(log.call_count, 2)
        self.assertEqual(send.call_count, 1)
        self.assertTrue(all(elapsed < 0.2 for elapsed in callback_times))
        print("[VERIFY] Real on_message callback times:", [round(t, 4) for t in callback_times])

    def test_pending_restart_recovery_but_no_retry_of_claimed_job(self):
        (self.root / "pending.json").write_text(json.dumps({"id": 1}))
        (self.root / "uncertain.inflight").write_text(json.dumps({"id": 2}))
        complete = threading.Event()
        seen = []
        def deliver(job):
            seen.append(job["id"])
            complete.set()
        dispatcher = self.dispatcher(deliver, workers=2)
        self.assertTrue(complete.wait(1))
        dispatcher.close()
        self.assertEqual(seen, [1])
        self.assertTrue((self.root / "uncertain.inflight").exists())

    def test_failed_worker_keeps_evidence_without_retry_and_continues(self):
        calls = []
        completed = threading.Event()
        def deliver(job):
            calls.append(job["id"])
            if job["id"] == 1:
                raise requests.Timeout("uncertain POST")
            completed.set()
        dispatcher = self.dispatcher(deliver, workers=1)
        dispatcher.submit({"id": 1})
        dispatcher.submit({"id": 2})
        self.assertTrue(completed.wait(2))
        dispatcher.close()
        self.assertEqual(calls, [1, 2])
        self.assertEqual(len(list(self.root.glob("*.inflight"))), 1)

    def test_disk_failure_is_explicit_not_a_callback_network_fallback(self):
        dispatcher = self.dispatcher(Mock(), workers=1)
        with patch.object(Path, "write_text", side_effect=OSError("disk full")), \
                patch("builtins.print") as output:
            self.assertFalse(dispatcher.submit({"id": 1}))
        self.assertIn("manual recovery required", str(output.call_args))
        dispatcher.handler.assert_not_called()

    def test_unconfirmed_result_is_kept_without_retry(self):
        complete = threading.Event()
        def deliver(job):
            complete.set()
            return False
        handler = Mock(side_effect=deliver)
        dispatcher = self.dispatcher(handler, workers=1)
        dispatcher.submit({"id": 1})
        self.assertTrue(complete.wait(1))
        dispatcher.close()
        handler.assert_called_once()
        self.assertEqual(len(list(self.root.glob("*.inflight"))), 1)

    def test_full_price_alert_keeps_pushover_but_skips_lookup_and_x(self):
        dispatcher = Mock()
        with patch.object(monitor, "log_event"), patch.object(monitor, "send_pushover") as push, \
                patch.object(monitor, "lookup_trader") as lookup, \
                patch.object(monitor, "send_x_tweet") as post:
            monitor.process_last_trade_price({**EVENT, "price": "0.999"},
                {"12345": INFO}, 1000, alert_dispatcher=dispatcher)
            self.assertTrue(monitor.deliver_whale_alert(dispatcher.submit.call_args.args[0]))
        push.assert_called_once()
        lookup.assert_not_called()
        post.assert_not_called()

    def test_snapshot_does_not_follow_changed_token_metadata(self):
        dispatcher = Mock()
        info, event = INFO.copy(), EVENT.copy()
        with patch.object(monitor, "log_event"):
            monitor.process_last_trade_price(event, {"12345": info}, 1000,
                                             alert_dispatcher=dispatcher)
        event["price"] = "0.01"
        info["event_title"] = "changed"
        job = dispatcher.submit.call_args.args[0]
        self.assertEqual(job["data"]["price"], "0.76")
        self.assertEqual(job["event_title"], INFO["event_title"])


if __name__ == "__main__":
    unittest.main()
