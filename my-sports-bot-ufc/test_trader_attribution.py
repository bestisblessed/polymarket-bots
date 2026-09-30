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


def trade_page(rows, cursor=None):
    """Convert recorded v1 fixtures to the documented v2 response envelope."""
    fields = {"conditionId": "condition_id", "asset": "token_id",
              "transactionHash": "transaction_hash", "proxyWallet": "proxy_wallet"}
    return {"data": [{fields.get(key, key): value for key, value in row.items()} for row in rows],
            "pagination": {"limit": 1000, "offset": 0, "has_more": cursor is not None,
                           "next_cursor": cursor}}


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

    def test_recent_alert_timestamp_lag(self):
        # Reconstructed stream fields and public trade timestamps from the two
        # Sep 30 alerts; original stream hashes were not retained.
        for timestamp, settled, size, public_size in [
                (1790794391389, 1790794394, "329", 329),
                (1790794793036, 1790794796, "1490.3235", 1490.323528)]:
            with self.subTest(timestamp=timestamp):
                event = {**EVENT, "timestamp": str(timestamp), "size": size}
                row = {**TRADE, "timestamp": settled, "size": public_size}
                for hashed in (True, False):
                    candidate = dict(event)
                    if not hashed:
                        candidate.pop("transaction_hash")
                    trader, evidence = attribution.match_trader(candidate, CONDITION, [row])
                    self.assertEqual(trader["wallet"], WALLET)
                    self.assertEqual(evidence["candidate_count"], 1)

    def test_extended_timestamp_window_keeps_safety_checks(self):
        event = {**EVENT, "timestamp": "1786702800000"}
        for delta in (-5, 5):
            row = {**TRADE, "timestamp": 1786702800 + delta}
            self.assertIsNotNone(attribution.match_trader(event, CONDITION, [row])[0])
            wrong_hash = {**row, "transactionHash": "0x" + "4" * 64}
            self.assertIsNone(attribution.match_trader(event, CONDITION, [wrong_hash])[0])
            other = {**row, "proxyWallet": "0x" + "4" * 40}
            self.assertEqual(attribution.match_trader(event, CONDITION, [row, other])[1]["status"], "ambiguous")
        for delta in (-6, 6):
            self.assertIsNone(attribution.match_trader(event, CONDITION,
                              [{**TRADE, "timestamp": 1786702800 + delta}])[0])

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
        empty.json.return_value = trade_page([])
        indexed.json.return_value = trade_page([TRADE])
        with patch.object(attribution.requests, "get", side_effect=[empty, indexed]) as get, \
                patch.object(attribution.threading.Event, "wait", return_value=False):
            trader, evidence = attribution.lookup_trader(EVENT, CONDITION, budget=1)
        self.assertEqual(trader["wallet"], WALLET)
        self.assertEqual(evidence["attempts"], 2)
        self.assertEqual(get.call_args.args[0], "https://data-api.polymarket.com/v2/trades")
        self.assertEqual(get.call_args.kwargs["params"]["condition"], CONDITION)
        self.assertEqual(get.call_args.kwargs["params"]["side"], "BUY")
        self.assertEqual(get.call_args.kwargs["params"]["taker_only"], "true")
        self.assertEqual(get.call_args.kwargs["params"]["filter_amount"], "6745.1799")
        self.assertNotIn("start", get.call_args.kwargs["params"])
        self.assertEqual(evidence["window_seconds"], 5)
        self.assertEqual(evidence["event"]["timestamp"], EVENT["timestamp"])

    def test_lookup_wall_clock_timeout(self):
        response = Mock()
        response.json.return_value = trade_page([])
        def delayed(*args, **kwargs):
            time.sleep(0.2)
            return response
        with patch.object(attribution.requests, "get", side_effect=delayed):
            start = time.monotonic()
            trader, evidence = attribution.lookup_trader(EVENT, CONDITION, budget=0.03)
        self.assertIsNone(trader)
        self.assertEqual(evidence["status"], "timeout")
        self.assertEqual(evidence["attempts"], 1)
        self.assertGreaterEqual(evidence["elapsed_seconds"], 0.03)
        self.assertLess(time.monotonic() - start, 0.15)

    def test_lookup_error_attempts_are_retained(self):
        indexed = Mock()
        indexed.json.return_value = trade_page([TRADE])
        with patch.object(attribution.requests, "get", side_effect=[requests.Timeout(), indexed]), \
                patch.object(attribution.threading.Event, "wait", return_value=False):
            trader, evidence = attribution.lookup_trader(EVENT, CONDITION, budget=1)
        self.assertEqual(trader["wallet"], WALLET)
        self.assertEqual(evidence["attempts"], 2)
        self.assertIn("elapsed_seconds", evidence)


class V2FeedTests(unittest.TestCase):
    def lookup(self, pages, *, event=EVENT, condition=CONDITION):
        responses = []
        for page in pages:
            response = Mock(headers={"CF-Cache-Status": "DYNAMIC"})
            response.json.return_value = page
            responses.append(response)
        with patch.object(attribution.requests, "get", side_effect=responses) as get:
            result = attribution.lookup_trader(event, condition, budget=1)
        self.assertTrue(all(call.args[0].endswith("/v2/trades") for call in get.call_args_list))
        return result, get

    def test_matching_later_page_and_fixed_local_window(self):
        outside = {**TRADE, "timestamp": TRADE["timestamp"] - 20}
        result, get = self.lookup([trade_page([outside] * 1000, "next-page"), trade_page([TRADE])])
        self.assertEqual(result[0]["wallet"], WALLET)
        self.assertEqual(result[1]["pages"], 2)
        self.assertEqual(result[1]["outside_window"], 1000)
        self.assertEqual(result[1]["response_rows"], 1001)
        self.assertEqual(get.call_args.kwargs["params"]["cursor"], "next-page")

    def test_first_page_is_not_accepted_before_ambiguity_check(self):
        other = {**TRADE, "proxyWallet": "0x" + "4" * 40}
        result, get = self.lookup([trade_page([TRADE], "next-page"), trade_page([other])])
        self.assertIsNone(result[0])
        self.assertEqual(result[1]["status"], "ambiguous")
        self.assertEqual(get.call_count, 2)

    def test_invalid_envelopes_and_cursor_loops_fall_back(self):
        for page in ([TRADE], {"data": []}, trade_page([{}]),
                     {"data": [], "pagination": {"has_more": True, "next_cursor": None}}):
            result, _ = self.lookup([page])
            self.assertIsNone(result[0])
            self.assertIn(result[1]["status"], ("invalid_response", "incomplete_window"))
        result, _ = self.lookup([trade_page([TRADE], "loop"), trade_page([], "loop")])
        self.assertIsNone(result[0])
        self.assertEqual(result[1]["status"], "incomplete_window")

    def test_hash_rejection_is_logged_with_original_evidence(self):
        wrong = {**TRADE, "transactionHash": "0x" + "4" * 64}
        response = Mock(headers={"CF-Cache-Status": "DYNAMIC"})
        response.json.return_value = trade_page([wrong])
        with patch.object(attribution.requests, "get", return_value=response):
            trader, evidence = attribution.lookup_trader(EVENT, CONDITION, budget=.02)
        self.assertIsNone(trader)
        self.assertEqual(evidence["last_status"], "unmatched")
        self.assertEqual(evidence["rejected"], {"transaction_hash": 1})
        self.assertEqual(evidence["event"]["transaction_hash"], TX)
        self.assertEqual(evidence["cache_status"], "DYNAMIC")

    def test_failed_gautier_alert_regression(self):
        # Actual log fields + public Data API row. The original stream hash
        # was not retained; this is explicitly a reconstructed event.
        condition = "0x4b897f960f234b0b6f07ee08313481443ce839b2fa6440ab120a3e32398e1b1f"
        token = "52563667488257722253844178460924496771983983501858347935033892130384423158852"
        event = {"asset_id": token, "market": condition, "side": "BUY",
                 "price": ".67", "size": "655.86", "timestamp": "1790802763248"}
        row = {**TRADE, "conditionId": condition, "asset": token,
               "price": .67, "size": 655.86, "timestamp": 1790802765,
               "transactionHash": "0x920123f4fda3aaa0c04b49a901049d8d4b6c81084ea72ee63197d291d932f777",
               "proxyWallet": "0x6dd6314d1670f9f1ccccbd6746b0bf2f2fa0f5f4", "name": "4751346"}
        response = Mock(headers={"CF-Cache-Status": "DYNAMIC"})
        response.json.return_value = trade_page([row])
        with patch.object(attribution.requests, "get", return_value=response):
            trader, evidence = attribution.lookup_trader(event, condition, budget=1)
        self.assertEqual(trader["name"], "4751346")
        self.assertEqual(trader["wallet"], row["proxyWallet"])
        self.assertEqual(evidence["matched_by"], "unique_trade")
        self.assertEqual(evidence["attempts"], 1)

    def test_recorded_live_event_matches_original_hash_and_wallet(self):
        # Recorded Sep 30 MLB stream event, not a reconstructed UFC event.
        condition = "0x17c93ea8fa84d1f0c5916e79f033d3623fed8d4d431089f21557fdc91b2b0fd6"
        token = "42582623562674250237201115321153881172387239207835122724506860872726437197351"
        tx = "0x9ee22aab2b6b60366f728aa96d85f9447d876466e8346e3fd4dbd832fed06dc1"
        wallet = "0x5268527977f700f9bf9b6d5cd843859e4e70135d"
        event = {"market": condition, "asset_id": token, "side": "BUY", "price": "0.64",
                 "size": "300", "timestamp": "1790804533150", "transaction_hash": tx}
        row = {**TRADE, "conditionId": condition, "asset": token, "price": .64,
               "size": 300, "timestamp": 1790804535, "transactionHash": tx,
               "proxyWallet": wallet, "name": "HomeRunHazard"}
        result, _ = self.lookup([trade_page([row])], event=event, condition=condition)
        self.assertEqual(result[0]["wallet"], wallet)
        self.assertEqual(result[0]["name"], "HomeRunHazard")
        self.assertEqual(result[1]["transaction_hash"], event["transaction_hash"])
        self.assertEqual(result[1]["matched_by"], "transaction_hash")


class AttributionBudgetTests(unittest.TestCase):
    def simulate(self, indexed_at, *, budget=None, rows=None):
        clock = [0.0]
        waits = []
        cached = {}

        class FakeEvent:
            stopped = False

            def is_set(self):
                return self.stopped

            def set(self):
                self.stopped = True

            def wait(self, seconds):
                waits.append(seconds)
                clock[0] += seconds
                return self.stopped

        class InlineThread:
            def __init__(self, *, target, **kwargs):
                self.target = target

            def start(self):
                self.target()

        def fetch(*args, **kwargs):
            # A request begun at 88s can finish with indexed data at 89s.
            if indexed_at is not None and 0 < indexed_at - clock[0] <= 1:
                clock[0] = float(indexed_at)
            response = Mock()
            # Reproduce a cache that freezes an initially empty URL for >90s.
            key = tuple(sorted(kwargs["params"].items()))
            if key not in cached:
                cached[key] = trade_page(([TRADE] if rows is None else rows)
                                          if indexed_at is not None and clock[0] >= indexed_at else [])
            response.json.return_value = cached[key]
            return response

        with patch.object(attribution.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(attribution.time, "time", side_effect=lambda: 1790802763 + clock[0]), \
                patch.object(attribution.threading, "Event", FakeEvent), \
                patch.object(attribution.threading, "Thread", InlineThread), \
                patch.object(attribution.requests, "get", side_effect=fetch) as get:
            result = attribution.lookup_trader(EVENT, CONDITION, **({} if budget is None else {"budget": budget}))
            attempts = get.call_count
            clock[0] += 100
            self.assertEqual(get.call_count, attempts, "polling must stop after returning")
        self.assertTrue(all(0 <= seconds <= 2 for seconds in waits))
        stable = {key: value for key, value in get.call_args.kwargs["params"].items() if key != "end"}
        self.assertTrue(all({key: value for key, value in call.kwargs["params"].items() if key != "end"}
                            == stable for call in get.call_args_list))
        self.assertEqual(len({call.kwargs["params"]["end"] for call in get.call_args_list}), attempts,
                         "retries must not reuse a cached first-page URL")
        self.assertEqual(result[1]["event"]["timestamp"], EVENT["timestamp"])
        self.assertEqual(result[1]["window_seconds"], 5, "matching window must stay fixed")
        self.assertEqual(result[1]["attempts"], attempts)
        return result

    def test_delayed_indexing_posts_once_with_attribution(self):
        for indexed_at in (0, 20, 60, 89):
            with self.subTest(indexed_at=indexed_at):
                result = self.simulate(indexed_at)
                self.assertEqual(result[1]["status"], "matched")
                self.assertEqual(result[1]["elapsed_seconds"], indexed_at)
                self.deliver_once(result, attributed=True)
                print(f"[VERIFY] Indexing at {indexed_at}s: one attributed post")

    def test_90_second_deadline_posts_once_without_attribution(self):
        result = self.simulate(None, budget=200)
        self.assertEqual(result[1]["status"], "timeout")
        self.assertEqual(result[1]["budget_seconds"], 90)
        self.assertEqual(result[1]["elapsed_seconds"], 90)
        self.assertEqual(result[1]["last_status"], "unmatched")
        self.deliver_once(result, attributed=False)
        print("[VERIFY] Unavailable at 90s: one fallback post, polling stopped")

    def test_unsafe_and_invalid_results_do_not_wait(self):
        other = {**TRADE, "proxyWallet": "0x" + "4" * 40}
        for rows, status in [([TRADE, other], "ambiguous"), ([{}], "invalid_response")]:
            result = self.simulate(0, rows=rows)
            self.assertIsNone(result[0])
            self.assertEqual(result[1]["status"], status)
            self.assertEqual(result[1]["elapsed_seconds"], 0)
            self.deliver_once(result, attributed=False)

    def deliver_once(self, result, *, attributed):
        job = {"data": EVENT, "condition_id": CONDITION, "price": .76,
               "event_title": INFO["event_title"], "market_display": "Moneyline",
               "outcome": INFO["outcome"], "usd_value": 5126.34,
               "potential_profit": 1618.84, "size": 6745.18,
               "ufc_image_path": None, "pushover_message": "test", "event_url": ""}
        with patch.object(monitor, "send_pushover") as push, \
                patch.object(monitor, "lookup_trader", return_value=result) as lookup, \
                patch.object(monitor, "send_x_tweet", return_value="test-post-id") as post:
            def find(*args):
                push.assert_called_once()
                return result
            lookup.side_effect = find
            self.assertTrue(monitor.deliver_whale_alert(job))
        lookup.assert_called_once()
        post.assert_called_once()
        self.assertEqual("Polymarket Trader:" in post.call_args.args[0], attributed)


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
