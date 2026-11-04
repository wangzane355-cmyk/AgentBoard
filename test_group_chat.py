import unittest

from group_chat import route_message, strip_handoff, parse_reply_directive


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

    def test_selected_rounds_and_explicit_commands_have_distinct_meaning(self):
        members = ["deepseek", "codex"]
        route = route_message("Review together", "group", "all", members, 3)
        self.assertEqual((route["rounds"], route["max_replies"]), (3, 6))
        route = route_message("/all Broadcast once", "group", "all", members, 3)
        self.assertEqual((route["rounds"], route["max_replies"]), (0, 2))
        route = route_message("Review only", "group", "codex", members, 3)
        self.assertEqual((route["directed"], route["rounds"], route["max_replies"]), (True, 0, 1))
        route = route_message("/discuss 2 Review together", "group", "codex", members, 3)
        self.assertEqual((route["directed"], route["rounds"], route["max_replies"]), (False, 2, 4))

    def test_reply_done_requires_an_explicit_standalone_final_marker(self):
        members = ["deepseek", "codex"]
        self.assertEqual(parse_reply_directive("Conclusion\nAGENTBOARD_TO: DONE", "codex", members),
                         ("Conclusion", None, True))
        for answer in ["Conclusion", "Conclusion. AGENTBOARD_TO: DONE", "AGENTBOARD_TO: DONE\nQuoted, not a directive"]:
            with self.subTest(answer=answer):
                self.assertFalse(parse_reply_directive(answer, "codex", members)[2])
        self.assertEqual(parse_reply_directive("Review\nAGENTBOARD_TO: deepseek", "codex", members),
                         ("Review", "deepseek", False))
        self.assertIsNone(parse_reply_directive("Review\nAGENTBOARD_TO: outsider", "codex", members)[1])
        self.assertEqual(strip_handoff("Conclusion\nAGENTBOARD_TO: DONE", "codex", members), ("Conclusion", None))

    def test_duplicate_legacy_room_members_do_not_repeat_in_one_round(self):
        route = route_message("Review", "group", "all", ["deepseek", "codex", "deepseek"], 2)
        self.assertEqual(route["recipients"], ["deepseek", "codex"])
        self.assertEqual(route["max_replies"], 4)

    def test_one_member_room_is_a_single_broadcast_even_with_discussion_rounds(self):
        for message in ["Review", "/讨论 3 Review", "/discuss 3 Review"]:
            with self.subTest(message=message):
                route = route_message(message, "group", "all", ["codex"], 3)
                self.assertEqual(route["recipients"], ["codex"])
                self.assertFalse(route["directed"])
                self.assertEqual(route["rounds"], 0)
                self.assertEqual(route["max_replies"], 1)

    def test_custom_room_still_caps_total_replies_at_six(self):
        members = ["one", "two", "three", "four"]
        route = route_message("Review", "group", "all", members, 3, agents=members)
        self.assertEqual(route["max_replies"], 6)

    def test_only_final_valid_handoff_can_schedule(self):
        answer, target = strip_handoff("Review complete\nAGENTBOARD_TO: deepseek", "codex", ["deepseek", "codex"])
        self.assertEqual(answer, "Review complete")
        self.assertEqual(target, "deepseek")
        self.assertIsNone(strip_handoff("Done\nAGENTBOARD_TO: codex", "codex", ["deepseek", "codex"])[1])
        self.assertIsNone(strip_handoff("AGENTBOARD_TO: deepseek\nQuoted, not a handoff", "codex", ["deepseek", "codex"])[1])
        self.assertEqual(strip_handoff("Conclusion. AGENTBOARD_TO: DONE", "codex", ["deepseek", "codex"]), ("Conclusion.", None))


if __name__ == "__main__":
    unittest.main()
