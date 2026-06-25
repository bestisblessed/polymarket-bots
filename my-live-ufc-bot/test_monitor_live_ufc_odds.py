import unittest
from datetime import datetime, timezone

import monitor_live_ufc_odds as bot


class LiveUfcOddsTests(unittest.TestCase):
    def test_best_ask_uses_lowest_ask_price(self):
        book = {
            "asks": [
                {"price": "0.03", "size": "50"},
                {"price": "0.01", "size": "10"},
                {"price": "0.02", "size": "20"},
            ]
        }

        self.assertEqual(bot.best_ask_from_book(book), 0.01)

    def test_alert_triggers_at_or_below_threshold_once(self):
        alerted = set()

        first = bot.should_alert("asset-1", 0.01, 0.01, alerted)
        alerted.add("asset-1")
        second = bot.should_alert("asset-1", 0.01, 0.01, alerted)

        self.assertTrue(first)
        self.assertFalse(second)

    def test_alert_does_not_trigger_above_threshold_or_missing_price(self):
        self.assertFalse(bot.should_alert("asset-1", 0.02, 0.01, set()))
        self.assertFalse(bot.should_alert("asset-1", None, 0.01, set()))

    def test_live_gate_requires_sports_live_state_by_default(self):
        info = {
            "event_slug": "ufc-fighter-a-fighter-b",
            "event_closed": False,
            "event_archived": False,
            "market_active": True,
            "market_closed": False,
            "market_archived": False,
            "accepting_orders": True,
        }

        allowed, reason = bot.is_live_alert_allowed(
            "asset-1",
            info,
            sports_states={},
            resolved_asset_ids=set(),
            require_sports_live=True,
        )

        self.assertFalse(allowed)
        self.assertIn("sports live", reason)

    def test_live_gate_allows_in_progress_sports_state(self):
        info = {
            "event_slug": "ufc-fighter-a-fighter-b",
            "event_closed": False,
            "event_archived": False,
            "market_active": True,
            "market_closed": False,
            "market_archived": False,
            "accepting_orders": True,
        }
        states = {
            "ufc-fighter-a-fighter-b": {
                "live": True,
                "ended": False,
                "status": "InProgress",
            }
        }

        allowed, reason = bot.is_live_alert_allowed(
            "asset-1",
            info,
            sports_states=states,
            resolved_asset_ids=set(),
            require_sports_live=True,
        )

        self.assertTrue(allowed, reason)

    def test_live_gate_suppresses_ended_or_resolved_markets(self):
        info = {
            "event_slug": "ufc-fighter-a-fighter-b",
            "event_closed": False,
            "event_archived": False,
            "market_active": True,
            "market_closed": False,
            "market_archived": False,
            "accepting_orders": True,
        }
        states = {
            "ufc-fighter-a-fighter-b": {
                "live": False,
                "ended": True,
                "status": "Final",
            }
        }

        ended_allowed, _ = bot.is_live_alert_allowed(
            "asset-1",
            info,
            sports_states=states,
            resolved_asset_ids=set(),
            require_sports_live=True,
        )
        resolved_allowed, _ = bot.is_live_alert_allowed(
            "asset-1",
            {**info, "event_slug": "other-live-fight"},
            sports_states={"other-live-fight": {"live": True, "ended": False}},
            resolved_asset_ids={"asset-1"},
            require_sports_live=True,
        )

        self.assertFalse(ended_allowed)
        self.assertFalse(resolved_allowed)

    def test_sports_state_from_message_normalizes_status(self):
        state = bot.sports_state_from_message(
            {
                "event_type": "sport_result",
                "slug": "ufc-fighter-a-fighter-b",
                "status": "InProgress",
                "live": False,
                "ended": False,
            },
            received_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        )

        self.assertEqual(state["slug"], "ufc-fighter-a-fighter-b")
        self.assertTrue(state["live"])
        self.assertFalse(state["ended"])

    def test_sports_state_from_message_handles_string_booleans(self):
        state = bot.sports_state_from_message(
            {
                "slug": "ufc-fighter-a-fighter-b",
                "status": "Scheduled",
                "live": "false",
                "ended": "false",
            }
        )

        self.assertFalse(state["live"])
        self.assertFalse(state["ended"])


if __name__ == "__main__":
    unittest.main()
