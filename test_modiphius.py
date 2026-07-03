import unittest

import modiphius


class ParseTestCase(unittest.TestCase):
    def test_all_fields(self):
        # c1 -> complication range of 1, i.e. threshold 20 - 1 = 19.
        self.assertEqual(
            modiphius.parse_test("2d20f3t12c1"),
            {"count": 2, "focus": 3, "target": 12, "comp": 19},
        )

    def test_focus_and_comp_default(self):
        # No c -> range 0 -> threshold 20 (complication only on a natural 20).
        self.assertEqual(
            modiphius.parse_test("2d20t12"),
            {"count": 2, "focus": 1, "target": 12, "comp": 20},
        )

    def test_focus_only(self):
        self.assertEqual(
            modiphius.parse_test("2d20f3t12"),
            {"count": 2, "focus": 3, "target": 12, "comp": 20},
        )

    def test_comp_only(self):
        # c1 -> threshold 19 (19-20 are complications).
        self.assertEqual(
            modiphius.parse_test("2d20t12c1"),
            {"count": 2, "focus": 1, "target": 12, "comp": 19},
        )

    def test_comp_range_two(self):
        # c2 -> threshold 18 (18-20 are complications).
        self.assertEqual(
            modiphius.parse_test("2d20t12c2"),
            {"count": 2, "focus": 1, "target": 12, "comp": 18},
        )

    def test_whitespace_tolerated(self):
        self.assertEqual(
            modiphius.parse_test("  3d20t10 "),
            {"count": 3, "focus": 1, "target": 10, "comp": 20},
        )

    def test_field_order_is_interchangeable(self):
        expected = {"count": 2, "focus": 3, "target": 12, "comp": 19}
        for expr in [
            "2d20f3t12c1",
            "2d20f3c1t12",
            "2d20t12f3c1",
            "2d20t12c1f3",
            "2d20c1f3t12",
            "2d20c1t12f3",
        ]:
            self.assertEqual(modiphius.parse_test(expr), expected, expr)

    def test_partial_fields_any_order(self):
        # t + c only, c before t.
        self.assertEqual(
            modiphius.parse_test("2d20c1t12"),
            {"count": 2, "focus": 1, "target": 12, "comp": 19},
        )
        # t + f only, t before f.
        self.assertEqual(
            modiphius.parse_test("2d20t12f3"),
            {"count": 2, "focus": 3, "target": 12, "comp": 20},
        )

    def test_duplicate_field_rejected(self):
        self.assertIsNone(modiphius.parse_test("2d20t12t14"))
        self.assertIsNone(modiphius.parse_test("2d20f3f4t12"))

    def test_trailing_junk_rejected(self):
        self.assertIsNone(modiphius.parse_test("2d20t12x"))
        self.assertIsNone(modiphius.parse_test("2d20t12 f3"))

    def test_plain_d20_is_not_a_test(self):
        # Must fall through to the d20 arithmetic path, not the Modiphius one.
        self.assertIsNone(modiphius.parse_test("2d20"))

    def test_missing_target_rejected(self):
        self.assertIsNone(modiphius.parse_test("2d20f3"))


class ParseChallengeCase(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(modiphius.parse_challenge("6cd"), {"count": 6})

    def test_whitespace(self):
        self.assertEqual(modiphius.parse_challenge(" 3cd "), {"count": 3})

    def test_not_challenge(self):
        self.assertIsNone(modiphius.parse_challenge("6d6"))
        self.assertIsNone(modiphius.parse_challenge("cd6"))


class EvaluateTestCase(unittest.TestCase):
    def test_focus_die_yields_two_successes(self):
        # 3 <= focus(3) and <= target(12) -> 2 successes; 15 is a miss.
        self.assertEqual(
            modiphius.evaluate_test([3, 15], focus=3, target=12, comp=20),
            (2, 0),
        )

    def test_target_hit_without_focus_is_one_success(self):
        # 10 <= target(12) but > focus(3) -> 1 success.
        self.assertEqual(
            modiphius.evaluate_test([10], focus=3, target=12, comp=20),
            (1, 0),
        )

    def test_complication_counted(self):
        self.assertEqual(
            modiphius.evaluate_test([20], focus=3, target=12, comp=20),
            (0, 1),
        )

    def test_complication_range_below_twenty(self):
        # comp=19 -> both 19 and 20 are complications.
        self.assertEqual(
            modiphius.evaluate_test([19, 20], focus=3, target=12, comp=19),
            (0, 2),
        )

    def test_success_and_complication_together(self):
        # 1 -> 2 successes (default focus 1), 20 -> complication.
        self.assertEqual(
            modiphius.evaluate_test([1, 20], focus=1, target=12, comp=20),
            (2, 1),
        )


class EvaluateChallengeCase(unittest.TestCase):
    def test_face_mapping(self):
        # 1->(1,0) 2->(2,0) 3->(0,0) 4->(0,0) 5->(1,1) 6->(1,1)
        self.assertEqual(
            modiphius.evaluate_challenge([1, 2, 3, 4, 5, 6]),
            (5, 2),
        )

    def test_all_blanks(self):
        self.assertEqual(modiphius.evaluate_challenge([3, 4, 3]), (0, 0))


class FormatCase(unittest.TestCase):
    def test_full_shows_command_and_decode(self):
        self.assertEqual(
            modiphius.format_test_full("2d20f3t12c19", [1, 20], 3, 12, 19, 2, 1),
            "🎲 Rolling `2d20f3t12c19` · 2d20 · Focus 3 · TN 12 · Comp 19+\n"
            "Dice: [1, 20]\n"
            "✨ 2 Successes | ⚠️ 1 Complication",
        )

    def test_full_success_only(self):
        self.assertEqual(
            modiphius.format_test_full("2d20f3t12", [3, 15], 3, 12, 20, 2, 0),
            "🎲 Rolling `2d20f3t12` · 2d20 · Focus 3 · TN 12 · Comp 20+\n"
            "Dice: [3, 15]\n"
            "✨ 2 Successes",
        )

    def test_full_failure_with_complication(self):
        self.assertEqual(
            modiphius.format_test_full("2d20t12", [15, 20], 1, 12, 20, 0, 1),
            "🎲 Rolling `2d20t12` · 2d20 · Focus 1 · TN 12 · Comp 20+\n"
            "Dice: [15, 20]\n"
            "💥 [Failure] | ⚠️ 1 Complication",
        )

    def test_full_failure(self):
        self.assertEqual(
            modiphius.format_test_full("2d20t12", [15, 16], 1, 12, 20, 0, 0),
            "🎲 Rolling `2d20t12` · 2d20 · Focus 1 · TN 12 · Comp 20+\n"
            "Dice: [15, 16]\n"
            "💥 [Failure]",
        )

    def test_single_success_is_singular(self):
        self.assertEqual(
            modiphius.format_test_full("1d20t12", [10], 1, 12, 20, 1, 0),
            "🎲 Rolling `1d20t12` · 1d20 · Focus 1 · TN 12 · Comp 20+\n"
            "Dice: [10]\n"
            "✨ 1 Success",
        )

    def test_challenge_full(self):
        self.assertEqual(
            modiphius.format_challenge_full("3cd", [1, 2, 5], 4, 1),
            "🎲 Rolling `3cd` · 3 Challenge Dice\n"
            "Dice: [1, 2, 5]\n"
            "**Total Result:** 4 | **Total Effects:** 1",
        )


class RollCase(unittest.TestCase):
    def test_test_roll_shape(self):
        out = modiphius.roll("2d20f3t12c19")
        self.assertIn("full_text", out)
        self.assertIn("inline", out)
        self.assertIn("summary", out)
        self.assertIn("expression", out)

    def test_challenge_roll_shape(self):
        out = modiphius.roll("6cd")
        self.assertTrue(out["full_text"].startswith("🎲 Rolling `6cd`"))

    def test_non_modiphius_returns_none(self):
        self.assertIsNone(modiphius.roll("2d20"))
        self.assertIsNone(modiphius.roll("1d6+3"))


if __name__ == "__main__":
    unittest.main()
