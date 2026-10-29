import unittest

from group_chat import route_message, strip_handoff


class RoutingTests(unittest.TestCase):
    def test_plain_group_message_invites_all_once(self):
        route = route_message("Plan next step", "group", "all", ["deepseek", "codex"])
        self.assertEqual(route["recipients"], ["deepseek", "codex"])
        self.assertEqual(route["max_replies"], 2)

    def test_direct_slash_overrides_discussion_and_all_selection(self):
        route = route_message("/codex\nReview this", "group", "all", ["deepseek", "codex"], 3)
        self.assertEqual(route["recipients"], ["codex"])
        self.assertEqual(route["max_replies"], 1)
        self.assertEqual(route["rounds"], 0)

    def test_discussion_is_bounded_and_requires_group(self):
        route = route_message("/讨论 3 审查", "group", "all", ["deepseek", "codex"])
        self.assertEqual(route["max_replies"], 6)
        for message, mode in (("/讨论 4 检查", "group"), ("/all hi", "single"), ("/unknown hi", "group")):
            with self.assertRaises(ValueError):
                route_message(message, mode, "deepseek", ["deepseek", "codex"])

    def test_only_final_valid_handoff_can_schedule(self):
        answer, target = strip_handoff("Review complete\nAGENTBOARD_TO: deepseek", "codex", ["deepseek", "codex"])
        self.assertEqual(answer, "Review complete")
        self.assertEqual(target, "deepseek")
        self.assertIsNone(strip_handoff("Done\nAGENTBOARD_TO: codex", "codex", ["deepseek", "codex"])[1])
        self.assertIsNone(strip_handoff("AGENTBOARD_TO: deepseek\nQuoted, not a handoff", "codex", ["deepseek", "codex"])[1])
        self.assertEqual(strip_handoff("Conclusion. AGENTBOARD_TO: DONE", "codex", ["deepseek", "codex"]), ("Conclusion.", None))


if __name__ == "__main__":
    unittest.main()
