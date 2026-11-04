"""Offline quota parsing and guard checks. No account or model calls."""
import unittest
from datetime import datetime

from usage_probe import summarize_rate_limits, codex_budget_block_reason


class QuotaTests(unittest.TestCase):
    def reading(self, primary=10080, used=23, secondary=None):
        return summarize_rate_limits({"ordinaryUsageAllowed": True, "rateLimitsByLimitId": {
            "codex": {"primary": {"windowDurationMins": primary, "usedPercent": used},
                      "secondary": secondary}}})

    def test_weekly_only_is_usable_without_inventing_five_hour_capacity(self):
        reading = self.reading()
        self.assertIsNone(reading["codex_5h_remaining"])
        self.assertEqual(reading["codex_remaining"], 77)
        self.assertEqual(reading["limiting_window_minutes"], 10080)
        self.assertIsNone(codex_budget_block_reason(reading))

    def test_both_windows_enforce_the_most_constrained_one(self):
        reading = self.reading(primary=300, used=20, secondary={"windowDurationMins": 10080, "usedPercent": 85})
        self.assertEqual(reading["codex_5h_remaining"], 80)
        self.assertEqual(reading["codex_remaining"], 15)
        self.assertIn("15%", codex_budget_block_reason(reading))

    def test_five_hour_window_can_be_secondary(self):
        reading = self.reading(secondary={"windowDurationMins": 300, "usedPercent": 42.5})
        self.assertEqual(reading["codex_5h_remaining"], 57.5)
        self.assertEqual(reading["limiting_window_minutes"], 300)

    def test_legacy_provider_shape_and_old_local_records_remain_supported(self):
        reading = summarize_rate_limits({"rateLimits": {"primary": {"windowDurationMins": 300, "usedPercent": 10}}})
        self.assertEqual(reading["codex_5h_remaining"], 90)
        legacy = {"codex_5h_remaining": 90, "observed_at": reading["observed_at"]}
        self.assertIsNone(codex_budget_block_reason(legacy))

    def test_absent_or_malformed_provider_windows_fail_closed(self):
        for value in (None, True, -1, 101, "23", float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.reading(used=value)
        for value in (None, 0, -1, "300", True):
            with self.subTest(minutes=value), self.assertRaises(ValueError):
                self.reading(primary=value)
        with self.assertRaises(RuntimeError):
            summarize_rate_limits({})

    def test_unavailable_or_disabled_account_blocks(self):
        reading = self.reading()
        reading["ordinary_usage_allowed"] = False
        self.assertIsNotNone(codex_budget_block_reason(reading))
        reading["ordinary_usage_allowed"] = True
        reading["probe_error"] = "provider unavailable"
        self.assertIsNotNone(codex_budget_block_reason(reading))

    def test_stale_future_and_invalid_timestamps_block(self):
        reading = self.reading()
        observed = datetime.fromisoformat(reading["observed_at"]).timestamp()
        self.assertIsNotNone(codex_budget_block_reason(reading, observed + 1801))
        self.assertIsNotNone(codex_budget_block_reason(reading, observed - 60))
        for value in (None, "bad", 3):
            reading["observed_at"] = value
            self.assertIsNotNone(codex_budget_block_reason(reading))

    def test_invalid_saved_windows_cannot_bypass_guard(self):
        for windows in ([], {}, [None], [{"window_minutes": 10080, "remaining_percent": True}],
                        [{"window_minutes": 10080, "remaining_percent": 101}]):
            reading = self.reading()
            reading["quota_windows"] = windows
            self.assertIsNotNone(codex_budget_block_reason(reading))


if __name__ == "__main__":
    unittest.main()
