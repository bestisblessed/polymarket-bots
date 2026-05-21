import unittest

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


if __name__ == "__main__":
    unittest.main()
