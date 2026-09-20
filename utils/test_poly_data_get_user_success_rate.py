import unittest

from utils.poly_data_get_user_success_rate import (
    calculate_success_summary,
    classify_prediction_result,
    normalize_user_target,
    select_exact_profile_match,
)


class PolymarketUserSuccessRateTests(unittest.TestCase):
    def test_normalize_wallet_target(self):
        kind, value = normalize_user_target("0x2589876F7934D8B9ED551E911E1B50DABBCC6868")

        self.assertEqual(kind, "wallet")
        self.assertEqual(value, "0x2589876f7934d8b9ed551e911e1b50dabbcc6868")

    def test_normalize_username_target(self):
        kind, value = normalize_user_target("@SakuraLover")

        self.assertEqual(kind, "username")
        self.assertEqual(value, "sakuralover")

    def test_normalize_profile_url_target(self):
        kind, value = normalize_user_target("https://polymarket.com/@aussietoken?tab=positions")

        self.assertEqual(kind, "username")
        self.assertEqual(value, "aussietoken")

    def test_select_exact_profile_match(self):
        profile = select_exact_profile_match(
            "aussietoken",
            [
                {"name": "aussietoken2", "proxyWallet": "0x1111111111111111111111111111111111111111"},
                {"name": "AussieToken", "proxyWallet": "0x2589876f7934d8b9ed551e911e1b50dabbcc6868"},
            ],
        )

        self.assertEqual(profile["proxyWallet"], "0x2589876f7934d8b9ed551e911e1b50dabbcc6868")

    def test_classify_prediction_result_uses_final_price_not_pnl(self):
        self.assertEqual(
            classify_prediction_result({"curPrice": 1, "realizedPnl": -30.8}),
            "success",
        )
        self.assertEqual(
            classify_prediction_result({"curPrice": 0, "realizedPnl": 42.0}),
            "failure",
        )
        self.assertEqual(
            classify_prediction_result({"curPrice": 0.5, "realizedPnl": -10.0}),
            "pending",
        )

    def test_calculate_success_summary_separates_prediction_and_pnl_results(self):
        summary = calculate_success_summary(
            total_traded=5,
            closed_positions=[
                {"curPrice": 1, "realizedPnl": -30.8},
                {"curPrice": 0, "realizedPnl": 12.5},
                {"curPrice": 0.5, "realizedPnl": "-3.25"},
                {"curPrice": 1, "realizedPnl": 0},
            ],
            current_positions=[
                {"curPrice": 0.6, "cashPnl": 10.0},
            ],
        )

        self.assertEqual(summary["prediction_successes"], 2)
        self.assertEqual(summary["prediction_failures"], 1)
        self.assertEqual(summary["prediction_pending"], 2)
        self.assertAlmostEqual(summary["prediction_hit_rate"], 66.66666666666666)
        self.assertEqual(summary["website_visible_wins"], 1)
        self.assertEqual(summary["profitable_closed_trades"], 1)
        self.assertEqual(summary["negative_pnl_closed_trades"], 2)
        self.assertEqual(summary["breakeven_closed_trades"], 1)
        self.assertEqual(summary["active_unresolved"], 1)

    def test_calculate_success_summary_handles_zero_resolved_prediction_count(self):
        summary = calculate_success_summary(
            total_traded=2,
            closed_positions=[{"curPrice": 0.5, "realizedPnl": -1}],
            current_positions=[{"curPrice": 0.6, "cashPnl": 5}],
        )

        self.assertEqual(summary["prediction_successes"], 0)
        self.assertEqual(summary["prediction_failures"], 0)
        self.assertEqual(summary["prediction_pending"], 2)
        self.assertIsNone(summary["prediction_hit_rate"])

    def test_calculate_success_summary_collapses_duplicate_market_rows(self):
        summary = calculate_success_summary(
            total_traded=1,
            closed_positions=[
                {
                    "conditionId": "0xabc",
                    "curPrice": 1,
                    "realizedPnl": 25,
                    "outcome": "No",
                    "title": "Will example happen?",
                },
            ],
            current_positions=[
                {
                    "conditionId": "0xabc",
                    "curPrice": 0,
                    "cashPnl": -100,
                    "outcome": "Yes",
                    "title": "Will example happen?",
                },
            ],
        )

        self.assertEqual(summary["raw_source_row_count"], 2)
        self.assertEqual(summary["source_row_count"], 1)
        self.assertEqual(summary["duplicate_market_rows"], 1)
        self.assertEqual(summary["prediction_successes"], 1)
        self.assertEqual(summary["prediction_failures"], 0)
        self.assertEqual(summary["website_visible_wins"], 1)
        self.assertEqual(summary["active_current_loss"], 0)

    def test_profile_visible_rate_excludes_negative_closed_api_rows(self):
        summary = calculate_success_summary(
            total_traded=3,
            closed_positions=[
                {"conditionId": "0xwin", "curPrice": 1, "realizedPnl": 10},
                {"conditionId": "0xloss", "curPrice": 0, "realizedPnl": -5},
            ],
            current_positions=[
                {"conditionId": "0xopen", "curPrice": 0.6, "cashPnl": 2},
            ],
        )

        self.assertEqual(summary["profile_visible_closed_wins"], 1)
        self.assertEqual(summary["profile_visible_closed_losses"], 0)
        self.assertEqual(summary["api_only_closed_markets"], 1)
        self.assertAlmostEqual(summary["profile_visible_closed_hit_rate"], 100.0)
        self.assertAlmostEqual(summary["api_final_outcome_hit_rate"], 50.0)


if __name__ == "__main__":
    unittest.main()
